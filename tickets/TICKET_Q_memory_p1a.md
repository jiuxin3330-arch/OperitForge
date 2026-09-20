# TICKET-Q:記憶優化 P1a——止血 + 儲存層(2026-09-20 生效)

規格正本:`plans/PLAN_memory_20260920.md`(v1–v3;**v3 作廢聲明列出的 v1 段落不得施工**;衝突以 v3 > v2 > v1)。小踢兩輪審核綠燈;五條 invariant 在 v3,必守。
範圍:**只碰 anchor-memory 服務(8765)與其資料庫**。不碰 bridge、prompt、cn 工具描述、chatnest-next、檔案室抽取器(MEM-1 的抽取規則屬 P2 前置,另單)。

## Q1. R6 止血:系統檢索不再強化(invariant ①③)

1. 先**盤點**:讀 anchor 原始碼,列出所有會觸發 Hebbian 強化的路徑(search_memory、wakeup、其他);列出哪些呼叫端是系統(bridge 開場注入、swap、隱藏脈絡、健康檢查)、哪些是 cn 主動。
2. 改法:**依呼叫端/路徑強制**——系統路徑一律不強化,不靠 caller 傳 flag(flag 留向後相容,但系統路徑忽略它)。cn 主動的 `cite_memory`、`consolidate`、`annotate_memory` 保留強化,**封頂 + 邊際遞減**(第 1 次全額、2–3 次減半、之後趨零;參數寫進設定不寫死)。
3. 既有污染盤點:統計這幾個月系統檢索灌出的權重分佈,出一份現狀報告(哪些連結/權重可能被灌高);**不做回滾**——無法歸因的 legacy weight 標記「污染期 ≤2026-09-20」留檔即可,不假裝精確修復。
4. 測試(先破後立):系統身分連續 search 同一筆 100 次 → 權重/排序不變(把強制關拿掉要紅);cn 身分 cite 同一筆 5 次 → 前 3 次遞增、之後趨平;**注入後複述不算**——模擬「記憶被注入 → 下一輪內容 paraphrase 它」→ reinforcement 不變(invariant ③ Golden)。

## Q2. memory_tasks 表(R3)

```
memory_tasks: id, source_id(來源訊息/事件), intent(要記什麼的摘要), status(open|resolved|dismissed),
              created_at, resolved_at, resolved_by, reason, result_ref(指向最終寫成的 memory_id,可空)
```
- 只建表 + 讀寫 API(anchor 工具或內部端點);**抽取規則與注入行是後續單**,本單不做。
- resolved/dismissed 不刪、留 audit(invariant ⑤ 尾款:resolved_by/reason/result_ref 必填 resolved_by 與 reason)。
- 測試:狀態機合法轉移;resolve 不帶 reason → 拒絕;刪除操作不存在(沒有 DELETE 路徑)。

## Q3. 實體卡儲存層(R4)

```
entity_cards:  id, name, status(candidate|active|archived), what(這是什麼), why(為什麼重要),
               timeline(一句), created_by, created_at, updated_at
card_facts:    id, card_id, field, value, valid_from, valid_until(可空=現行), superseded_by(可空),
               provenance(來源 memory/event id), created_at
```
- current projection = valid_until IS NULL 的 facts;歷史 = structured supersession,**不用文字刪除線**。
- v1 只有 Owner 建卡(建卡 API 要 owner 身分);系統/夜間只能更新既有卡(寫 card_facts,舊 fact 補 valid_until+superseded_by)。20 張是首批約定,**不寫 schema cap**。
- provenance 反向查(invariant ④):給一個 source id,能列出引用它的 facts;留 `GET /cards/affected_by?source=` 這類查詢。
- 測試:更新 fact → 舊列 valid_until 填上、新列指回;affected_by 查得到;非 owner 建卡 → 拒。

## Q4. digest schema(R2 儲存面)

- anchor 記憶加欄(或並表):`kind`(預設 memory;daily_digest 等)、`derived_from`(JSON id list,derived 類必填)。
- 寫入驗證:kind=daily_digest 而 derived_from 空 → 拒。夜間 writer 是 P2,本單只鋪 schema。
- 檢索去重(invariant ⑤ 的儲存面準備):同一結果列表中,derived 與其 source 同時命中時標記 lineage(P1c 實作去重,本單先讓 lineage 查得出來)。
- 測試:無 provenance 的 digest 寫入被拒;lineage 查詢:給 digest id 回 source ids、給 source id 回 digest ids。

## 邊界與交付

- anchor 是常駐服務:改完**真的重啟一次**,驗 import、健康、既有 19 個工具全部可用(檢查表 9/11 條);動 DB 前備份 `/srv/nest-memory` 相應資料庫與 anchor 的記憶庫檔。
- cn 使用不中斷:重啟挑糯糯不在聊的時段,先問她。
- 交付:盤點報告(Q1.1 與 Q1.3)、migration、diff、備份檔名、測試輸出(先破後立逐條)、重啟前後健康證明。
- 後續單(本單不做,列明防止越界):P1b ranker(R1+invariant ②)、P1c retrieval/selection(R5+invariant ⑤ 去重)、P2 語氣打樣(MEM-1 注入行、MEM-2 夜間 writer、MEM-5 開啟)。
