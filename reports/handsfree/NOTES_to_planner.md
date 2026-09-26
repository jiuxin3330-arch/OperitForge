# NOTES_to_planner — 放手實驗留言

## 2026-09-26 18:45 台北｜第 0 步卡住：回滾按鈕跟邊界互相矛盾

**狀態：停在第 0 步。沒有動任何畫面，也沒有碰後端／bridge／systemd／crontab／資料庫。** 工單說「第 0 步做完才准動畫面」，按鈕做不出來，所以後面的抽查改版我全部沒開始。

### 矛盾在哪

工單要「設定頁一顆按鈕，按下去把 dist 換回上一版快照」，又要「只碰 frontend」。但：

1. 網頁按鈕只能呼叫後端 API；後端沒有任何寫 `frontend/dist` 的路由。
2. 後端服務 `ProtectSystem=strict`，可寫路徑只有 `data/` 和 `/srv/mumu-server/photos`，就算加路由也寫不了 `frontend/`。
3. 所以伺服器端換 dist 這件事，一定得有「一個有寫入權限的執行者」被網頁叫醒。能當執行者的只有：後端 Python、systemd（path unit／放寬 ReadWritePaths）、crontab、bridge（cn）。全都在鐵邊界裡。

我評估過「純前端」的做法（按鈕把版本釘在瀏覽器 localStorage／service worker，讓那台裝置載入舊版）：只對按下去的那台裝置有效、伺服器的 dist 根本沒換，跟工單說的「把 dist 換回上一版快照」不是同一件事。拿它來交差，等於把演練證據做成假的，所以沒做。

### 已經做好的（不論選哪個方案都用得上）

- `frontend/handsfree/hf_build.sh / hf_publish.sh / hf_rollback.sh`：build 有記憶體上限、發佈前自動快照（留 3 份）、回滾冪等且保留被換下的版本。
- 完整演練過一次來回，證據見 `PROOF_rollback.md`。
- 目前的安全網：任何有 hands `exec_vps` 的窗口一行 `/srv/chatnest-next/frontend/handsfree/hf_rollback.sh` 就能回上一版。

### 選項（請規劃窗選，或轉 Owner）

**A（我推薦）：開一個最小例外，由有權限的窗口施工**
- 後端：加一條 `POST /api/v2/frontend/rollback`，`_require_owner` + CSRF，不收任何參數，只做 `hf_rollback.sh` 那三步（複製最新快照 → 換掉 dist → 寫 log）。
- systemd：`chatnest-next.service` 加 drop-in，`ReadWritePaths` 多一個 `/srv/chatnest-next/frontend`（只放寬這一個目錄）。
- 前端（我來做）：①設定頁 Owner 區一顆「回滾前端」按鈕＋二次確認＋顯示目前版本和可回的快照時間；②**另外做一張不經 React bundle 的靜態頁 `/rollback.html`**（純 HTML＋fetch），這樣就算我發佈了一版把設定頁弄壞的前端，Owner 還是按得到回滾。這才叫「整個實驗期間永遠有效」。
- 缺點：開了兩個小洞（一條後端路由＋一個可寫目錄）。

**B：後端只寫旗標，root 的 systemd path unit 執行換版**
- 後端路由把一個旗標檔寫進 `data/`（不用放寬 ReadWritePaths），`chatnest-frontend-rollback.path` 看到旗標就以 root 跑 `hf_rollback.sh`。
- 優點：後端程序本身永遠碰不到 dist；缺點：多一個常駐 unit，動到 systemd 更多，而且除錯多一層。

**C：接受「單機釘版」**（不推薦，理由在上面）。

**D：不要按鈕，改寫進工單：回滾 = CLI `hf_rollback.sh`**
- 最不動邊界，但 Owner 自己按不到，要靠有 root shell 的窗口。

### 其他要知會的

- 單寫者協議：`COCO_HANDOFF.md` 目前寫 Codex 是 TICKET-R 的單寫者。依記憶，R 前端已經發佈、只剩 Owner 手機驗收＋coco 補報告，規劃窗也說「R 前端發佈後即可開跑」，所以我動了 `frontend/`。我碰到的原始碼只有 `frontend/index.html` 加一行 meta（原檔備份 `reports/handsfree/index.html.orig-20260926`），沒碰 R 的任何檔案。
- 線上目前是含那行 meta 的版本（不可見、零行為差異）。要清掉的話：還原 index.html → `hf_build.sh` → `hf_publish.sh`。
- 快照會吃磁碟：一份約 33MB，snap 3 份＋undone 3 份，上限約 200MB，目前磁碟剩 30G，沒問題。
- 放手令說 `CHANGELOG_handsfree.md`（記憶裡的寫法）跟 `reports/handsfree/CHANGELOG.md`（工單寫法）名字不一樣，我照工單用 `reports/handsfree/CHANGELOG.md`。
- 規劃窗拍板後，要在這裡或工單留一句，下個放手窗就會從第 0 步的按鈕接著做。
