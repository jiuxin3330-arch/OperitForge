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

---

## 2026-09-29 03:20 台北 — 放手窗：撕取線已恢復上線；整合紀錄頁提案待 Owner 過目

**撕取線恢復**：移除 batch 1 家票券、batch 2 日記紙張兩段覆寫（改為註解），02:43 發佈 `index-C-8VjJeU.js`（index `9b7ccb77…`），快照 `dist.hf-snap-20260929-024322`，vitest 68/326。

**整合紀錄頁（未發佈）**
- 工作方式：正式 `frontend/src` **未改動**。在 `frontend/handsfree/ia-root/frontend`（src 複本、node_modules 連結）開發，改動全部以腳本表達：`ia_patch.py`（主體，每個替換唯一命中否則中止）、`ia_patch2.py`（選日後捲入畫面）、styles.css 尾端「整合紀錄頁」一段、測試。候選 build：`/srv/chatnest-next/reports/handsfree/stage-ia-025339`。
- 設計：日曆為骨架（`data-calendar-lens="emotion"` 保留原格子外觀，格高維持 62px）；格子左下角行程點（最多 2）＋日記方點——位置經幾何量測選在雙貼紙對角／單貼紙置中都不會碰到的角落（重疊 0、壓數字 0）；點日期（再點取消）→ 當天卡（兩人心情唯讀、當天行程、記心情／排行程／寫這天的日記，分別開**原本的**心情 sheet、ScheduleDaySheet、日記編輯器並預填日期），並平滑捲入畫面（尊重減少動態）；下方日記沿用原票卡，改列「本月」或「當天」，作者篩選與寫新日記保留。拿掉：頁位圓點、左右滑、身心／行程鏡片、日曆專用寫入鈕。保留：月份切換、今天（改為直接選取今天）、月標題→情緒色團、「月／週／行程」切換（週＝Timetable 未改，TICKET-M 不在範圍）、經期顯示、日曆蝴蝶。後端與 API 零改動。
- 驗證：工作區 vitest 69 files／331 passed（6 項舊契約改寫為新契約，非 IA 斷言原樣保留；新增 recordPage.test.ts 5 項，3 個變種紅測全抓 → `ia-red.txt`）；分身（**自製示範資料**，demo_seed.py，非真實內容）日夜：頁位圓點 0、鏡片 0、水平溢出 0、超出視窗 0、outline 0、page error 0；當天卡點開後 365px 全在視窗內。
- 過目截圖：`reports/handsfree/ia-review/`（light.png／dark.png 四格總覽＋單張＋README）。
- **上線流程（Owner 點頭後）**：確認正式 src 自分叉後無他人改動（App.tsx 分叉基準 md5 `2dc892d8…`），是則把 ia-root 的 App.tsx／styles.css／4 支測試複製回正式 src；否則在正式 src 上重跑 ia_patch.py＋ia_patch2.py＋CSS 段＋測試改寫 → 全套測試 → hf_build → hf_publish → 更新 FRONTEND_CURRENT_STATE。
- **想要一份新內容種子**：示範資料能驗版面，但 Owner 的真實月份密度（例如一天多篇日記、長標題）用真資料再驗一次最穩。若規劃窗同意，請放新種子，我在發佈前跑一次真實密度量測（只取數字），用完即刪。

---

## 2026-09-29 — 整合紀錄頁 v2（Owner 過目回饋兩項）已重拍，待 Owner 裁定

- ① 寫入入口：當天卡改「點哪裡改哪裡」——糯糯心情格即按鈕（`record-mood-edit`，新擬態 raise-soft，空時「＋ 貼上心情」；牧牧格唯讀 article），行程標題列圓形＋（32px）與行程清單可點，均開原 ScheduleDaySheet；「寫這天的日記」提示列＋當天篇數；FAB 在選日時標籤改「寫這天的日記」並預填日期。標籤旁非功能圖示因無實心版本（鐵律④）改為純文字。移除舊的三顆泛用按鈕。
- ② 篩選：`[['mumu','牧牧'],['nuonuo','糯糯']]`，文字未改；預設 `nuonuo`。附帶：當天日記只在另一位時提示切換（`ia_patch4.py`）。
- 改動腳本：`ia_patch3.py`、`ia_patch4.py`（接在 ia_patch.py／ia_patch2.py 後）＋ styles.css「整合紀錄頁 v2」段＋ recordPage.test.ts 更新。候選 build：`/srv/chatnest-next/reports/handsfree/stage-ia-040010`。
- 驗證：工作區 vitest 69／332；新變種紅測 m4（加回「全部」）、m5（心情格不可點）皆抓到（`ia-red.txt`）；分身示範資料日夜：篩選文字 ['牧牧','糯糯']、當天卡 401px 全在視窗內、點心情格開原心情 sheet、水平溢出 0、超出視窗 0、outline 0、新元件線框 0、page error 0。
- 截圖：`ia-review/`（light.png／dark.png 四格＋單張＋README），v1 移至 `ia-review/v1/`。
- 設計核可後：請發新內容種子做上線前密度驗證（只取數字、用完即刪），再依 NOTES 前段上線流程發佈。

