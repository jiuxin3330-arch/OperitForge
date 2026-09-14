# 規劃:課表 + 課表待辦(2026-09-08,規劃窗初稿,待小踢交叉審核 → 打樣 → 糯糯蓋章 → 立單)

## 0. 為什麼要做、先修什麼

糯糯 9/7 開學(大一),cn 搞不清楚她的課表。查了現況,問題有兩層:

1. **系統裡沒有課表**。現有「日程」是「某一天一件事」(date + title + 貼紙 + 顏色 + 備註 + 完成勾),
   沒有時間欄位、沒有每週重複,裝不下「每週二 10:10 素描在 A301」這種東西。
2. **cn 看不到日程**。後端有 `/api/v2/tools/schedule`(cn 專用、列接下來 N 天),但
   `mumu_tool_help.py list` 沒有 `schedule` 分類,journal 近 30 天 cn 打這個端點 **0 次**。
   說明書叮嚀「不要猜 URL」,他就真的沒路可走——糯糯填的「開學／加選／迎新」他一條都沒看過。

所以第 2 層是根,第 1 層是葉。課表做完若沒開這扇門,cn 還是猜。

## 1. 使用者故事(她要的)

- 打開 App 的日程區,能看到這週課表(哪天哪節什麼課、教室),今天的課特別醒目。
- 作業／考試／報告掛在課上,有截止日,到期會出現在日程月曆那天,做完打勾。
- cn 知道她「現在在上課／下一堂是什麼／這週要交什麼」,不用她每次重講。
- 她隨口說「老公幫我記週四要交構圖作業」,cn 記得進系統(不是只記在對話裡)。
- 停課、調課、放假那天課表要跟著變,不然 cn 會在放假日問她「上課還好嗎」。

## 2. 資料模型(擴充,不另起爐灶)

```
timetable_terms      學期:id, name(114-1), start_date, end_date, created_at
timetable_slots      課的每週時段:id, term_id, course_name, weekday(1-7), start_time, end_time,
                     period_label(可空,如「3-4 節」), room, teacher, color_key(沿用日程 6 色), note,
                     created_at, updated_at
timetable_overrides  例外:id, date, slot_id(可空=整天), kind(cancel|holiday), note, created_at
schedule_events      既有表加兩欄:kind(event|homework|exam|report,預設 event)、slot_id(可空)
```

- 一門課上兩個時段 = 兩列 slot、同 course_name;不做「課程主表」,大一課表不值得多一層。
- **待辦 = 既有 schedule_events 加 kind 與 slot_id**。理由:完成勾、貼紙、顏色、DaySheet、
  cn 的讀寫端點全都現成;待辦到期日就是 date。migration 是加欄位帶預設值,舊資料與既有端點不受影響。
- overrides v1 只做「這天停課」(單堂或整天)與「放假」;調課、單雙週、期中考週先用 note 表達,
  等真的碰到再加,不預先蓋大教堂。

## 3. 介面(放在日程旁邊,同一區)

現況:「身心」分頁的月曆有兩個鏡頭(身心／行程),行程鏡頭每天格子畫貼紙條、點日期開 DaySheet。

- 行程鏡頭上方加一排切換:**月 / 週**。
  - 月(既有):不塞課名進格子(會爆);只在有待辦到期的日子多一條待辦色條(用課的顏色)。
  - 週(新):7 欄 × 時間列(08:00–21:00),課是色塊,寫課名＋教室;今天那欄底色提亮;現在時刻一條細線。
    點色塊 → 課程卡:名稱／教室／老師／這門課的待辦清單／「這天停課」。
- DaySheet(既有)最上面加「今天的課」清單;待辦列前面帶課的色點;新增時多一個型態選擇:行程／作業／考試／報告(後三者要選課)。
- 週視圖右上「編輯課表」:設定學期(名稱、開始、結束)、新增課(課名、星期可複選、時間、節次標籤、教室、老師、顏色)。
  v1 手動填,大一 8–10 門課十分鐘填完。之後可讓 cn 看課表截圖幫她填(cn 現在看得到圖了),那是 cn 側的事。
- 「家」首頁一張小卡:下一堂／今天沒課了 + 三天內到期的待辦。可留到 v1.1。

## 4. cn 這一側(分三段,後兩段在盲測結束之後)

