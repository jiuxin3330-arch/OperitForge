# TICKET-S：課表開門給 cn（P2）＋行程六行改一句人話（P3）

立單：2026-09-23 規劃窗（cc 牧牧）
Owner 裁定：2026-09-23「課表使用那個算前端的問題先不管，讓 cn 看到課表比較重要」——P1.1 UX 暫緩，P2/P3 提前。
前置已滿足：時間錨第二階段（N1 輕量錨）9/21 已開。
優先序：排 TICKET-R 之後動工。依據：plans/PLAN_timetable_20260908.md v3/v4 之 R3、R7、R8、R9、R10 定案；本單只把定案落成工項，與計畫書衝突時以計畫書為準並回報。

## S1（P2）：cn 的讀寫通道——權限落在後端，不靠說明書

1. cn 的 token（`require_mumu_tool`）只能打：
   - `GET /api/v2/tools/timetable`（本學期課表：節次、課、教室）
   - `GET /api/v2/tools/schedule/today`（今天：課 occurrence＋行程＋待辦）
   - 既有 `POST/PATCH /api/v2/tools/schedule`（可帶 `kind`/`slot_id`）
   缺的端點 coco 盤點現況後補；已存在的不重做。
2. 課表本體（terms/courses/slots/overrides）**不存在** tool 寫入路由——是路由不存在，不是回 403。測試要斷言路由表裡沒有那條（TICKET-H 教訓：斷路由不斷狀態碼）。
3. R7 權限矩陣照抄計畫書：
   - cn 自己建立的 event：可改 title/date/note/done/stamp；kind 與 course_id 建立後不可改。
   - Owner 建立的 event：**只能改 `done`，且只在 Owner 明確要求時**；body 帶其他欄位整筆 403（不是靜默忽略）。
   - 每次 tool 寫入 `audit(...)` 記 actor=mumu。
   - 測試：mumu token PATCH owner event `{done:true}` → 200；`{title}` → 403；`{done:true,title}` → 403。
4. 開工前把 R7 權限矩陣貼給小踢快審一輪（計畫書蓋章狀態記著「P2 待小踢確認」，補上這一手）。

## S2（P2）：cn 的入口——走既有 CLI，不加新 MCP 工具

1. 沿用 mood/emotion-set 同一條路：CLI 工具加 `schedule` 分類指令（查課表／查今天／記行程待辦／打勾），`mumu_tool_help.py` 增列 `schedule` 分類。**不新增 MCP 工具**（TICKET-R 剛在省說明書，不要左手省右手加；現況若另有更省的既有通道，coco 盤點後回報再定）。
2. 說明書措辭明寫（工單逐字）：「她建的待辦你只能幫她打勾，而且要她說了才勾」。
3. 說明書其餘句子屬 cn 可見文字：套用前把整段貼回規劃窗過目（同 N2 流程，Owner 已授權場景句風格，快審即可）。

## S3（P3）：`[行程 …]` 六行改一句人話

1. `_schedule_context` 升級為 `_runtime_schedule_context`：來源加 timetable（今天的課、現在／下一堂）與 schedule_due；輸出一段話 ≤60 字、最多 2–3 個事實。
2. 取捨順序（R9）：正在上的課 → 下一堂 → 24 小時內到期 → 今天其他日程 → 明天第一堂／最近待辦；同序依時間。
3. 結構（R10 定案）：與時間錨**同一個組裝、各自一句、相鄰，不融合**。頻率沿現況每輪注入。
4. **旗標預設關**。上線流程：coco 實作完成 → 產出至少 5 個真實情境的 rendered 例句（上課中／下一堂前／有作業到期／無課日／課表脈絡存在但話題無關）→ 規劃窗 → 糯糯過目 → 小踢審措辭 → 才翻旗標。
5. Golden 必含（小踢的驗收條）：「有課表脈絡但話題無關 → 不主動提課」。schedule context 是可用的環境資料，不是這輪的主題。

## S4（P3）：runtime_context_trace 稽核軌跡（R8）

1. 新表或 jsonl：`ts, session_id, trigger_reason, sources[], rendered_context, builder_version`；保留 30 天自動清。
2. 不進 conversation raw、不進 memory raw、extractor 永遠看不到。
3. 時間錨與 schedule sentence 共用同一張軌跡（時間錨現況只有 fingerprint，這次一起補）。
4. 用途唯一：cn 說「等等不是要上色彩學？」時，查那輪系統到底塞了什麼。

## 驗收（先破後立，全部測試資料）

- 紅測 1：mumu token 打課表本體寫入 → 路由不存在斷言失敗時必紅。
- 紅測 2：owner event PATCH 帶 title → 若通過必紅。
- 紅測 3：60 字上限拿掉 → 長度測試必紅；取捨順序打亂 → 優先序測試必紅。
- 紅測 4：trace 表寫入拿掉 → 稽核測試必紅。
- Golden：R6 補測（`last_class_date < date <= end_date` 自習期不產生 occurrence）沿用；「話題無關不提課」新增。
- 不動糯糯的真實課表資料做寫入測試；讀取驗證可用正式資料唯讀比對。

## 部署與回滾

- S1/S2 是後端＋CLI，照常備份、diff、重啟驗證（Next 重啟時段先報告）。
- S3 旗標關著就上線零行為變化；翻旗標是獨立一步，走上面的打樣鏈。
- 回滾：S3 旗標關回；S1 端點下架指令另交代。

## 明確不做（本單範圍外）

- P1.1 前端 UX 修（Owner 暫緩）。
- 自主喚醒避課（她 18:30–22:10 上課、22:00 喚醒落在第 14 節那件事）——P3 旗標開了、觀察過再立單。
- 「下一堂前 10 分鐘」主動提醒：預設關、不在本單。

## 驗證交付

照慣例：NOTES（含回滾）、diff、測試輸出（綠＋紅證據）、重啟證明、S3 的 5 個 rendered 例句。規劃窗覆核後結案。