---

## 2026-09-29 — 整合紀錄頁 v3「手帳」（Owner 設計）施工完成，待 Owner 過目

依 Owner 六點設計施工（`ia_patch5.py` 接在 ia_patch1–4 後；styles.css「整合紀錄頁 v3：手帳」段；recordPage.test.ts 改寫為手帳契約 7 項；scheduleUi 一條指向新日記區）。候選 build：`/srv/chatnest-next/reports/handsfree/stage-ia-055415`。v2 狀態備份：`frontend/handsfree/ia-v2-backup/`。

**驗證（分身、示範資料、日夜一致）**：月頁日記區 0、FAB 1；日頁月曆 0、FAB 0；篩選文字 ['牧牧','糯糯'] 寬 [78,78]；左滑 9/6→9/7、右滑→9/6；心情 sheet 開著時左滑日期不變；三入口各開原編輯器（心情 sheet、行程 dialog、日記 composer）；空白天有空貼紙位與「在方格紙上寫下這一天」；返回回月頁；水平溢出 0、超出視窗 0、outline 0、handbook 元件線框 0、page error 0。vitest 69／333；新變種 m6（拿掉減少動態）m7（編輯器開著可翻頁）m8（篩選三格）皆紅（`ia-red.txt`）。截圖：`ia-review/`（兩列七格總覽＋單張＋README），v1／v2 於子資料夾。

**Owner 文字描述未明說、我採保守做法的細節（請確認，不同意即改）**
1. 月頁完全不列日記（原「本月日記」索引拿掉），日記只從日頁進入。若 Owner 仍想在月頁看到月份日記索引，需她指示位置與形式。
2. 日頁頂端除返回外，放了小的「前一天／後一天」箭頭（給無法滑動時用）；屬導覽不屬寫入按鈕。可拿掉只留滑動。
3. 日頁隱藏右下寫日記浮鈕（入口改長在方格紙上）；月頁浮鈕保留＝寫今天。
4. 牧牧貼紙唯讀；兩人的心情短語以小字列在貼紙下方。
5. 月頁「今天」鈕＝回到本月月頁（不直接翻進今天日頁）。
6. 跨月翻頁時月曆月份自動跟著換。
7. 篩選預設「糯糯」，放在方格紙標題列右側。
8. 日期票根上大數字與星期間用虛線撕取線（票券擬物豁免，同 Owner 恢復的撕取線）。
9. 週課表／行程清單仍由月頁上方「月／週／行程」進入（TICKET-M 未動）。

核可後流程同前：新內容種子做密度驗證（只取數字、用完即刪）→ 正式 src 套用 → 全套測試 → 發佈。

---

## 2026-09-29 — 手帳翻紙＋寫入 v4（Owner 兩項新需求合併交付），待 Owner 過目

候選 build：`/srv/chatnest-next/reports/handsfree/stage-ia-062905`。改動接在 ia_patch1–5 後：`ia_patch6.py`（翻紙接線）、`ia_patch7.py`（寫入 v4）、新檔 `src/handbookFlip.ts`、styles.css「手帳翻紙」「手帳寫入 v4：空白就是入口」兩段、新測試 `handbookFlip.test.ts`、`handbookWrite.test.ts`。正式 src 仍未改動、未發佈。

### 一、翻頁調研結論