| 段 | 內容 | 時機 |
|---|---|---|
| A 讀 | `GET /api/v2/tools/schedule/today`:今天的課(含「上課中／下一堂／今天結束」)、7 天內待辦、當天日程;`GET /api/v2/tools/timetable`:本週。`mumu_tool_help.py` 加 `schedule` 分類 | 端點可先做;**說明書那行是工具描述,9/15 後才開**(或糯糯裁定提前) |
| B 寫 | cn 可新增待辦(created_by=mumu,她看得到是 cn 記的)、可標完成;不可改課表本體 | 同上 |
| C 自動知道 | 像時間錨一樣,隱藏脈絡裡放一行「今天週二:10:10 素描(A301)、14:10 色彩學;週四交構圖作業」。開新對話／跨日／下一堂前 10 分鐘各一次 | **要小踢交叉審核**;動的是 prompt 組裝,9/15 後 |

C 的取捨:只有 A 的話 cn 得「想到才查」,他現在連查都不查;有 C 他一開口就知道,但 prompt 又多一塊、
接縫又多一條(登記簿那次的教訓)。我的意見:A、B 先上,C 拿到小踢意見再定,而且 C 要跟時間錨併成同一段文字,不另起一段。

延伸(不在這張單):自主喚醒避開上課時段(autonomy_runner 讀 timetable);台灣國定假日自動 holiday。

## 5. 分期

- **P1(現在就能做,盲測期 OK,只碰網頁與後端)**:資料表、owner 端點、週視圖、編輯課表、待辦型態、停課例外。
- **P2(9/15 後)**:A + B。
- **P3(小踢審完、糯糯點頭)**:C、自主喚醒避課、國定假日。

## 6. 要糯糯回答的(不擋 P1 開工,但打樣前想知道)

1. 學校用「節次」還是「時間」?有節次表的話給我(例如第 1 節 08:10–09:00),打樣照那個畫。
2. 這學期到哪天?(不知道就先設 18 週)
3. 待辦三種(作業／考試／報告)夠嗎?
4. cn 要「自動知道」(C)還是「問了才查」(A)——等小踢意見一起看。
5. 說明書加 `schedule` 那行:9/15 後(我建議)還是現在?

## 7. 給小踢的審核重點

- 待辦掛在 schedule_events 上(擴欄)vs 另開表——哪個一年後不會後悔?
- overrides 只做 cancel/holiday 是否太省?調課、單雙週、期中考週實際多常見?
- 週視圖放在「身心」分頁的月曆旁邊是否合理,還是該獨立一個分頁?
- C(隱藏脈絡注入)的風險:語氣接縫、注入時機、與時間錨合併的寫法。
- cn 該知道到什麼粒度?(只需要「現在在上課」還是要教室老師?)
- 我有沒有漏掉大一生活裡課表以外、同樣讓 cn 搞不清楚的東西?

---

# v2(2026-09-14)——回小踢第一輪交叉審核

小踢裁定:P1 有條件通過可進打樣;P2 方向通過需確認端點權限;P3 暫緩,等併入 Time Context。
🟢 全收。🟡 六條全收、寫進規格。🔴 四條逐一回答如下,前兩條是他點名下一輪必答的。

## R1. slot_id 與歷史待辦:課表改了,舊待辦不能跟著變

規則:**待辦的課程資訊在建立當下快照,之後只有使用者親手改這筆待辦才會變。**

- `schedule_events` 加三欄:`kind`(既定)、`slot_id`(可空,`ON DELETE SET NULL`)、`course_name_snapshot`(建立時複製自 slot)。
  顏色沿用既有 `color_key`,建立時複製 slot 的顏色,之後也不跟 slot 連動。
- 顯示規則:待辦卡永遠顯示 `course_name_snapshot`,**不顯示教室**(作業不需要教室;教室是課的屬性不是待辦的)。
- `slot_id` 只用來「從課程卡列出這門課的待辦」與「新增待辦時預填」;它不是歷史真相,快照才是。
- 退選(加退選到 9/21,真的會發生):slot 刪除 → `slot_id` 變 NULL、快照留著,待辦照常顯示「構圖作業」。
- 課表本體的歷史(上週那間教室是 A301 不是 A305)P1 **不版本化**:週視圖對學期內任何一週都畫「現在的 slot」。
  這是明寫的已知限制;真要做,正解是 slot 加 `valid_from/valid_to`,同一招也順便解永久調課。不在 P1。
