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


## 2026-09-26 19:12 台北 — root 半邊安裝驗收完成（Codex）

- 已安裝 `/root/chatnest-ops/frontend_rollback_runner.sh`（root:root，700），以及 `frontend-rollback-watch.path` / `.service`；path enabled、active/waiting。
- 旗標固定 `data/frontend_rollback.request`，只當資料處理、讀後消費；dryrun 只寫日誌、不占真回滾限速額度。真請求以 flock 防重入、跨程序 monotonic＋boot ID 實施 60 秒限速；狀態壞掉會 SKIP，不冒險連續換版。
- 實测：DRYRUN 不換版；真旗標完成換版；同秒第二個真旗標出現 `SKIP 60-second rate limit`。隨後以演練前備份重新發佈；整棵 dist 的檔案集合及 SHA-256 完全相同，health 200。
- Next / bridge / production PID 分別 1291064 / 1291078 / 1291063，演練前後不變。後端 ProtectSystem=strict 與 ReadWritePaths 完全未放寬。
- 備份 `/root/codex-backups/handsfree-root-20260926-191009/`；證據 `reports/handsfree/root-watcher/acceptance.json`、`test-green.txt`；root 日誌 `/root/chatnest-ops/rollback.log`。
- root 前置已解除。放手窗可接續規劃批准的按鈕／旗標 API／靜態救生頁工作，再完成按鈕到回滾的全鏈路演練；本次沒有代做放手窗半邊，也不宣稱第 0 步全鏈路完成。

---

# 第 0 步・第二輪（2026-09-27 06:36–06:51 台北）：按鈕＋救生頁＋全鏈路演練

**狀態：A 段（分身真點按鈕→旗標落地）與 L0/L1 線上發佈完成；L2（線上旗標→watcher 換版）與 L3（再發佈）被放手窗 session 的權限閘以「Production Deploy」擋下，未執行。第 0 步尚未關閉。** 線上目前是含回滾卡的新版（見 L1），狀態穩定。

## 1. 第一道覆核：coco 後端路由匿名實測（06:36）

| 請求 | 本機 127.0.0.1:8790 | 公網 next-chat.cn-dev.uk |
|---|---|---|
| GET `/api/v2/owner/frontend-rollback` | 401 login required | 401 |
| POST 同路由（無 CSRF） | 401 | 401 |
| POST 同路由（假 CSRF） | 401 | 401 |
| GET `/rollback.html` | 401 | 401 |

線上旗標檔前後都不存在；`frontend-rollback-watch.path` active；`restart-after.json` 的 `data_dir_matches: true`，旗標落點＝`/srv/chatnest-next/data/frontend_rollback.request`＝watcher 的 PathExists。

## 2. 交付物

| 檔案 | sha256 前 16 | 說明 |
|---|---|---|
| `frontend/src/FrontendRollback.tsx` | `f4354b39c8f14db3` | 設定頁回滾卡：先 GET 狀態，非 Owner 整張卡不出現；兩段式確認；POST 後輪詢，consumed 只說「伺服器已收下」並提示 60 秒限速，不宣稱成功；永遠附救生頁連結 |
| `frontend/src/frontendRollback.test.tsx` | `178715c00a51071f` | 5 項契約 |
| `frontend/src/App.tsx` | — | 只加 1 行 import＋`<FrontendRollback />` 放在 `<Toolbox />` 正後方；工具箱零改動 |
| `frontend/src/styles.css` | — | 尾端加 5 行 `.rollback-*` 樣式 |
| `data/static/rollback.html` | `20a472422f8b6e6c` | 救生頁：純 HTML＋inline JS，不經 React、不在 dist；讀 `chatnest_next_csrf` cookie；未登入顯示「需要 Owner 登入」；`confirm()` 後 POST |
| `frontend/handsfree/clone_drill.py/.mjs`、`hf_check.sh` | — | 分身演練、線上雜湊檢查工具 |

備份：`reports/handsfree/backup-step0b-20260927-063800/`（App.tsx、styles.css 原檔）。

## 3. 測試（先破後立）

- 全套 vitest（從專案根目錄跑，符合既有慣例）：**68 files / 326 passed**（`step0b-vitest.txt`）。
- 變種紅測（`step0b-red.txt`）：拿掉 `<FrontendRollback />` → 紅；拿掉二次確認 → 紅；拿掉救生頁連結 → 紅；還原後 md5 相同、5/5 綠。
- `tsc -b && vite build`（systemd-run MemoryMax=900M）通過：stage-20260927-064200，bundle `index-DW613Jsk.js`。