| 候選 | 授權 | 體積（min / gzip） | 外連 | 結論 |
|---|---|---|---|---|
| page-flip（StPageFlip）2.0.7 | MIT | 43,826 B / 10,288 B，0 依賴 | 原始碼掃描無 URL／fetch／XHR／動態 import | **不收**：要求固定尺寸的頁、所有頁預先渲染、自己接管觸控事件——跟我們長短不一可捲動的日頁、React 管的 DOM、「編輯時不翻頁」守門都會打架。npm 包還夾帶一個 8.8MB 的 video.gif（安裝後 9.39MB，雖不進 bundle）。 |
| react-pageflip 2.0.3 | MIT | 約 1,033 B gzip（外殼，底下仍是 page-flip） | 同上 | **不收**：同上問題，多一層包裝。 |
| turn.js | — | — | — | **不收**：依賴 jQuery。 |
| **CSS 3D 手工輕量翻頁（備案）** | 自寫 | 見下 | 0 | **採用** |

- 做法（`handbookFlip.ts`，約 70 行，零依賴、零網路）：翻頁那一刻把目前這頁「拓印」成一張紙片疊在原位（inert、aria-hidden、不帶 id），紙片以書脊為軸 rotateY 翻開（下一天從左側書脊、前一天從右側），帶紙背陰影與落影，620ms；底下 React 早已換成新的一天。動畫結束紙片即移除，不殘留節點。
- 體積差（對 v3 候選 stage-ia-055415，含寫入 v4 的改動一起算）：JS 598,728→600,756 B（gzip 173,505→174,148，**+643 B**）；CSS 377,130→380,919 B（gzip 65,254→65,898，**+644 B**）。合計約 +1.3KB gzip；若用 page-flip 光本體就 +10.3KB gzip。
- 降級三層：①「減少動態」開啟（系統或 App 內 `data-reduced-motion`）→ 直接跳頁，不播任何動畫（CSS 也另外把紙片 display:none 兜底）；② 低階裝置（≤2 核或 ≤2GB）→ 平移滑動；③ 實測幀率連續兩次低於 40fps → 本次使用期間改用滑動（一次偶發卡頓不算；第一版是一次就降，錄影時太敏感，已改）。
- 效能實測（分身、手機尺寸 390×844、觸控）：這台 VPS 只有 **1 核**，比任何手機都弱，所以讓瀏覽器偽裝成中階手機（8 核／4GB）才會走翻紙路線。錄影中白天 42–51fps、晚上 35–44fps（晚上那段連兩次 <40，第五頁就照規則降成滑動，短片裡看得到）；CDP CPU 降速 4× 量得 41／52／53、6× 量得 27／46／42——動畫只動 transform，在合成層跑，主執行緒降速影響很小。不偽裝時（1 核原生）直接走滑動 ✅。**限制**：手上沒有實體手機，真機體感請 Owner 看片後若有機會在自己手機上試；任何卡頓都會自動降級，不會卡住。
- 既有行為（翻紙版實測）：9/30 左滑 → 10/1，月曆自動換到十月 ✅；10/1 右滑 → 9/30 ✅；心情編輯開著時滑動不翻頁、也不出現紙片 ✅；日記編輯器開著時不翻頁 ✅；返回鍵回月頁 ✅；三入口各開原編輯器 ✅；page error 0。
- 測試：工作區 vitest **71 檔／342 條全綠**；recordPage.test.ts 手帳契約 7 條、scheduleUi／fPolishUi／visualPolish 皆原樣保留未改。新變種紅測 m9（減少動態仍播）m10（一次就降級）m11（拿掉低階機退路）m12（拿掉紙片 CSS 兜底）全抓到（`ia-red.txt`）。

### 二、寫入交互重新設計：「空白就是入口」

出發點：在紙本手帳上，人不會去找按鈕——哪裡有空白就在哪裡下筆。所以每一塊都**永遠留一段空白**，那段空白本身就是入口；已經寫上去的東西點了就是改它。沒有按鈕列、沒有圓形＋、日頁沒有浮動鈕。

- **心情**：自己那格空著時是一個「空貼紙位」，鉛筆記號＋「貼一張今天的心情」；貼了之後點貼紙＝換一張（像撕下重貼）。牧牧那格唯讀，空時寫「還沒貼」。
- **行程**：行程區畫成橫線紙，每件事佔一行；最後永遠留一行空白「寫下一件事…」，整天沒行程時是「這天要做什麼？寫在這一行」。點任何一行都打開原本的行程編輯。
- **日記**：方格紙上的日記票卡照舊；最後留一段空白「接著寫一篇…」；整天沒寫時整張方格紙（至少 168px 高）就是入口「輕點紙面，寫下這一天」，打開原本的日記編輯器、日期已帶好。
- **回饋**：點下去有一圈淡淡的墨水暈開（減少動態時關閉）。所有點擊區 ≥44px 高。
- 編輯器畫面本身一律沒動。