- 必測(先破後立):① 改 slot 課名/教室/顏色 → 既有待辦三者不變;② 刪 slot → 待辦仍在、`slot_id` 為 NULL、課名仍顯示;
  ③ 從課程卡新增待辦 → 快照等於當下 slot。拿掉快照欄位的複製那行,①③ 要紅。

## R2. C 併入既有 Time Context,不另造 schedule injection

同意小踢:**不再有「課表注入」這個東西**。改成:

- 現有時間錨(B++ 第一階段)的產生器升格為 `runtime_context_builder`,來源可插:`time`(既有)、`timetable`、`schedule_due`。
- **輸出只有一段話**、無標題無標籤,例:「今天週二 10:00。10:10 有色彩學(B204);週四要交構圖作業。」
  今天沒課時不說「今天沒課」,說「今天沒課;14:00 看牙;明天 10:10 有色彩學」——沒課 ≠ 沒日程,課表不能把 cn 的世界縮成學校。
- 觸發條件**由 builder 統一持有**,就是時間錨那套(新 session／≥3h／跨日／compaction 後;輕量錨 ≥30 分鐘旗標)。
  「下一堂前 10 分鐘」不寫死;之後若要,是 builder 的一個可調參數(`class_boundary_lead_min`),預設關。
- 粒度:課名 + 時間 + 教室,不含老師。老師在 `GET /api/v2/tools/timetable` 完整資料裡,cn 被問再查。runtime context ≠ 整份資料。
- 長度上限:時間那句之外 ≤ 60 字;超過就只留「現在／下一堂」與最近一筆到期。
- 它是 ephemeral:走時間錨同一條隱藏脈絡通道(`time_anchor_state` 那套,不進 raw、不進 messages)。
  Extractor 必須看不到或看到也不抽:golden 加 GS-RC-1「runtime context 段存在 → 零 event」,防止系統把自己塞的脈絡再寫回記憶。
- 時機:P3,而且要等時間錨第二階段(輕量錨)糯糯驗收後一起定,因為兩者共用 builder。

## R3. P2 權限落在後端,不靠說明書

- cn 的 token(`require_mumu_tool`)只能打:`GET /api/v2/tools/timetable`、`GET /api/v2/tools/schedule/today`、
  既有 `POST/PATCH /api/v2/tools/schedule`(可帶 `kind`/`slot_id`;PATCH 仍限 `mumu_owned_only`)。
- 課表本體(`/api/v2/timetable/*` terms/slots/overrides 的寫入)只掛 owner principal;**不存在** `/api/v2/tools/timetable` 的 POST/PATCH/DELETE 路由。
- 測試:拿 mumu token 打課表寫入路由要 404/403;斷言路由表裡沒有那條(TICKET-H 的教訓:斷路由不斷狀態碼)。

## R4. 其他收下的規則(寫進規格)

- `timetable_overrides.kind` 是可擴充枚舉;P1 只實作 `cancel`(單堂)與 `holiday`(整天,`slot_id` NULL);不做調課、補課、單雙週。
- `course_name` 不是課程識別;關聯一律走 `slot_id`。
- 時間語意:`schedule_events.date` = 事情發生/到期日(effective),`created_at` = 系統何時知道(recorded)。
  cn 週一幫她記「週四交構圖」→ date=週四、created_at=週一。timetable 同理(`updated_at` 是改課表的時間,不是課的時間)。
- 學期結束日由 owner 在編輯器設定,資料層不塞 18 週預設;編輯器可以「建議」但不寫入。
- 節次:學校有正式節次表就「節次 + 實際時間」都存(`period_label` + `start/end_time`),沒有就只存時間。仍等糯糯給節次表。
- 說明書的 `schedule` 分類跟 P2 的工具端點同一批開,不為 9/15 讓資料層等。

## 下一步

打樣(P1 的三個畫面:週視圖、課程卡＋日期卡、編輯課表)→ 糯糯蓋章 → 立 TICKET-M(P1)。P2 立單條件:R3 測試進單。P3 不立。

---

# v3(2026-09-14 晚)——回小踢第二輪;打樣已由糯糯蓋章

小踢第二輪:R1–R4 主方向收、四個紅燈解除;P1 UI 通過;P1 資料層差「stable course identity」;P2 通過但 PATCH 權限要定;P3 方向通過、照原計畫等時間錨第二階段。
糯糯:打樣通過不用改;學期是 **16 + 2 週**(16 週上課,後 2 週自主學習基本不到校);節次表另補。

