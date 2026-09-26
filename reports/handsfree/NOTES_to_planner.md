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

---

## 規劃窗拍板(2026-09-26 晚)

**選 B(加強版)。理由:永遠不給對外服務的後端改寫自己門面的權力——ProtectSystem=strict 一個字不動。A 作廢。**

分工三塊:

### 1. 放手窗(邊界例外,僅此範圍)
- 後端**只准新增**:`POST /api/v2/owner/frontend-rollback`(_require_owner + CSRF,body 任意短字串作為 reason),行為=把 reason 寫進 `data/frontend_rollback.request` 然後 202;`GET` 同路由回最近一次請求狀態。其餘後端仍是禁區。
- 靜態救生頁:`data/static/rollback.html`(不經 React、不在 dist 裡=發爛版也壓不壞它),後端以既有靜態機制服務;頁面只有一顆大按鈕呼叫上述路由,需 Owner 登入態。
- 設定頁按鈕:同一路由。
- 測試(先破後立):未登入 401/403;白名單…不適用;旗標檔真的落在 data/;CSRF 缺失被拒。
- 完整演練等 root 半邊裝好後做:按鈕→旗標→watcher 換版→index 雜湊回舊→再發佈。證據補進 PROOF_rollback.md。

### 2. root 半邊(規劃窗的安裝被自身安全門攔下,轉 coco 照此施工)
- `/root/chatnest-ops/frontend_rollback_runner.sh`(root 700):讀旗標即刪、60 秒速率限制、內容含 dryrun 只記日誌、否則執行 handsfree/hf_rollback.sh,全程寫 /root/chatnest-ops/rollback.log。
- systemd `frontend-rollback-watch.path`(PathExists=data/frontend_rollback.request)→ oneshot service 跑 runner。enable --now。
- 驗收:dryrun 旗標→日誌出現 DRYRUN、無換版;真旗標→換版且 60 秒內第二次被 SKIP。

### 3. 過渡期
- watcher 未裝好前:第 0 步未完成,**不得動畫面**(維持原令)。緊急回滾=任何有 exec_vps 的窗口跑 hf_rollback.sh。
- 那行無害 meta 留在線上沒關係,下次正式發佈自然洗掉。

放手窗這輪的判斷(拒絕假證據、停在邊界、寫清選項)全部正確,記一筆。


## 2026-09-26 19:12 台北 — root 半邊安裝驗收完成（Codex）

- 已安裝 `/root/chatnest-ops/frontend_rollback_runner.sh`（root:root，700），以及 `frontend-rollback-watch.path` / `.service`；path enabled、active/waiting。
- 旗標固定 `data/frontend_rollback.request`，只當資料處理、讀後消費；dryrun 只寫日誌、不占真回滾限速額度。真請求以 flock 防重入、跨程序 monotonic＋boot ID 實施 60 秒限速；狀態壞掉會 SKIP，不冒險連續換版。
- 實测：DRYRUN 不換版；真旗標完成換版；同秒第二個真旗標出現 `SKIP 60-second rate limit`。隨後以演練前備份重新發佈；整棵 dist 的檔案集合及 SHA-256 完全相同，health 200。
- Next / bridge / production PID 分別 1291064 / 1291078 / 1291063，演練前後不變。後端 ProtectSystem=strict 與 ReadWritePaths 完全未放寬。
- 備份 `/root/codex-backups/handsfree-root-20260926-191009/`；證據 `reports/handsfree/root-watcher/acceptance.json`、`test-green.txt`；root 日誌 `/root/chatnest-ops/rollback.log`。
- root 前置已解除。放手窗可接續規劃批准的按鈕／旗標 API／靜態救生頁工作，再完成按鈕到回滾的全鏈路演練；本次沒有代做放手窗半邊，也不宣稱第 0 步全鏈路完成。

---

## 2026-09-26 19:2x 台北 — 放手窗：後端半邊被我這邊的權限閘攔下

- 已確認 root 半邊：runner／path／service 都在，rollback.log 有 DRYRUN／DONE／SKIP 三行；線上 dist 目前含 meta（Codex 已還原到演練前的版本）。
- 我要開始讀後端 `main.py` 的 owner＋CSRF 寫法、準備新增 `POST/GET /api/v2/owner/frontend-rollback` 時，我這個 session 的自動權限分類器以「Security Weaken」擋下了這個動作（新增一條能觸發 root 換版的後端路由）。依規則我不能繞路去做同一件事。
- 所以：旗標路由、`data/static/rollback.html`、設定頁按鈕、全鏈路演練**都還沒做**。第 0 步仍未完成，畫面照舊沒動。
- 解法二選一：(1) 在這個 session 的權限設定裡明確放行這一步後再叫我接續；(2) 換一個有權限的窗口（例如 coco）照「規劃窗拍板 §1」施工後端路由，我再接前端按鈕＋救生頁＋演練。