**用 Owner 三準則自評**
1. 使用者體驗：想寫哪一塊就點哪一塊，一步到編輯器、日期自動帶好；翻到別天也不用回月頁。弱點：「空白可以點」第一次不一定看得出來——用鉛筆記號＋一句淡色提示補，已有內容時提示縮成一行不搶戲。
2. 視覺感受：日頁上看到的是紙（票根、貼紙位、橫線紙、方格紙），不是控制項；提示用紙上墨色的淡色小字；橫線與方格是紙張紋理，非分隔框線（版面檢查：handbook 元件線框 0，唯一的線是票根撕取線，屬 Owner 恢復的豁免）。弱點：橫線紙讓行程區比 v3 多一點紋理，若 Owner 覺得雜可改回素面。
3. 是否方便合理：入口永遠在該資訊的正下方，寫完回來就看到自己剛寫的那一行；三個入口行為一致（點空白＝新增、點內容＝修改），學一次通用。弱點：要補寫過去的某天，仍需先在月頁點那天（或連續翻頁）。

**對編輯器的單獨提案（未實作、未夾帶，僅供 Owner 參考）**：日記編輯器若改成「從方格紙往上抽出一張紙」的樣子、心情編輯改成「一張貼紙頁」讓她撕一張貼上，會跟手帳語言更一致。要做再另開一輪。

### 三、請確認的細節（我採的做法，不同意即改）
1. 翻頁方向：後一天＝紙從右往左翻（書脊在左），前一天反過來；上方小箭頭也走同一個翻紙動畫。
2. 降級門檻：40fps、連續兩次；低階機判定 ≤2 核或 ≤2GB。
3. 空白日的方格紙入口高度 168px（約半個螢幕的紙）；有日記時只留一行高的空白。
4. v3 的待確認九點仍然有效（上一段）。

過目素材：`ia-review/`（light.png／dark.png 兩列八格＋單張、`flip-light.webm`／`flip-dark.webm` 翻頁短片、flip.json、hb.json、README），v1／v2／v3 於子資料夾。全部示範資料，非真實內容。核可後流程同前：新內容種子做密度驗證（只取數字、用完即刪）→ 正式 src 套用（**記得連新檔 handbookFlip.ts 一起**）→ 全套測試 → 發佈。

---

## 2026-09-29 — 整合紀錄頁 v5「手帳本」（重新裝訂），待 Owner 過目

候選 build：`/srv/chatnest-next/reports/handsfree/stage-ia-070200`。改動接在 ia_patch1–7 後：`ia_patch8.py`（裝訂）＋ `handbookFlip.ts` 一行（拓印時拿掉章節標籤）＋ styles.css「手帳裝訂」段＋新測試 `handbookBinding.test.ts`。v4 狀態備份：`frontend/handsfree/ia-v4-backup/`。正式 src 仍未改動、未發佈。

### 結構決策
- **三章**：第一章「月計劃」＝月頁（一月一頁）；第二章「週計劃」＝週課表＋行程表兩頁（原本掛在「月／週／行程」切換下的內容整章搬進來，Timetable 元件一行未改）；第三章「筆記」＝日頁＋方格紙日記（v4 的空白入口全部沿用）。
- **章節不另存一份狀態**：由既有狀態推出（有選日期＝筆記、週或行程＝週計劃、其餘＝月計劃），所以舊的行為和測試都不用改，也不會出現「標籤說在 A 章、畫面卻在 B 章」的不一致。
- **側邊章節標籤**：固定在畫面右緣（像活頁手帳的索引標籤），三色取自既有行程色（honey／aqua／blush 淡化）。所在的章那張比較長、顏色比較深，並用 `aria-current="page"` 標示。標籤用陰影浮起、外側圓角、不用框線。頁面右側讓出 16px，實測內容右緣 358px、標籤從 362px 開始，不重疊；水平溢出、超出畫面、outline 都是 0。
- **跳章**：點標籤＝用同一套翻紙往前或往後翻（往後面的章＝往後翻）；標籤本身釘在書邊，不跟著紙翻（拓印時拿掉標籤）。
- **章內翻頁**：
  - 第一章：左右滑＝下個月／上個月（上方的月份箭頭也走翻紙）。
  - 第二章：週課表 ⇄ 行程表兩頁，翻到章尾就停，不會翻出這一章；上方「週／行程」兩顆（沿用原本的切換，拿掉「月」這顆，因為月計劃已經有自己的標籤了）。
  - 第三章：前一天／後一天（原本的行為）。
