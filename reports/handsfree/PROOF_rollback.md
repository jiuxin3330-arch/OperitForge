# PROOF_rollback — 放手實驗第 0 步

執行：o5.5 放手窗（2026-09-26 18:40–18:45 台北）
結論先講：**回滾機制（快照／發佈／回滾腳本）做好了，也完整演練過一次來回；但「設定頁上的回滾按鈕」在目前的邊界裡做不出來，第 0 步沒有全部完成，所以我沒有動任何畫面。** 原因跟選項寫在 `NOTES_to_planner.md`。

---

## 1. 為什麼按鈕卡住（事實，可自己驗）

- 前端 `frontend/dist` 是 Next 後端（`chatnest-next.service`，uvicorn）直接伺服的：`backend/app/main.py:10034` 起，`/assets` 掛 StaticFiles、其他路徑 catch-all 回 `dist/index.html`。
- 網頁上的按鈕只能打後端 API。後端**沒有任何**會寫 `frontend/dist` 的路由（已列過全部 POST/PUT/PATCH/DELETE）。
- 就算加路由也寫不進去：`systemctl show chatnest-next` → `ProtectSystem=strict`、`ReadWritePaths=/root/chatnest-next/data /srv/mumu-server/photos`。整個 `frontend/` 對後端程序是唯讀。
- 所以「按鈕 → 換 dist」一定要動**後端 Python**（加路由）＋**systemd**（開寫入權限或加 path unit）其中至少一個，兩個都在鐵邊界裡。

## 2. 已完成的部分：回滾工具（只在 frontend/ 與 reports/handsfree/）

位置：`/srv/chatnest-next/frontend/handsfree/`

| 腳本 | 做什麼 |
|---|---|
| `hf_build.sh` | `systemd-run --wait --collect -p MemoryMax=900M -p MemorySwapMax=400M` 下跑 `tsc -b && vite build`，輸出到 `reports/handsfree/stage-<時間>/`，**不碰線上 dist** |
| `hf_publish.sh <stage> "說明"` | ① 整份 `cp -a dist → dist.hf-snap-<時間>` ② rsync 合併發佈（不 `--delete`，保住 `chatnest-ble.apk` 與舊 assets）③ `index.html` 最後才原子替換 ④ 快照只留最近 3 份 |
| `hf_rollback.sh [快照]` | 預設最新一份 `dist.hf-snap-*`：複製成 `dist.hf-incoming` → `mv dist dist.hf-undone-<時間>` → `mv incoming dist`。快照不會被吃掉，重按結果一樣（冪等）；被換下來的版本留在 `dist.hf-undone-*`（也只留 3 份） |

所有動作都記在 `reports/handsfree/publish.log`。

## 3. 演練紀錄（原始輸出在 VPS `reports/handsfree/rehearsal.txt`）

無害小改動：`frontend/index.html` 在 `<title>` 前加一行 `<meta name="chatnest-frontend-channel" content="handsfree" />`（不可見、不影響任何行為）。

演練前先做「零改動 build」：原始碼 build 出的主 bundle 是 `index-DYFAg3eY.js`，跟線上一模一樣 → 確認原始碼沒有別人未發佈的東西，不會被我順手帶上線。

因為 bundle hash 不會變（只動 index.html），驗證看的是線上 index.html 的 sha256 前 16 碼和 meta 有沒有出現：

| 時點 | 動作 | 本機 127.0.0.1:8790 | 公網 next-chat.cn-dev.uk | health |
|---|---|---|---|---|
| T0 18:42:15 | 發佈前 | `48b22658e32893a9` meta=0 | `48b22658e32893a9` meta=0 | 200 |
| T1 18:42:15 | `hf_publish.sh`（快照 `dist.hf-snap-20260926-184215`） | `5c9d417c37eee2d1` meta=1 | `5c9d417c37eee2d1` meta=1 | 200 |
| T2 18:42:18 | `hf_rollback.sh` | `48b22658e32893a9` meta=0 ✅ 回到 T0 | `48b22658e32893a9` meta=0 ✅ | 200 |
| T3 18:42:21 | 再發佈回來（快照 `dist.hf-snap-20260926-184221`） | `5c9d417c37eee2d1` meta=1 | `5c9d417c37eee2d1` meta=1 | 200 |

補充檢查：
- `curl /api/v2/health` 回的是真的 `{"status":"ok"}`，不是 SPA 備援頁。
- 公網 `/assets/index-DYFAg3eY.js` 200、593124 bytes。
- `diff -rq dist.hf-snap-20260926-184215 dist` → 只有 `index.html` 不同（整棵樹其他檔案逐一相同）。
- `diff -rq dist dist.hf-undone-20260926-184218` → 完全相同（被回滾換下的就是含 meta 的那版）。
- `dist/chatnest-ble.apk` 9982548 bytes，全程都在。
- 服務完全沒重啟（純靜態檔替換）。

## 4. 規劃窗怎麼驗

```bash
cd /srv/chatnest-next/frontend
cat ../reports/handsfree/rehearsal.txt ../reports/handsfree/publish.log
ls -1d dist.hf-*
curl -s http://127.0.0.1:8790/ | grep -c chatnest-frontend-channel   # 現在應該是 1
# 想親手再驗一次回滾：
handsfree/hf_rollback.sh && curl -s http://127.0.0.1:8790/ | grep -c chatnest-frontend-channel   # 變 0
# 再發回來：
handsfree/hf_publish.sh ../reports/handsfree/stage-20260926-184124 "planner re-verify"
```

## 5. 目前狀態

- 線上：含無害 meta 的版本（功能、畫面與發佈前完全一樣）。
- CLI 回滾：任何有 root shell（hands `exec_vps`）的窗口，一行 `hf_rollback.sh` 就能回上一版，已驗證。
- **設定頁按鈕：未做（BLOCKED）**，等規劃窗在 `NOTES_to_planner.md` 的選項裡拍板。
