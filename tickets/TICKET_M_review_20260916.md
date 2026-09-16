# TICKET-M P1 覆核(規劃窗,2026-09-16)

結論:後端與前端成品通過;9/20 題裁定「無課週末 holiday 不額外顯示灰欄」;前端 v162 發佈等糯糯批准。

| 項 | 驗法 | 結果 |
|---|---|---|
| schema | `.schema` | overrides:term_id CASCADE、slot_id CASCADE、CHECK 到位;periods UNIQUE;events 四欄到位 |
| 先破後立 | DB 臨時複本插入/刪除(做完即刪) | cancel+NULL 擋、holiday+slot 擋、刪 slot → cancel 隨之消失(1→0) |
| 權限 | curl | mumu token /timetable/terms 401;無登入 401;/tools/timetable 的 200 是 SPA fallback html,程式碼 0 處 |
| 服務 | systemctl/health | 9/15 21:55 重啟後 NRestarts=0、health 200 |
| 正式 DB | count | 五張 timetable 表 0 列;schedule_events 15 筆 kind=event(測試沒寫進正式庫) |
| 測試 | 重跑 test_timetable.py | 14 passed |
| 既有紅 | preexisting-bridge-baseline.txt | 2 條皆 TICKET-I B2 未做前的漂移測試,非本單 |
| 成品 | stat/diff | frontend-dist(9/15 22:05)≠ 服務中 dist(9/14),未發佈;備份 19 項在;rollback.py 無 DROP/DELETE |

工作窗這次做得好的:先破後立 25 個突變、分批完整回歸不把既有紅說成綠、真的重啟、驗收第 7 步不假裝過、發佈守 AGENTS.md 另批。