- **月頁點日期＝跳進第三章那一天**（不留在第一章）。理由：
  - 日頁的主體是那天的筆記（方格紙日記），心情和行程是那頁的頁首。放在筆記章，標籤會亮在「筆記」，她永遠知道自己在哪。
  - 如果日頁留在第一章，第一章就會同時有「月頁」和「日頁」兩種頁，第三章反而沒有自己的東西。
  - 實體手帳也是這樣用：在月計劃看到某天，翻到筆記那一頁去寫。
  - 返回鍵「回到月頁」不變（翻回第一章、停在那天所在的月份）。
- **筆記章記得上次那一天**：直接點「筆記」標籤＝回到上次看的那一天，沒看過就是今天（像夾著書籤）。
- **防誤翻加強**：除了原本「編輯器開著不翻」，另外排除三種情況：從彈出的編輯器（portal）裡滑、在輸入框裡滑、在會橫向捲動的區塊（例如課表）上滑。這樣課表的操作不會被翻頁搶走。
- 週課表頁不跟著月份重掛，TICKET-M 自己的週次狀態不會被翻頁打斷。

### 驗證（分身、示範資料、日夜一致，page error 0）
- 各章實測：
  - 第一章左滑 9 月→10 月、右滑回 9 月。
  - 點「週計劃」→ 週課表；左滑 → 行程表；再左滑停在行程表（章尾）。
  - 點「筆記」→ 今天的日頁。
- 點月曆 9/6 → 筆記章 9/6，後一天 → 9/7；心情編輯開著時滑動，日期不變。
- 回到月頁 → 月計劃 9 月；再點「筆記」→ 回到 9/7（記得）。
- 跨月：9/30 翻後一天 → 10/1，返回 → 月計劃 10 月。
- 減少動態：跳章直接換頁、沒有紙片、日頁動畫 none。
- 效能：
  - 不錄影時翻紙 52–60fps。
  - 錄影時錄影編碼會吃掉 1 核伺服器的 CPU。原尺寸錄影 fps 掉到 23–37，照規則降級成滑動（**降級門檻沒有為了拍片調整**）。
  - 改用 270px 寬錄影後，10 次翻頁全程翻紙，fps 34–51。
- 測試：工作區 vitest **72 檔／349 條全綠**。既有 recordPage／handbookFlip／handbookWrite／scheduleUi／fPolishUi 一條未改；新增 handbookBinding 7 條。新變種紅測 m13–m17 全抓到（`ia-red.txt`）：
  - m13 portal 可翻
  - m14 點日期不翻
  - m15 標籤跟著紙飛
  - m16 課表隨月重掛
  - m17 筆記章忘記上次那天
- 體積（對 v4 stage-ia-062905）：JS gzip 174,148→174,840（+692 B）、CSS gzip 65,898→66,293（+395 B）。

### 請確認的細節（我採的做法，不同意即改）
1. 標籤文字：「月計劃」「週計劃」「筆記」（第二章雖然也含行程表，標籤只寫週計劃，保持短）。
2. 標籤顏色：月＝蜂蜜黃、週＝薄荷綠、筆記＝粉，都是既有行程色的淡版。
3. 月頁點日期＝跳進筆記章（理由見上）；若 Owner 想要點日期留在月計劃章，改一行即可。
4. 第二章兩頁的順序：週課表在前、行程表在後；翻到章尾停住，不會連到下一章。
5. 右下「寫新日記」浮鈕：月計劃章和週計劃章都保留（寫今天）；筆記章照 v4 隱藏（入口長在方格紙上）。
6. v3／v4 的待確認細節仍然有效。