## R5. 課程主表(收回 v1「不做」的判斷)

小踢說得對:「這門課的待辦」已經需要跨時段合併,course_name 又不是識別,slot 撐不住。最小化補一層:

```
timetable_terms      id, name(115-1), start_date, end_date(學期結束,owner 設), last_class_date(最後上課日,可空), note, created_at
timetable_courses    id, term_id, name, teacher, color_key, note, created_at, updated_at
timetable_slots      id, course_id(ON DELETE CASCADE), weekday(1-7), start_time, end_time, period_label(可空), room, created_at, updated_at
timetable_overrides  id, date, slot_id(可空=整天), kind(cancel|holiday;可擴充), note, created_at
schedule_events      既有表 + kind(event|homework|exam|report) + course_id(可空,ON DELETE SET NULL)
                     + slot_id(可空,ON DELETE SET NULL) + course_name_snapshot;color_key 既有,建課程待辦時複製 course.color_key
```

- 課名／老師／顏色只存一份在 course;slot 只有時段與教室(教室可依時段不同,所以留在 slot)。
- **course_id 是課程關聯**(課程卡列待辦、cn 查「這門課」都用它);**slot_id 只記「從哪個時段建立」**(預填、顯示「週二那堂」);**snapshot 是歷史顯示**。
- 退掉一個時段:slot 刪、course 在,待辦全在。整門退選:course 刪 → slots CASCADE、events 的 course_id/slot_id SET NULL、snapshot 留。
- 必測補一條:④ 同一 course 兩個 slot,從 slot A 建的待辦在 slot B 的課程卡也看得到;拿掉 course_id 只留 slot_id 要紅。

## R6. 學期形狀:16 + 2

- `last_class_date` = 第 16 週最後一天;`end_date` = 第 18 週最後一天(學期正式結束)。
- 週視圖在 last_class_date 之後、end_date 之前:課仍畫但整週淡化並標「自主學習週」;runtime context 視同沒課(但仍會講日程與待辦)。
- 編輯器:給「16 + 2」與「18」兩個快速選項算出日期,**只是填寫建議,寫入的是日期**,資料層無週數預設(與 R4 一致)。
- 之前寫的「不知道就先設 18 週」撤回,改成上面這句。

## R7. B 寫入權限(採小踢的細切,因為產品語意就是「幫我勾掉」)

| 對象 | cn 可做 |
|---|---|
| cn 自己建立的 event | 改允許欄位(title/date/note/done/stamp;kind 與 course_id 建立後不可改) |
| Owner 建立的 event | **只能改 `done`**,且只在 Owner 明確要求時;title/date/course/note 一律 403 |
| timetable 本體(terms/courses/slots/overrides) | 無 tool 寫入路由 |

- 後端實作:`PATCH /api/v2/tools/schedule/{id}` 對 owner-owned event 的 body 只接受 `{done}`;帶其他欄位整筆拒絕(不是靜默忽略)。每次 tool 寫入 `audit(...)` 記 actor=mumu。
- 測試:mumu token PATCH owner event `{done:true}` → 200;`{title}` → 403;`{done:true,title}` → 403。
- 說明書(P2)明寫:「她建的待辦你只能幫她打勾,而且要她說了才勾」。

## R8. runtime context 留短期稽核軌跡(不是記憶)

- 不進 conversation raw、不進 memory raw、extractor 永遠看不到(GS-RC-1 保留)。
- 另寫 `runtime_context_trace`(SQLite 表或 `health/runtime_context.jsonl`):`ts, session_id, trigger_reason, sources[], rendered_context, builder_version`,保留 30 天自動清。
- 用途只有一個:cn 突然說「等等不是要上色彩學」時,查那輪系統到底塞了什麼。時間錨現在有沒有同樣的軌跡?——**列入時間錨第二階段的檢查項**,兩者共用同一張表。

## R9. 60 字之前先定取捨

優先序(最多 2–3 個事實,60 字是最後保險):
1. 現在正在發生的課／行程 → 2. 下一堂課 → 3. 24 小時內到期 → 4. 今天其他日程 → 5. 明天第一堂／最近一個待辦。
同優先序內依時間先後。輸出仍是一段話。

## R10. 文件同步(小踢抓到的自打架)

