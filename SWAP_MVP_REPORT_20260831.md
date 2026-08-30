# Swap MVP 交付報告(實驗步驟 2)

2026-08-31|規劃窗放行後實作。**已建成並在拋棄式會話上完整驗證一次真實換窗;
生產側以 SHADOW 模式上線(只記決策不動手),等離場結算(步驟 3)/規劃窗裁定後轉正。**

## 架構:真的長在現成機制上

換窗指標本來就存在——bridge store 的 `conversations.latest_session_id`,每輪
`begin_turn` 讀它 resume、`complete_turn` 寫它。Swap 只加了兩件東西:

1. **bridge `/api/chat` 新旗子 `fresh_session`**(約 6 行):本輪不 resume、
   先 invalidate warm actor(冷啟必要,否則 warm client 沿用舊 session 令
   resume=None 失效——測試抓到的真 bug)。成功時 `complete_turn` 照常把指標
   翻到新 session=**NEW GOOD**;失敗指標不動=**last-good 免費送**。
2. **`scripts/swap_runner.py`**(獨立程序,cron */10):觸發判定→打包→ping→驗證→
   manifest;驗證不過就把指標滾回舊窗。backend 完全不用改
   (它經 `session` 事件自然跟上 upstream_session_id)。

## 規格點落實對照(小踢十點中屬 MVP 的)

| 規格 | 落實 |
|---|---|
| 3. margin 程式算 | trigger = context_max − 30k(成本總帳核准值);runner 讀 turn_usage 判定,模型完全不參與 |
| 1. token budget 打包/閉合單元 | 近段原文由新到舊裝閉合單元(user+assistant 配對)至 20k chars 預算,整單元進出 |
| 2. Tool Primer 原子性 | 最後 2 個 assistant 回合附完整 tool_use→tool_result(內容可截斷,回合絕不切半) |
| 4. atomic handoff/last-good | 指標翻轉=complete_turn(成功才發生);驗證不過→回滾指標;舊 transcript 永不刪 |
| 5. 逃生門+留痕 | runner 失敗不影響 CLI 原生 auto-compact;每次成敗都落 manifest+health jsonl+推播 |
| 6. context manifest | 每次換窗寫 `data/swap_manifests/swap_<ts>.json`:birth_snapshot_hash、組裝清單(tail chars/units/tool rounds/model)、觸發數值、probe 回應 |
| 9. ping 驗證+失敗清理 | 驗:回應非空、新 session id 合法且≠舊、transcript 檔存在且非空;不過→回滾(=清理);guardian 併發由 bridge chat_lock/actor busy 天然擋 |

人格+State+AM wakeup 不用打包——bridge 每輪重建 system prompt 本來就帶
(這正是「bridge 現成機制上長」最省的一刀);Swap 只需補「近段原文+Tool Primer」。

## 實測紀錄(拋棄式 conv `2a35ab8b`,已刪)

1. 種話題錨點「章魚燒攤車的營運計畫」(2 輪)
2. `swap_runner --force` 三連跑,前兩次驗證器逮到真 bug:
   - transcript 路徑錯(bridge HOME 在 `/srv/chatnest-next/data/version-bridge/home`)→ **回滾路徑實際執行過**
   - warm actor 令 resume=None 失效(session id 未變)→ 加 invalidate 修復
3. 第三次全綠:舊 `dac42f74` → 新 `c06fb78a`,指標翻轉,
   **probe 回應:「讀到了!近段原文顯示這是 Swap-MVP 測試會話,話題錨點是『章魚燒攤車的營運計畫』」**
4. 換窗後普通一輪:resume 到新 session,答出話題——換窗對後續輪次不可見 ✓

## 生產姿態(當前)

- cron `*/10` 已裝,**SHADOW 模式**:context ≥ 170k 時只記 `shadow_would_swap`
  (順便實測觸發頻率,驗證成本總帳的 0.63 次/天投影),不執行。
- 觸發同時要求距上一輪 ≥90s(不插話)。
- **轉正條件(規劃窗裁定)**:離場結算(步驟 3)建成——目前換窗會硬丟預算外的
  中期段落,這正是補刀 B 說的唯一真實退步;或規劃窗評估後決定先開。
  轉正=cron 那行加 `SWAP_ENABLED=1`,一個環境變數。
- 手動演練:`swap_runner.py --force --conv <id>`(用拋棄式 conv,勿對 canonical)。

## 已知邊界(誠實聲明)

- 驗證是機械項+probe 留檔人審;人格/State 的深度驗證屬步驟 5(continuity probe
  進 golden)與步驟 6(糯糯盲測),MVP 不越權提前宣稱。
- 近段原文用 bridge store 訊息(模型實際看過的 prompt 渲染),與 CLI transcript
  可能有格式差;MVP 接受,步驟 5 regression 再校。
- manifest 未記工具 schema 尺寸(turn_usage 沒有此欄);基線調查已建議補。

## 檔案(絕對路徑,供未來窗口定位)
- 改:`/srv/chatnest-next/runtime/version-bridge-app/app/main.py`
  (**fresh_session 旗子在這裡,不在 claude.py**:`ChatBody.fresh_session` 欄位
  +`/api/chat` handler 內 `resume_id=None`+`invalidate(conv_id)` 三處;bak-swapmvp-*)
- 新:`/root/chatnest-next/scripts/swap_runner.py`、
  `/root/chatnest-next/data/swap_manifests/`、
  `/root/chatnest-next/data/swap_health.jsonl`、root crontab 一行(shadow)
- 指標所在:`/srv/chatnest-next/data/version-bridge/conversations.db` 的
  `conversations.latest_session_id`(注意不是 `/srv/chatnest/full-stack/` 那顆舊拷貝)
- transcripts:`/srv/chatnest-next/data/version-bridge/home/.claude/projects/-srv-chatnest-full-stack/`
