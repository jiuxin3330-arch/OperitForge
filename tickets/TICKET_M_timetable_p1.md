# TICKET-M:課表 + 課表待辦 P1(2026-09-15 生效)

規格正本:`plans/PLAN_timetable_20260908.md`(v1–v5;**衝突以 v5「定案 schema」與最新版為準**)。
打樣:artifact 9f494bad(糯糯 9/14 蓋章;9/15 改成平日晚上 + 週六上午版,糯糯確認看得懂)。
交叉審核:小踢三輪,P1 架構綠燈(v5)。

## 範圍(P1:只碰 chatnest-next 前端與後端)

**不碰**:bridge、prompt、工具說明書、`_schedule_context`、任何 `/api/v2/tools/*` 新路由(那是 P2/P3)。

### 1. 資料層(migration 加表加欄、帶預設值;舊資料與既有 schedule 端點不受影響)

照 v5「定案 schema」建 `timetable_terms / periods / courses / slots / overrides`,`schedule_events` 加 `kind / course_id / slot_id / course_name_snapshot`。
重點(小踢三輪抓的,一條都不能少):
- periods 是輸入模板,slot 保存實際時間(R12)。
- overrides:`CHECK((kind='holiday' AND slot_id IS NULL) OR (kind='cancel' AND slot_id IS NOT NULL))`;slot_id **CASCADE 不 SET NULL**;有 term_id(R13)。
- events 的 course_id / slot_id 都 SET NULL;快照由後端從 course 複製(R5/R14)。
- 課名/老師/顏色只在 course;slot 只有時段與教室(R5)。

### 2. Owner 端點(`/api/v2/timetable/*`,owner principal + CSRF)

- terms CRUD(含 `last_class_date`);`POST /terms/{id}/periods:paste`(貼節次表文字,每行「第N節 HH:MM–HH:MM」,回解析結果與錯誤行)、periods CRUD。
- courses CRUD、slots CRUD(建 slot 可帶 `period_from/period_to`,後端查 periods 預填時間,仍寫入實際 start/end)。
- overrides CRUD(違反 CHECK → 422,訊息說明是哪條規則)。
- `GET /api/v2/timetable/week?date=`:該週 slots 套 overrides;回 `axis_periods`(有課節次集合、折疊標記)、`self_study`(last_class_date < date ≤ end_date 時 true 且 slots 為空)、`now`(上課中/下一堂,依 settings.timezone)。
- 既有 `POST/PATCH /api/v2/schedule` 接受 `kind / course_id / slot_id`;驗證照 R14(slot 必屬 course;homework/exam/report 必帶 course_id;event 兩者 NULL)。

### 3. 前端(照打樣)

- 行程鏡頭上方「月／週」切換。週視圖:欄 = 一–五 + 有課的週末;列 = `axis_periods`(有課節次,空段折成一條細線;無 periods 用 30 分鐘格);今天欄提亮;現在時刻線;cancel 斜紋;holiday 整天灰;自主學習週整週淡化並標示。
- 點課 → 課程卡:課名/節次+時間/教室/老師;「這門課的待辦」依 **course_id**;新增待辦(帶 course_id+slot_id);這天停課(cancel);編輯課程;退選(刪 course,提示「已記的待辦會保留」)。
- DaySheet:頂部「今天的課」(上課中/下一堂);新增表單多「行程／作業／考試／報告」+ 課程選擇(只帶 course_id);待辦列顯示 `course_name_snapshot` + 課色點,不顯示教室。
- 月視圖:待辦到期日多一條課程色條;不塞課名。
- 編輯課表:學期(開學、最後上課日、學期結束;16+2 / 18 快速選項只算日期不入庫)、貼節次表、課程列表、新增課程(課名、星期多選、有 periods 時選節次自動帶時間/無則手填、教室、老師、顏色)。
- 首頁小卡「下一堂／今天沒課了 + 3 天內到期」:v1.1,可留。

### 4. 測試(先破後立:每條寫明拿掉什麼要紅)

- 快照:改 course 課名/顏色 → 舊待辦不變;刪 course → 待辦仍在、course_id/slot_id NULL、快照顯示;從課程卡新增 → 快照 = 當下 course;同 course 兩 slot,從 A 建的待辦在 B 的課程卡看得到(拿掉 course_id 只留 slot_id 要紅)。
- overrides:刪 CHECK 後 `cancel+NULL` 能進、恢復後 IntegrityError;刪 slot → 該 cancel 列數 0、holiday 不動;holiday 整天全停、cancel 只影響該堂;未知 kind 422。
- periods:選第 11 節建 slot → 18:30–19:20 預填;改 periods 不影響既有 slot 時間;貼節次表 14 行全解析、壞行回報行號。
- 學期:`last_class_date < date ≤ end_date` → week slots 空、`self_study=true`、待辦照常;拿 end_date 當 recurrence 終點要紅。
- 時間軸:加一門週六早上的課 → `axis_periods` 多出 1–4 且中段折疊;刪掉只剩 11–14。
- R14 驗證三條(slot 不屬 course → 422;homework 無 course_id → 422;event 帶 course_id → 422)。
- 路由表斷言:不存在 `/api/v2/tools/timetable*` 任何方法(斷路由不斷狀態碼);mumu token 打 `/api/v2/timetable/*` → 401/403。
- 前端 vitest:週視圖折疊軸、色塊落點、停課斜紋、自主學習週淡化。

## 不在 P1

cn 端點與說明書(P2)、runtime context 改寫與 trace(P3)、調課/單雙週/補課、國定假日自動、自主喚醒避課、課表截圖自動填。

## 邊界與交付

- 改到常駐服務的檔:`chatnest-next` 真的重啟一次後驗 import 與健康端點(檢查表 9/11 條)。
- 測試 fixture 用糯糯學校 14 節節次表(v4 R11)。
- 交付:migration、diff、測試輸出(全綠 + 先破後立輸出)、NOTES、回滾指令、**糯糯人話驗收步驟**:
  貼節次表 → 設學期(9/7 開學、16+2)→ 加「網站規劃與設計 週一 11–12 節 圖文301」與「體育 週一 13–14 節 桌球教室」→ 看週視圖(上午空段折疊、晚上兩塊)→ 從課程卡加一份作業 → 改課名確認作業不變 → 退選確認作業還在 → 把 9/20 設整天放假看週視圖變灰。
