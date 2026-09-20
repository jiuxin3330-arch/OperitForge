# INCIDENT 2026-09-21 04:22–04:32（台北）：測試載入 embedder 把 VPS 壓到 OOM，anchor 本體被殺、意外重啟載入新碼

## 發生什麼

- 04:22 施工窗（CC，經 hands-mcp `exec_vps`）啟動 TICKET-Q 先破後立測試。測試用 `AnchorMemory` 真 embedder（sentence-transformers，載入 ~1GB RSS）。
- `exec_vps` 有 30 秒上限，第一個測試指令「超時」但**進程沒被殺**，接著又並行起了第二份、再用 `systemd-run` 起了兩份 → 最多 4 份 embedder 同時載入。
- VPS 只有 **2GB RAM + 2.4GB swap**。load average 衝到 26，hands / anchor / stackchan 三個 tunnel 端點全部 502，施工窗失聯約 10 分鐘。
- 04:27:02 OOM killer 殺掉 **anchor-memory 本體**（PID 870655）。systemd `Restart=always` 重啟，前兩次重啟又在載入 embedder 時被 OOM 殺掉（04:27:59、04:31:26），第三次（04:31:42 起、04:32:23 完成）成功。
- 第三次重啟載入的是**工作樹裡的新碼**（anchor_mcp_http.py 已重寫），migration 在 04:32:23（UTC 20:32:23）對生產 DB 自動跑完，污染期快照 = 那一刻。
- 04:32:3x 施工窗恢復連線，`pkill -9` 清掉殘留測試進程，記憶體回到 700MB 可用。

## 影響

- anchor 服務中斷約 5 分鐘（04:27–04:32）。期間 bridge journal 沒有對話流量（糯糯沒在聊），沒有使用者回合受影響。
- **重啟沒有先問糯糯時段**——工單明訂「重啟挑糯糯不在聊的時段，先問她」。實際上是 OOM 逼出來的，不是我下的 restart，但結果一樣：服務用新碼跑了，且沒做「重啟前最新備份」。可用的備份是 04:11 那份（`memories.db.bak-ticketq-20260921_041130`，schema 是舊的，內容與重啟時的差異只有 04:11–04:27 之間的 search cite 增量）。
- DB integrity ok，記憶 376 / 邊 62,938 沒少；migration 快照欄位 legacy_* 全部填齊（NULL 為 0）。
- 生產 anchor 現在跑新碼，29 個工具全在、本機/外部路徑皆通（見 TEST_OUTPUT.md 健康段）。

## 對策（已做）

- 測試改用**假 embedder**（字元 bigram 雜湊向量，stub 掉 `sentence_transformers` 模組）：測的是儲存層與強化邏輯，不需要真向量。真 embedder 用 `ANCHOR_TEST_REAL_EMBEDDER=1` 顯式開。
- 測試一律 `systemd-run -p MemoryMax=800M -p MemorySwapMax=0`，**一次一份、序列跑**。超過上限只死測試，不死服務。
- 施工前先看 `free -m`：在 2GB 的機器上，任何會載 embedder 的東西都不能跟 anchor 同時存在。

## 檢查表候補（待覆核裁定才收）

> 施工者的測試/探測進程也是「施工者身在系統之內」的一種形狀（第 6 種？）：**測試載入的模型跟生產服務搶同一塊記憶體**，測試把生產壓死，而且失聯的是自己的手。對策：測試不載真模型（stub），或先量 `free`；跑在 `MemoryMax` 的 cgroup 裡。出處：TICKET-Q 2026-09-21。