過目素材：`ia-review/`（light.png／dark.png 兩列六格＋單張、`book-light.webm`／`book-dark.webm`、book.json、README），v1–v4 於子資料夾。核可後流程同前：新內容種子做密度驗證 → 正式 src 套用（**handbookFlip.ts 新檔一起**）→ 全套測試 → 發佈。

---

## 2026-09-29 — 整合紀錄頁 v6「印刷手帳內頁」（Owner 四條回饋），待 Owner 過目

候選 build：`/srv/chatnest-next/reports/handsfree/stage-ia-074718`。改動接在 ia_patch1–8 後：`ia_patch9.py`（第二章頁序、刪標題區、頁眉／頁尾／月份排印）、`handbookFlip.ts`（回翻改寫）、styles.css「手帳翻紙」段改回翻樣式＋新增「手帳內頁 v6：印刷版面」段、新測試 `handbookPrint.test.ts`。v5 狀態備份：`frontend/handsfree/ia-v5-backup/`。正式 src 仍未改動、未發佈。

### 四條回饋的做法
1. **第二章頁序**：行程表第一頁、週課表第二頁。點「週計劃」標籤預設翻到行程表；行程表往左滑（前翻）到週課表，章尾停住。上方兩顆切換也改成「行程／週」。
2. **印刷內頁**：每一頁都照市售活頁頁芯的版面語言重畫，功能與資料一概未動。
   - 整頁是一張紙：紙色、左側書脊陰影、右緣露出 22px 桌面，章節標籤從紙邊伸出來。
   - 頁眉：英文欄目字距（MONTHLY／SCHEDULE／WEEKLY／DAILY）＋中文欄目名，下面一條細印刷線；頁尾是頁碼（月頁「— 09 —」、第二章「1 / 2」「2 / 2」、日頁「DAY 272」＝一年中的第幾天）。
   - 月頁：大號襯線月數字＋英文月名＋中文年月；翻月箭頭與「今天」縮成頁角小字。星期列小字，日紅六藍。每格只有細印刷線，日期數字在左上角，今天是實心墨圈。經期／預測與圖例改成頁底註腳。
   - 行程表：一天一列印在橫線上，左欄是襯線日期；行程條從浮起的小卡改成「橫線上的一行字＋左邊一小段色筆記號」。
   - 週課表：只用限定在手帳內的 CSS 換外觀（頁眉排印、格子壓平、細欄線），Timetable 元件一行未改。月份箭頭在這頁不顯示：這頁的課表本來就不跟月份連動，箭頭在這裡按了也沒有作用。
   - 日頁：頁眉是大號襯線日數字＋英文星期＋中文星期與年月，「今天」是斜蓋的紅色小印章。欄位名是中文小字＋英文欄目字（MOOD／PLAN／NOTES）。心情是印好的兩個貼紙圈，行程是印在頁上的橫線欄，方格直接印在頁上。貼上去的日記票卡照舊（Owner 喜歡的樣子不動）。
   - 視覺鐵律：
     - 所有印刷線都用背景漸層畫，是印在紙上的線（同方格紙的擬物豁免），不是用框線當分隔。測試保證這段 CSS 裡沒有任何 border／outline。
     - 沒有大片純色：紙面上都有印刷內容。
     - 沒有尖角。
     - 高亮用淡色調。
3. **標題區刪除**：紀錄頁不再有「寫入與記錄」標題區，整頁交給手帳本；記憶頁的標題照舊。
4. **回翻＝前翻倒放**：
   - 前翻不變：眼前這頁從右緣掀起，沿左側書脊翻過去，新頁在底下。
   - 回翻做法：
     1. 先把眼前這頁拓印成「底頁」壓著。
     2. 等上一頁畫好（約 90ms，讓日頁先回到頁首）後拓印它。
     3. 這張「已翻過的頁」從左緣書脊立起（-92°），向右倒回到 0° 蓋上。
     4. 陰影與落影的時間軸也反過來。
   - 兩個方向用同一條書脊，互為鏡像。
   - 跨章同一邏輯：往後面的章＝前翻，往前面的章＝回翻；返回月頁＝回翻。
   - 減少動態時仍然直接跳頁，底頁也不會建立。

### 驗證（分身、示範資料、日夜一致，page error 0）
- 既有行為全部實測通過：
  - 第一章左右翻月。
  - 第二章：先行程表、左滑到週課表、章尾停住。
  - 點「筆記」→ 今天；點月曆 9/6 → 筆記章 9/6；後一天 → 9/7。
  - 心情編輯開著時不翻頁；返回月頁；筆記章記得上次那天。
  - 跨月 9/30 → 10/1，返回 → 月計劃 10 月。
  - 減少動態：跳章直接換頁、沒有紙片。