## 4. A 段：一次性分身＋真瀏覽器（06:47，`step0b/clone-drill.txt`）

分身＝假 DB、FAKE_MODE、臨時 data/、前端用上述 stage build、救生頁用線上同一份檔案。Playwright Chromium：

| 步驟 | 結果 |
|---|---|
| 匿名 GET 救生頁／API | 401／401 |
| Owner 登入 → 導覽 → 設定 | 回滾卡出現，DOM 上緊接在工具箱卡後面（true） |
| 點「回滾前端」第一下 | 只出現確認列，旗標**未**產生 |
| 點「確定回滾」22:47:19.151Z | 旗標落地：內容 `Owner 從設定頁按下回滾前端`，sha256 `53d1200d8358b66eaebc237cac282d61e41b56c91baddb4ec534034b334383d4`，權限 600；GET 狀態 `pending`，requested_at 22:47:19.219Z |
| 模擬 watcher 取走旗標 | GET 變 `consumed`、outcome `unknown`；卡片顯示「伺服器已收下請求…60 秒內」 |
| 救生頁（390×844，帶 Owner cookie） | 200、`Cache-Control: no-store`、回應 sha256 `20a47242…`＝磁碟檔 |
| 救生頁按鈕＋confirm 22:47:21.389Z | 旗標落地：`Owner 從救生頁請求回滾`，sha256 `4749fade…516d`，600 |
| 不帶 CSRF 的 POST | 403 |
| 頁面 JS 錯誤 | 0 |

截圖（`step0b/`）：card-idle `d0e4f228…`、card-confirm `d1a41bd4…`、card-consumed `a870d533…`、rescue-idle `7985f091…`、rescue-consumed `090883d7…`。

接縫（誠實標註）：分身沒有 watcher，旗標路徑也不是線上路徑。所以「按鈕→旗標」在分身證明、「旗標→watcher→換版」要在線上證明，兩段用**同一份旗標位元組（sha 53d1…）**銜接。完全不接縫的一次（Owner 在手機上真按）留作最終驗收。

## 5. B 段：線上（`step0b/live-drill.txt`）

| 時點 | 動作 | 本機 index（HTTP 取值） | 公網 | dist/index.html 檔案 sha | 回滾卡在 bundle |
|---|---|---|---|---|---|
| L0 06:48:55 | 基準 | `5c9d417c37eee2d1` DYFAg3eY | 同 | `293c045e6974cbe7` | 0 |
| L1 06:49:48 | `hf_publish.sh` stage-064200，快照 `dist.hf-snap-20260927-064948`（其 index＝`293c…`＝L0） | `afcfcc7042732817` DW613Jsk | 同 | `3c4a67caf4a15032` | 1 |
| L2 | 線上放旗標（sha 53d1…）→ watcher → 預期回到 `5c9d…`／`293c…` | **未執行：權限閘 Production Deploy 擋下** | | | |
| L3 | 再發佈 → 預期回到 `afcf…` | **未執行** | | | |

06:50:58 複查：兩端都是 `afcfcc7042732817`、health 200；旗標不存在；rollback.log 最後一行仍是 9/26 的 SKIP（本輪沒有觸發任何線上回滾）。

## 6. 要完成第 0 步還差什麼

只差 L2＋L3，兩者都得在線上觸發一次真回滾再發佈回來。三種做法擇一：
1. 在放手窗 session 放行「線上觸發回滾／發佈」這類動作，我照 L2/L3 腳本跑完、補表。
2. 有權限的窗口照下面指令跑（預期值都已寫好）：
   ```bash
   cd /srv/chatnest-next/frontend
   handsfree/hf_check.sh                                   # 應為 afcf… / DW613Jsk
   (umask 077; printf '%s' 'Owner 從設定頁按下回滾前端' > ../data/.hf-flag && mv ../data/.hf-flag ../data/frontend_rollback.request)
   sleep 5; tail -3 /root/chatnest-ops/rollback.log; handsfree/hf_check.sh   # 應為 DONE、5c9d… / DYFAg3eY / 卡=0
   handsfree/hf_publish.sh /srv/chatnest-next/reports/handsfree/stage-20260927-064200 "step0b: 演練後再發佈"
   handsfree/hf_check.sh                                   # 應回 afcf… / DW613Jsk / 卡=1
   ```
3. 最乾淨：Owner 在手機 設定 → 回滾前端 → 確定回滾，一次走完真實全鏈路；之後任何窗口用第 2 點最後兩行再發佈回來。