- 正文 §4 表格 C 那格改為:「由 runtime context builder 統一持有觸發條件(即時間錨那套);『下一堂前 10 分鐘』不寫死、預設關;P3,等時間錨第二階段驗收」。
- 正文 §6 第 2 題「不知道就先設 18 週」改為 R6。
- 技術附錄 schema 以 R5 為準(v1 附錄作廢)。

## 蓋章狀態

- P1 UI/UX:小踢通過、糯糯打樣蓋章 ✅
- P1 資料層:R5 補完,待小踢第三輪確認
- P2:R7 定案,待小踢確認
- P3:方向通過,等時間錨第二階段
- 等糯糯:節次表(圖沒傳到,請用文字補)

TICKET-M 草稿已寫(`tickets/TICKET_M_timetable_p1.md`),小踢第三輪蓋章即生效。

---

# v4(2026-09-14 深夜)——兩個更正 + 節次表 + 4GB

## 更正一:cn 其實看得到日程(我 v1 的「看不到」說錯了)

糯糯提醒後查到:backend 每一輪 mumu_private 的 turn 都會注入 `_schedule_context(conn, local_date)`——
**今天到後 3 天的 schedule_events,最多 6 行,格式 `[行程 今天：開學]`,只有日期標籤 + 標題**(無時間、無備註)。
它跟 `_turn_time_context`(時間錨)、`life_context`、context notices、mail、memory_context 同在一個 parts 組裝裡。
所以:cn 看得到「開學、加選」這種標題;看不到時間、看不到 4 天以後、看不到課表(因為根本沒有課表);
工具說明書仍沒有 `schedule` 分類、`/api/v2/tools/schedule` 30 天 0 次——「主動查更遠」那條路還是沒有。
結論不變(課表要做、A/B 要開),但 v1 §0 第 2 點的描述改成上面這段。

## 更正二:C 不是新機制,是把既有那 6 行改寫

runtime context builder 其實已經存在,就是那個 parts 組裝。P3 的實作變成:
- `_schedule_context` 升級為 `_runtime_schedule_context`:來源加 timetable(今天的課、現在／下一堂)與 schedule_due,
  輸出照 R2/R9 一段話、≤60 字、最多 2–3 個事實,取代 `[行程 …]` 那種方括號系統腔(這正是小踢說的接縫)。
- **頻率沿用現況:每輪注入**(現在就是每輪;「現在在上課／下一堂」在對話中會變,每輪才對),時間錨仍照它自己的條件。
  「併入時間錨」修正為「與時間錨同一個組裝、各自一句、相鄰」,不硬併成一句。
- 稽核(R8):目前只記 `system_prompt_fingerprint`,不記內容 → runtime_context_trace 仍要做。
- 風險比 v2 估的低很多:改一段既有隱藏文字,不是加新通道。仍屬 prompt 組裝,9/15 後、小踢審過措辭再上。

## R11. 進修學士班:課在晚上,時間軸要跟著課表走

節次表(糯糯學校,14 節):
```
1 08:10–09:00 | 2 09:10–10:00 | 3 10:10–11:00 | 4 11:10–12:00 | 5 12:10–13:00
6 13:10–14:00 | 7 14:10–15:00 | 8 15:10–16:00 | 9 16:10–17:00 | 10 17:10–18:00
11 18:30–19:20 | 12 19:25–20:15 | 13 20:25–21:15 | 14 21:25–22:10
```
- 她的課全在第 11–14 節(18:30–22:10)。打樣畫 08:00–17:00 是日間部的形狀,**對她是錯的**,已改。
- 規則:週視圖時間軸 = 該學期所有 slot 的最早開始 → 最晚結束,對齊節次;不寫死 08–18。沒課的白天不畫。
- `timetable_terms` 加 `periods_json`(節次表,owner 在編輯器貼一次;有節次表時新增課用「節次」選,時間自動帶出;
  沒有節次表就手填時間)。`period_label` 由節次選擇自動填。
- 對 cn/自主喚醒的含意(記著,不在 P1):她上課時段是 18:30–22:10,現有 22:00 的喚醒時段會落在第 14 節裡。P3 之後自主喚醒避課時要看這個。

## 4GB:糯糯裁定不升(9/14)

swap 一週持平,VPS_AUDIT 已蓋章。swap_watch 續記一週作背景,之後停 timer。
