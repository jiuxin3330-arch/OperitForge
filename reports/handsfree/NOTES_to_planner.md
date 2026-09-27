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

---

## 2026-09-27 20:05 台北 — 放手窗：第 0 步關閉後 batch 1 已上線；兩件事留給規劃窗

**已做**：以屋主鐵律 3.4／§4 為尺，分身（假 DB）390×844 日夜掃 家／寫入記錄／收藏／記憶／設定。整體乾淨：零水平溢出、零超出視窗、零預設 outline、零 JS 錯誤。batch 1 只修「用線條分界」的違規（CSS 尾端一段，已發佈 19:57，bundle `index-j_siZfMq.js`，index `fb90f97a…`，快照 `dist.hf-snap-20260927-195723`）。稽核前後差異：家 3 處、收藏 1 處、設定 3 類按鈕的線框日夜皆消失，無新違規。證據 `audit-r1/`、`audit-b1/`、`b1-shots-*`、`b1-compare.jpg`、`b1-publish.txt`、`b1-vitest.txt`（68/326 綠）。

**刻意沒改（查證後是屋主決定，不是 bug）**：設定卡直角——`styles.css:8285` 屋主修正「quiet settings」讓卡片與頁面同底色，直角不可見；topbar-icon 的白色上緣是新擬態亮部。

**需要裁定 1｜收藏筆記卡的細框**：`.collection-message-card` 有 1px 細框（違反鐵律①），但同一張卡被「Home cards and all new panels remain flat」鎖成 `box-shadow:none !important`。夜間底色與頁面只差 4% 白，拿掉框就幾乎看不到邊界。兩條規則打架：A 允許這張卡用極淡陰影；B 夜間把卡底提亮到可辨識再去框；C 維持現狀。我傾向 B，但這是視覺取捨，等裁定。

**需要裁定 2｜看不到「有內容」的畫面**：分身是假 DB，日記寫入在假模式回 404（資料接真實來源），記憶頁讀 anchor 也是空的。所以我目前只能抽查空狀態與設定類畫面，Owner 每天看的「滿滿內容」畫面抽不到。要讓放手窗抽查內容頁，需要其中一種：(1) 一份脫敏的示範資料集給分身用；(2) 允許用 Owner 帳號做**唯讀**的線上截圖；(3) Owner 自己截幾張手機畫面放進 reports/handsfree/owner-shots/。沒有這個之前，我只做規則類小修，不做需要看內容才能判斷的改版。

**待辦（小）**：設定頁 `service-health` 狀態膠囊有 1px 框，下批順手修。

---

## 2026-09-28 03:25 台北 — 放手窗：內容種子抽查 → batch 2 上線；本輪收尾

**種子使用**：只匯入一次性分身的臨時庫（15 張有資料的表，依欄位交集 insert；另在分身庫補一筆 `migration_records legacy_dashboard_v1 applied` 讓 dashboard 讀本地表——只存在分身臨時庫）。照片以純色佔位圖代替（不含任何影像）。未觸及對話、生理、憑證。量測只取幾何／顏色數字（density.json、audit.json 不含文字）。

**發現與處置（batch 2，03:20 發佈，bundle `index-wVZYrNDN.js`，index `0c50148c…`，快照 `dist.hf-snap-20260928-032043`）**
1. 收藏手帳卡：屋主 v119「日間白區下緣有影、夜間素身」（styles.css:13243）被 6202 的 flat `!important` 蓋掉，**日間陰影從未生效**（實測 box-shadow none）。以更高權重讓 v119 生效；夜間依裁定提亮（底色對比 ≈1.15→1.325，與日記卡夜間 1.335 一致），無框無影。
2. 日記紙張 `diary-paper-sheet`：虛線撕取線 → 漸隱細線（同 G1／batch 1），三處票券造型統一。
3. 設定 `service-health`：灰框 → 新擬態內凹。
驗證：vitest 68/326；內容分身稽核前後差異只有上述線框消失、無新違規、零 page error、零失敗請求；密度量測確認 1、2 生效。

**收尾**：種子檔已刪（sha256 記在 `seed-deleted.txt`）；分身臨時目錄 0（另清掉 2 個 9/27 空庫稽核遺留的臨時目錄，無內容）；含內容的截圖目錄 content-r1/r2/d1/d2 已改 700/600 僅 root 可讀，未進 repo。

**觀察（未動，供參考）**：日記清單 83 篇一條到底（每卡 88px、首屏 7 張、全長約 8600px），目前沒有月份分段或跳轉；若要處理屬資訊架構，需屋主意見。日曆月標題按鈕高 28px、`nest-switch` 42×24，略低於 32px 觸控建議，屬 Calendar 區未動。
