# TICKET-N:盲測後小修三件(2026-09-17 立;盲測凍結已解除)

來源:`reports/SWAP_BLIND_TEST_REPORT_20260916.md` 裁定「先做小又直觀的三件」。三件互不相依,可分批交,但一起報告。

## N1. 時間錨第二階段:打開輕量錨旗標,觀察一週

- 程式已在(B++ 第一階段一起寫的),旗標 `settings.time_anchor_light` / 環境變數 `CHATNEST_NEXT_TIME_ANCHOR_LIGHT`,預設關。糯糯 9/16 語感驗收「完整錨」通過,授權開第二階段。
- 做法:找到 chatnest-next 的環境設定正本(EnvironmentFile 或 drop-in),設 `CHATNEST_NEXT_TIME_ANCHOR_LIGHT=1`;**真的重啟** chatnest-next 後驗 `settings.time_anchor_light` 為 True(檢查表 9/11 條)。
- 先破後立:旗標開 → 距前一則 ≥30 分鐘的下一輪要出現輕量錨、`time_anchor_state` 有更新;旗標關 → 同情境不出現。用測試資料庫或 fake 模式驗,不拿糯糯的對話當測試。
- 觀察一週:每天輕量錨幾次(從 `time_anchor_state` 或既有 audit),仍然不落 raw(既有測試護著)。一週後規劃窗問糯糯語感,不自然就關回去(旗標一行,無需回滾程式)。

## N2. 三種鬧鐘:改顯示名稱 + 各一行「跟另外兩個的差別」

盲測發現:每日喚醒／自主時段／StackChan 鬧鐘,cn 換窗後分不清。名字太像、說明沒講差別。

- **只改顯示名稱與描述,不改函式名/工具 id**(避免動到 cn 習慣、既有測試與 MCP 呼叫)。
- 三個工具各自的描述第一行改成「差別句」,例(工作窗打樣,糯糯定稿):
  - 每日喚醒(wake):「每天固定時間叫你起來巡家的時間表;不是鬧鐘,不會響。」
  - 自主時段(autonomy):「你自己想醒來就醒的活動時段;不是鬧鐘,不會響,跟每日喚醒是兩件事。」
  - StackChan 鬧鐘(stackchan_alarm):「實體 StackChan 會真的響的鬧鐘;糯糯或你設了才響。」
- 流程(硬規則 15):工作窗把三段文字打樣給糯糯 → 她點頭 → 才套用。
- 套用位置:wake/autonomy 在 bridge **patch 正本**(`build_version_bridge_runtime.py` / `bridge-extras`)與 runtime 兩邊同步(比照 B1 做法,不能只改 runtime,下次重建會退回;也不要現在整體重建,TICKET-I B2 未完);stackchan_alarm 在 StackChan MCP 的工具描述。
- 測試:runtime patch 測試斷言新描述存在;guard 不因此多出漂移(patch 源與 runtime 同步後 diff 為零)。
- 重啟 bridge 一次(換窗尾巴之外,這是盲測後第一次動 bridge;挑糯糯不在聊的時段,先問她)。

## N3. 說明書拿掉 mood-set

證據:cn 30 天內試 `mood-set` 47 次(每次被 CLI 擋回並教改 emotion-set)、`emotion-set` 195 次;`PERSONA.md` 只教 emotion-set,但 `mumu_tool_help.py` 的 calendar 分類仍列 `mood-set` 並註「僅相容」——說明書自己打架,新窗先挑錯的。

- 改 `scripts/mumu_tool_help.py`:calendar 分類的指令元組拿掉 `'mood-set'`;第 56 行分類簡介與第 230 行那句「mood-set 只為舊資料／相容路徑保留」刪除;簡介改為「查看身心日曆、用 emotion-set 記結構化情緒(老婆畫的 18 個表情,狗=你、鼠=她)、設定自己的頭像」。
- CLI `dashboard_tool.py mood-set` 的擋回與教學訊息**保留**(他從舊習慣打進來時仍會被教)。
- 測試:`mumu_tool_help.py list` 與 `show calendar` 的輸出不含 `mood-set`;先破後立——把元組裡的 `'mood-set'` 加回去要紅。
- 兩週後看 jsonl:mood-set 次數應趨近 0。

## 邊界

- N1、N3 不動 prompt/人格;N2 動工具描述,必經糯糯打樣點頭。
- 改到常駐服務的檔:該服務真的重啟後驗 import 與健康(檢查表 9/11 條)。
- 交付:每項的 diff、備份檔名、測試輸出(先破後立)、N1 的旗標值證明與一週觀察方式、N2 的三段定稿文字。