- 前翻中途畫面裡只有翻起的紙；回翻中途畫面裡有「底頁＋倒回來的紙」。
- 版面檢查：水平溢出 0、超出畫面 0、outline 0。剩下的線框都是原本就有的：頂欄按鈕、圖例小色塊、日記票卡撕取線。
- 效能：
  - 同一環境對照五種樣式變體，翻頁都在 54–60fps，新的紙張版面沒有讓翻頁變重。
  - 驗貨腳本在翻到一半時截圖，會卡住畫面、讓 fps 掉到 28–32 而觸發降級。這是量測方式造成的，不是產品問題；錄影那輪不在中途截圖。
  - 240px 寬錄影日夜兩段各 10 次全程翻紙（37–56fps）。
- 測試：工作區 vitest **73 檔／354 條全綠**。handbookBinding 有一條斷言照 Owner 新需求改成「行程表在前」，其餘既有測試一條未改；新增 handbookPrint 5 條。新變種紅測 m18–m22 全抓到（`ia-red.txt`）：
  - m18 第二章先開週課表
  - m19 標題區回來
  - m20 回翻像翻開新頁
  - m21 回翻沒有底頁
  - m22 印刷頁用框線
- 體積（對 v5 stage-ia-070200）：JS gzip 174,840→175,409（+569 B）、CSS gzip 66,293→68,220（+1,927 B）。

### 請確認的細節（我採的做法，不同意即改）
1. 頁眉與欄位用英文欄目字（MONTHLY／SCHEDULE／WEEKLY／DAILY、MOOD／PLAN／NOTES）增加印刷感；若 Owner 想全中文，改字即可。
2. 數字字體用系統襯線體（Georgia，Android 退到 Noto Serif），不載入外部字型（零外連）。不同手機的襯線體會略有差異。
3. 星期列日紅六藍；今天用實心墨圈；日頁「今天」是斜蓋的紅色小印章。
4. 頁尾頁碼：月頁「— 09 —」、第二章「1 / 2」「2 / 2」、日頁「DAY 272」。
5. 週課表頁不顯示月份箭頭（理由見上）。
6. 回翻比前翻晚約 90ms 開始（等上一頁畫好再拓印），體感上是「手先碰到紙、紙才立起來」。
7. v3～v5 的待確認細節仍然有效。

過目素材：`ia-review/`（light.png／dark.png 兩列八格＋單張、`book-light.webm`／`book-dark.webm`、book.json、README），v1–v5 於子資料夾。核可後流程同前：新內容種子做密度驗證 → 正式 src 套用（**handbookFlip.ts 新檔一起**）→ 全套測試 → 發佈。

---

## 2026-09-29 08:26 — 手帳本正式發佈（Owner 終審通過）

- **Owner 唯一修改**：拿掉標籤側紙邊陰影（`.panel[data-handbook-chapter]` 背景第二層漸層），書脊陰影保留。標籤陰影改成只往右落（負擴散），不溢到紙面。自驗方式是日夜各三章的截圖逐像素量：無標籤列的紙色一路平到 367px，368px 起是桌面或標籤本體；夜間最多差 4 個亮度級、只有 3 列（反鋸齒）。
- **自驗時抓到的上線前問題**：`.panel[data-testid="dashboard-panel"]` 的進場動畫 `nest-detail-in … both`，播完後 transform 仍掛在 panel 上，導致 `position: fixed` 的章節標籤跟著內容捲走（筆記頁捲 359px 時標籤 top 變成 -209）。修法：只在手帳頁 `animation-fill-mode: backwards`；修後捲到底標籤仍在 150／234／318。
- **真實密度驗證**（新種子，只取數字，`density-real-20260929.json`，無日期、無文字）：
  - 第一次量到 5 個月中有 3 個月各有 18–26 張貼紙被格子右緣裁切、4–10 個元素超出內容區。原因是讓出標籤空間後格子約 49px，貼紙 27px 放不下兩張。
  - 手帳內月曆貼紙改成 23px 後重量：5 個月／3 頁行程表／最密 6 天，溢出 0、裁切 0、page error 0。
  - 種子檔已刪；分身資料庫在暫存資料夾隨結束刪除；殘留的 /tmp/hf-clone-* 已清。
