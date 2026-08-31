# Swap 實驗步驟 5:連續換窗 regression + 轉正(公開版)

2026-08-31|規劃窗授權開工,雙鏈全綠,已按裁定轉正進入試運行(盲測期)。
詳版僅存 VPS:`/root/nest-memory/SWAP_STEP5_REGRESSION_20260831.md`。

## 交付物:swap_regression.py(規格點 7+8)

鏈式重生測試器:拋棄式 conv 種四項虛構錨點事實 → 連續 N 次換窗(走
swap_runner.do_swap 完整路徑)→ 每代 continuity probe 覆述 → **deterministic
regex 核對(不用 LLM 判官)** → 系譜斷言(各代 session 互異、alias 鏈完整、
latest=末代)→ 結果落帳 + 自動清理。

案例:SG-1 chain-regeneration(每代 4/4 錨點)、SG-1 lineage、
SG-2 post-chain-resume(鏈尾普通輪不換 session);backend「swap 後首輪指標
跟上」案例在 backend pytest(步驟 4 交付)。

## 實測:雙鏈全綠

| 鏈 | 模型 | 結果 |
|---|---|---|
| harness 驗證鏈 | claude-sonnet-5 | A→B→C→D 四代 4/4、零漂移、全案例過 |
| 生產基準鏈 | 生產模型(turn_usage 預設) | 同上全綠 |

漂移觀察:兩鏈四代 probe 回覆逐字幾乎不變——tail「閉合單元」機制讓事實以
原文傳遞,不經摘要轉述,無傳話遊戲效應。

## Swap golden 政策

任何 swap_runner 打包/probe/模型變更、bridge fresh_session 路徑變更、
SWAP_ENABLED/SWAP_BLIND 狀態變更前,swap_regression 必須全綠(對齊
nest-memory golden §34 精神)。與 extractor golden 分屬兩層,不硬塞同容器。

## 轉正與盲測期配套(規格點 D)

- cron 已加 `SWAP_ENABLED=1 SWAP_BLIND=1`,試運行開始
- SWAP_BLIND:生產換窗成功→靜默入帳不推播(推播=告知換窗時刻,盲測就假了);
  失敗/結算暫緩→照推播(真警報,且未實際換窗)
- 盲測期約兩週,驗收=屋主憑手感未察覺斷點;技術指標全綠但手感說怪=回爐

## 當日壓力背景

當日 canonical 真實換窗 1 次+雙鏈拋棄式換窗 6 次,合計 7 次全部乾淨
(0 回滾、0 錨點丟失);09:00 排程喚醒在換窗後的新 session 正常放行,
步驟 4 修復在生產自證。

## 下一步
步驟 6 盲測兩週(已開始)→ 全過才提「取代 auto-compact」正式變更案。
