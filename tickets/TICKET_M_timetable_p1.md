# TICKET-M:課表 + 課表待辦 P1(草稿 2026-09-14;小踢第三輪蓋章後生效)

規格正本:`plans/PLAN_timetable_20260908.md`(v1–v4,衝突以最新版為準;v4 更正 cn 現況與 C 的形狀、加節次表與時間軸規則)。打樣:artifact 9f494bad(糯糯 9/14 蓋章,不用改)。

## 範圍(P1,只碰 chatnest-next 前端與後端;不碰 bridge、prompt、工具說明書、cn 端點)

1. **資料層**(migration 加表加欄,帶預設值,舊資料與既有 schedule 端點不受影響):
   `timetable_terms`(含 `last_class_date`、`periods_json` 節次表)、`timetable_courses`、`timetable_slots`、`timetable_overrides`,`schedule_events` 加 `kind`、`course_id`、`slot_id`、`course_name_snapshot`。外鍵行為照 v3 R5。糯糯學校節次表 14 節見 v4 R11,測試 fixture 用它。
2. **Owner 端點**(`/api/v2/timetable/*`,owner principal,CSRF):terms CRUD、courses CRUD、slots CRUD、overrides CRUD、`GET /api/v2/timetable/week?date=`(該週 slots 套 overrides,含 自主學習週 旗標)。
   既有 `POST/PATCH /api/v2/schedule` 接受 `kind`、`course_id`、`slot_id`;建立課程待辦時後端複製 `course_name_snapshot` 與 `color_key`。
   **不新增任何 `/api/v2/tools/timetable*` 路由**(P2 才開,且只 GET)。
3. **前端**(照打樣):
   - 行程鏡頭上方「月／週」切換;週視圖(時間列 × 一–五,週末有課才顯示欄;**時間軸 = 學期有課的節次集合、空段折疊成細線,不寫死;週末欄有課才顯示**(v4 R11 補);今天欄提亮;現在時刻線;停課斜紋;整天 holiday 灰;自主學習週淡化)。
   - 點課 → 課程卡(課名/時段/教室/老師;這門課的待辦(依 course_id);新增待辦;這天停課;編輯課程;退選)。
   - DaySheet 頂部「今天的課」(上課中/下一堂);新增表單多「行程／作業／考試／報告」型態與課程選擇。
   - 月視圖:待辦到期日多一條課程色條;不塞課名。
   - 編輯課表:學期(開學、學期結束、最後上課日;16+2 / 18 快速選項只算日期;節次表貼一次)、課程列表、新增課程(課名、星期多選、**有節次表時選節次、時間自動帶出;沒有就手填時間**、教室、老師、顏色)。
   - 首頁小卡「下一堂／今天沒課了 + 3 天內到期」:v1.1,可留。
4. **測試**(先破後立,每條寫明拿掉什麼要紅):
   - 快照三條(v2 R1)+ 跨時段合併一條(v3 R5 ④)。
   - overrides:cancel 單堂只影響該堂;holiday 整天全停;`kind` 未知值 422。
   - 學期:last_class_date 之後 week 端點回 `self_study=true`;week 端點回 `axis_periods`(有課的節次集合,含折疊標記);先破後立:加一門週六早上的課,axis 多出 1–4 節且中段折疊;刪掉它只剩 11–14。
   - 路由表斷言:不存在 `/api/v2/tools/timetable` 的 POST/PATCH/DELETE(斷路由不斷狀態碼)。
   - mumu token 打任何 `/api/v2/timetable/*` → 401/403。
   - 前端:週視圖渲染、色塊落在正確欄列、停課斜紋(vitest)。

## 不在 P1

cn 端點與說明書(P2)、runtime context(P3)、調課/單雙週/補課、國定假日自動、自主喚醒避課、課表截圖自動填。

## 邊界與交付

- 盲測 9/15 結束,但 P1 仍**不碰** bridge/prompt/工具描述、**不碰 `_schedule_context`**(那是 P3);那是 P2/P3 的單。
- 改到常駐服務的檔:`chatnest-next` 重啟後驗 import 與健康端點(檢查表 9/11 條)。
- 交付:migration、diff、測試輸出(全綠 + 先破後立截圖或輸出)、NOTES、回滾指令、糯糯人話驗收步驟(填一門課→看週視圖→從課程卡加作業→改課名確認作業不變→退選確認作業還在)。