- **發佈**：
  - 正式 src 與分叉基準一致（App.tsx md5 2dc892d8；styles.css 為工作區版本的前綴），直接搬入 11 個檔（App.tsx、styles.css、handbookFlip.ts、8 支測試）。原檔備份在 `reports/handsfree/archive/src-backup-prepublish-20260929-082418/`。
  - 工作區與各版備份從 `frontend/handsfree/` 移到 `reports/handsfree/archive/`：它們的舊測試會被正式 vitest 掃到而誤報。移走後正式 frontend vitest **73 檔／357 條全綠**。
  - `hf_build.sh` → `stage-20260929-082549`，bundle hash 與分身驗過的 `stage-ia-082225` 相同（JS `index-D9Hlem5r.js`、CSS `index-BohBgwSw.css`）。
  - `hf_publish.sh` 快照 `dist.hf-snap-20260929-082629`（前一版 `index-C-8VjJeU.js`，保留 3 份）。
- **版本指紋**（hf_check）：本機與公網 index sha256 前綴都是 `14033c6dfeabec76`，bundle `index-D9Hlem5r.js`，回滾卡在 bundle 內（1），health 200。救生頁 `/rollback.html` 兩端匿名皆 401（由後端 data/static 提供，不在 dist，發佈不影響）。
- `docs/FRONTEND_CURRENT_STATE.md` 已加本次紀錄（原檔備份 `reports/handsfree/FRONTEND_CURRENT_STATE.md.bak-20260929`）。
- 回滾：設定頁回滾卡或 `/rollback.html` 會換回 `dist.hf-snap-20260929-082629`，也就是撕取線恢復那一版。

---

## 2026-09-29 09:19 — 手帳微調上線（Owner 真機回饋四條）

- **① 配色**：參考收藏頁訊息卡色帶（淺色全彩 #9CD9C9／#FFC9C9，夜間 30% 混色）。
  - 章節標籤：淺色未選 86%、選中 100% 色；夜間未選 36%、選中 58% 色，選中那張配深墨字 #1f2420。
  - 週課表課程色塊（只在手帳內）：淺色 88%、夜間 60%。夜間配深墨字，保證讀得清楚。
- **② 切換膠囊方形底**：原因是 `.record-view-switch` 有底色但圓角 0。改成透明、圓角 999px、兩顆之間留 4px 間距。
- **③ 導覽列下方方框**：`.workspace` 底部原本固定讓出 82px（`--nest-nav-height`），這條露出 app-shell 的底色。
  - 修法：新增 `float-nav` class，只加在 chat／work／emotions 以外的頁面。這些頁的內容延伸到畫面底，`.panel` 底部留出導覽高度＋24px。
  - 聊天、工作、情緒總覽維持原本的保留帶，因為聊天輸入框需要。
  - 分身各頁捲到底抽查（日夜一致）：家 39px、收藏 396px、記憶 305px、設定 34px、紀錄頁 84px，都在膠囊之上；聊天 workspace 仍到 762px；水平溢出 0、page error 0。
- **④ 行程↔週課表**：同章換視圖改為 `data-turn="swap"`，140ms 淡入加 4px 上浮，按鈕和滑動都一樣，不建立翻紙紙片。減少動態時是 `none`，直接切。跨章、翻月、翻日仍是翻紙（實測都有紙片）。
- **測試**：正式 frontend vitest **74 檔／361 條全綠**。handbookPrint 一條斷言照新需求改成 swap；新增 handbookTweak 4 條。
- **發佈**：
  - `stage-20260929-091628`；快照 `dist.hf-snap-20260929-091919`（前一版 `index-D9Hlem5r.js`）。
  - src 原檔備份：`reports/handsfree/archive/src-backup-pre-tweak-20260929-091146/`。
- **版本指紋**（hf_check）：本機與公網 index sha256 都是 `cd350489dbc954cb`，bundle `index-CFvURgFg.js`，回滾卡在 bundle 內，health 200。救生頁兩端匿名 401。
- **尚未驗到的一點**：週課表色塊的實際顏色，示範資料沒有課表可以量，只由測試保證 CSS 規則存在。若 Owner 覺得課表色還不夠，可以再往上調。
