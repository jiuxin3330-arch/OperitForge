# TICKET-T：壓縮警報器——auto-compact 不得再靜默發生

立單：2026-09-24 規劃窗。背景：INCIDENT_20260924_autocompact_race.md。
前提：SWAP_MARGIN_TOKENS=55000 hotfix 已上（本單不重做）；本單是第二道防線＋善後自動化。
優先序：排 TICKET-R 之後、可與 S 並行或先做（很小）；coco 開工前讀事故報告。

## T1 偵測

1. 週期檢查 canonical 對話 session jsonl 的 compact 標記（`isCompactSummary` / `compact_boundary`），新標記出現＝事件。掛進既有 swap_runner cron 週期或 health.py，不開新常駐服務。
2. 判定「新」：記住上次已見的 compact 標記位置（檔案+行位址或 uuid），存 swap_runner 同目錄 state 檔。

## T2 反應（兩件都做）

1. **警報**：寫 health log＋推播給 Owner（走既有 push 通道），文案人話：「cn 的對話被官方壓縮了一次，時間線可能失真，建議盡快換窗」。
2. **排換窗**：偵測到壓縮後，向 swap_runner 標記「壓後待換」；下一次滿足安靜條件（QUIET_SECONDS）即觸發換窗，**不等 145k 門檻**（壓縮後 tokens 已掉回 6–8 萬，正常門檻等不到）。換窗仍走既有流程（結算→換窗→近況卡）。壓後換窗一次為限，state 清除。

## T3 邊界

- 只讀 jsonl 的結構欄位（type/subtype/uuid/timestamp），不讀對話內容、不存摘要文字。
- 誤報成本低（多換一次窗），漏報成本高——判定從寬。
- SWAP_BLIND 現值沿用；壓後換窗的推播不受 blind 抑制（警報本身就是要人知道）。

## 驗收（先破後立，測試資料）

- 紅測 1：注入含 compact 標記的測試 jsonl → 未產生警報必紅。
- 紅測 2：同一標記重複掃描 → 重複警報必紅（冪等）。
- 紅測 3：壓後待換 state 存在且安靜條件滿足 → 未觸發換窗必紅。
- 不拿正式 canonical 對話做注入測試。

## 交付

NOTES（回滾＝移除檢查掛載點＋刪 state 檔）、diff、測試輸出、一次手動演練紀錄（測試 conv）。規劃窗覆核後結案。