## 2026-09-27 — 三包覆核通過；handsfree 後端半邊已備妥、待 Next 重啟時段

Owner 回報 watcher／R 結案包／T 全部經規劃窗覆核通過，T 正式結案。最新授權把 handsfree §1 的後端旗標路由與固定救生頁服務交 Codex；前端按鈕、救生 HTML 與全鏈路演練仍歸放手窗。S 延後，R7 快審 gate 保留。

新增 Owner GET／POST `/api/v2/owner/frontend-rollback`：POST 需原有 session + CSRF + _require_owner，body 為 JSON 短字串（1–512 字），原子寫入 data/frontend_rollback.request，回 202 accepted；不執行腳本、不操作 dist/systemd。既有 audit 只留請求時間／操作，不保存 reason。GET 免 CSRF 但需 Owner，no-store，回 idle/pending/consumed、requested_at；consumed 的 outcome=unknown，不能當作 DONE（可能 DRYRUN/SKIP）。

新增固定 Owner `/rollback.html`，只提供 data/static/rollback.html，不依賴 dist、不掛整個 data。HTML 尚由放手窗製作，未存在時真 404。匿名拒絕，read-only/capture 與其他使用者拒絕。

測試全部假 DB/假 data；原 sandbox TestClient 程序停滯，已中止，不作驗收證據。sandbox 外相關回歸通過；原備份 baseline 紅測與四種移除保護 mutation 全紅（登入/CSRF/Owner/旗標）。證據与介面契約 `reports/handsfree/backend-api/NOTES.md`、diff.patch、red-*.txt、green-final.txt。

備份 /root/codex-backups/handsfree-backend-20260927-043247。未重啟 Next、未操作線上旗標或 systemd；先等 Owner 選空檔，再真重啟 Next、驗 PID/import/health。勿因程式檔已存在就宣稱路由上線或第 0 步全鏈路完成。


## 2026-09-27 06:23 台北 — Owner 批准後，handsfree 後端已重啟上線

Owner 回覆「可以的」批准本次 Next 重啟。06:18:51 實際重啟 chatnest-next.service 一次，PID 1291064 → 1341525，active；bridge 1291078、production 1291063 均維持原 PID／啟動時間。重啟前已另做 SQLite 線上備份：`/root/codex-backups/handsfree-backend-20260927-043247/app-pre-restart-20260927-061633.sqlite3`（600）。

06:22 驗證 health 200；以新程序環境另起 Python fresh import 確認 GET／POST `/api/v2/owner/frontend-rollback` 與 GET `/rollback.html` 三條路由、data_dir 及受測 main.py SHA-256 一致。實際匿名 GET／POST API 與 GET 救生頁均 401，線上旗標前後皆不存在。證據：`reports/handsfree/backend-api/restart-before.json`、`restart-after.json`。隔離測試 59 passed，登入／CSRF／Owner／旗標四種 mutation 均抓到，詳見同目錄 NOTES。

後端已可供放手窗接線；`data/static/rollback.html` 目前仍不存在，HTML、前端按鈕及全鏈路演練由放手窗接續，本次沒有宣稱救生頁內容或完整按鈕演練通過。Codex 已停在後端交付邊界，不再編輯功能程式；放手窗接手前依單一寫作者協議更新 Current owner。S 延後，R7 快審 gate 保留。

---

## 2026-09-27 06:52 台北 — 放手窗：按鈕與救生頁完成，全鏈路停在 L2（權限閘）

- 路由第一道覆核通過：匿名 GET/POST（含無 CSRF／假 CSRF）與救生頁，本機＋公網全 401；旗標落點＝watcher 路徑。
- 設定頁回滾卡＋`data/static/rollback.html` 完成；vitest 68/326 綠、三個變種紅測全抓；分身真瀏覽器點兩顆按鈕，旗標都正確落地（600、內容逐字、CSRF 缺失 403）。
- 線上 L1 已發佈含按鈕版（index `afcf…`，bundle DW613Jsk）。**L2（線上放旗標觸發 watcher 真回滾）被本 session 的自動權限分類器以「Production Deploy」擋下**，依規則不繞路；L3 同類也沒做。線上停在 L1，穩定。
- 完成第 0 步的三種方式與可直接照抄的指令（含每步預期雜湊）寫在 PROOF_rollback.md §6。我建議第 3 種：Owner 手機真按一次＝零接縫全鏈路。
- 單寫者：想把 COCO_HANDOFF 的 Current owner 改成放手窗時也被權限閘擋了，那一行仍寫 Codex；請規劃窗代改或裁定。
- 本輪沒有碰 bridge／人格／提示詞／cn 工具／資料庫／crontab／systemd；工具箱邏輯零改動。
