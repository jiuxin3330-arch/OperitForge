# 附帶小案報告(2026-08-30 合稿裁定,同單兩件)

執行窗:CC(Swap 實驗規劃分支)。成本總帳見同分支 `SWAP_COST_LEDGER_20260830.md`。
所有代碼變更都在 VPS 上,改前均留 `.bak-*` 備份;本文記錄變更點與驗證證據,
逐字 diff 可在 VPS 上 `diff -u <bak> <file>` 重現。**A/B 的逐條 event 內容不出島**
(含私人對話內容),詳表在 VPS:`/srv/nest-memory/health/ab_regression_20260830_0701.{md,json}`。

---

## 小案①:extractor Sonnet 5 A/B regression + 429 退避重試

### 429/5xx 退避重試(已上線)
- `/srv/nest-memory/bin/extractor.py`:`call_haiku()` 加 429/500/502/503/504/529
  退避重試,60s × 3 次,其他錯誤照舊直接拋、batch 落 `failed` 留痕。
- **不是假想需求**:2026-08-30 03:30 的每日抽取(batch 24)正好被 429 打掛。
  修完後手動補跑,batch 25 committed(rows 957-992,6 events),投影+snapshot 已跟上。
- 同時把 `MODEL` 改為可用環境變數 `NEST_EXTRACTOR_MODEL` 覆寫(預設仍 Haiku 4.5 不變),
  `extract()`/`call_haiku()` 加 `model` 參數——A/B 與未來正式換模都走這個口,不動預設。

### A/B regression 結果(哨兵數字;質面詳表在 VPS 人審)
新工具 `/srv/nest-memory/bin/ab_regression.py`:golden 全跑 ×2 模型 +
過去 7 天真實 raw(216 條/4 批,照生產 60 條批次規則)雙模型重抽。
抽取結果只進 :memory: 沙盒(預載生產 subjects/events/state,升級行為與生產一致),
**生產 events 零寫入**;raw 外送兩次均記 `egress_audit(purpose=ab_regression)`。

| 指標 | Haiku 4.5(現役) | Sonnet 5(候選) |
|---|---|---|
| golden | 11 passed / 0 failed | 11 passed / 0 failed |
| raw 7d events | 32 | 22 |
| proposals | 4 | 0 |
| dropped | 0 | 0 |
| escalated | 23 | 16 |
| secret 命中 | 0 | 0 |

**初判(需規劃窗+糯糯質面人審後才裁定換不換)**:
- 「過度記憶」方向與預想相反——**過抽的是 Haiku**:同一事實抽出多筆重複
  (例:選課完成一事抽 3 筆)、輸出英文 snake_case 碎片值(`course_registration_completed`
  這類,對 owner 不可讀)、subject 歸位錯誤(把筆友/心情日曆的事放進 `chatnest.agent_sdk`)。
- Sonnet 5:條數較少但單條資訊密度高、全中文可讀、subject 歸位正確,無碎片值。
- Sonnet 漏抽風險:有幾條 Haiku 抽到的日常細節 Sonnet 沒抽(詳表「只有 Haiku 抽出」節),
  需人眼判斷那些是「該記的」還是「本來就不該成 event 的閒聊」。
- 成本:Sonnet 5 $2/$10 vs Haiku $1/$5 每 MTok,每日一批量級,差額可忽略。
- **本窗未切換預設模型**——裁定條件是「數據上真的更穩才換」,數字+質面樣本已備齊,
  等規劃窗看過 VPS 詳表拍板;屆時只需在 cron 那行加 `NEST_EXTRACTOR_MODEL=claude-sonnet-5`。

---

## 小案②:審核台 Owner 手動修正入口(已上線)

硬規則落實:**修正必產生 correction event 留證,絕不無痕直改 State。**

### 變更點(三層)
1. **nest-console**(`/srv/nest-memory/bin/console_service.py`,nestmemory 獨占寫入):
   新增 `POST /corrections` → `correct_state()`:
   - 驗 subject 在 Registry 且 active;value ≤500 字、note ≤300 字;secret 掃描沿用 extractor 同一 regex
   - 同一交易內:寫一筆 `extraction_batches`(model=`owner_console`,
     prompt_version=`console_correction_v1`,留痕)→ 寫 events
     (`event_type=correction`,`authority=owner_correction`,`confidence=high`,
     value_before=修正前 state 值)→ **用官方 `projection.project()` 全量重算 state**
     (與夜間投影同一套代碼,state 永遠是 events 的投影,不是被手改的)
   - 同秒同值重複送出→擋下;每次呼叫(成功/失敗)都落 `console_audit`
2. **backend 過橋**(`chatnest-next/backend/app/main.py`):
   `POST /api/v2/console/corrections`,pydantic 驗形 + owner 認證 + CSRF,純代理不碰 DB。
3. **前端檔案室 UI**(`nestConsole.tsx` + `api.ts` + `styles.css`):
   現況登記每列加「修正」鈕 → sheet 內改值+填原因(可留空)→「登記修正」;
   文案明示「會留一筆糯糯糾正的紀錄,不是偷偷改」。vite build 通過,dist 已部署。

### 驗證
- 單元測試(生產庫拷貝上跑,已清理):修正後 event/batch 各 +1、
  state 投影跟上且 authority=`owner_correction`;重複送出/不存在 subject/空值均正確擋下。
- 服務層:`nest-console` 重啟後 `/health` ok,`/corrections` 對不存在 subject 回 404+中文錯誤;
  backend 重啟後新端點掛上(未帶認證回 401 如預期)。兩服務均 active。

### 順帶發現(給規劃窗)
生產 state 有一筆現成髒資料:`chatnest.active_frontend`(聊天前端)目前被投影成
「頭像裝飾: H09狗耳…」——弱權威事件蓋錯了主題。這正是修正入口的第一個實戰用例,
建議糯糯開審核台直接修掉,順便走一遍新流程。

---

## 檔案清單(VPS)
- 改:`/srv/nest-memory/bin/extractor.py`(retry+model 覆寫)、
  `/srv/nest-memory/bin/console_service.py`(corrections)、
  `chatnest-next/backend/app/main.py`(過橋)、
  `chatnest-next/frontend/src/{nestConsole.tsx,api.ts,styles.css}`(UI)
- 新:`/srv/nest-memory/bin/ab_regression.py`
- 報告:`/srv/nest-memory/health/ab_regression_20260830_0701.{md,json}`(不出島)
- 備份:各檔同目錄 `.bak-swapexp-*` / `.bak-correction-*`
