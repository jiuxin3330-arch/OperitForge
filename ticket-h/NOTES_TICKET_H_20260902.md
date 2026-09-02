# TICKET-H:StackChan 照片進相簿

第一段(後端管線)與第二段(畫面,糯糯 9/2 蓋章後)都已上線。
第二段的內容見文末「第二段」。

工單:`/root/nest-memory/TICKET_H_stackchan_photos_to_gallery.md`(含 R1 修訂)
Owner 設計意圖(原話,以此為準):**「只要拍了沒有立刻刪除就要進相簿ㄛ！」**

分兩段做:先後端管線(工程),畫面等糯糯蓋章後才上線。兩段都完成了。

---

## 做法:對帳,不是在拍照當下推一筆

StackChan 照片有三條會改變狀態的路徑:

| 路徑 | 誰做的 |
|---|---|
| ① 拍照落地 → `pending/` | `ota_server.py` 的 `_store_pending_photo()` |
| ② keep(`pending/`→`saved/`)/ delete | stackchan-mcp 的 `stackchan_photo_keep` / `_delete` |
| ③ 60 天到期直接刪檔 | stackchan-mcp 的 `_cleanup_expired_pending()` |

要在每一條上都掛「順便通知相簿」,就等於改動 StackChan 既有行為
——**工單邊界明文禁止**——而且只要漏掉一條,相簿就會留下指向已刪檔案的死卡。

所以改成單向對帳:**磁碟是唯一事實來源,相簿跟著它走。**

* 三條路徑一條都不用改
* 漏了會在下一輪自動補回來(自癒)
* 「回填既有 12 張」不是特例,只是第一次跑而已

反方向(相簿按永久收藏／刪除 → 實體檔)由 `set_permanent_on_disk()` /
`delete_on_disk()` 在端點裡同步,寫完後下一輪對帳確認兩邊一致
——就算寫回失敗,狀態也只是回到磁碟說的那個,不會兩邊各說各話。

## 交付檔案

| 檔案 | 說明 |
|---|---|
| `prod/stackchan_gallery.py` | 新模組。對帳 + 反向寫回。生產路徑 `backend/app/` |
| `prod/main.py.ticket-h.diff` | main.py 的五處接線 + PATCH 寫回 + 新的 DELETE 端點 |
| `tests/test_stackchan_gallery.py` | 22 條測試(21 passed, 1 skipped) |
| `tests/conftest.snippet.txt` | 測試隔離用的一行環境變數(見下) |

repo 這兩份與 VPS 上的 md5 相同(`fe7e9aa7…` / `dbe202a1…`)。

## 驗收

### 生命週期實測(用合成照片,沒有動真的相機)

| 步驟 | 結果 |
|---|---|
| 放一張進 `pending/` | 60 秒內出現在相簿,`permanent=0`(暫存),note = 拍照當下的提問 |
| cn 用**真的** `stackchan_photo_keep` | 相簿轉 `permanent=1` |
| cn 用**真的** `stackchan_photo_delete` | 相簿資料列消失、相簿的檔案也收掉、磁碟兩邊皆無 —— **無死卡** |

### 回填

12 張全部到位:`permanent=0` 10 張(含 9/1 逛寶雅 10 張)、`permanent=1` 2 張。
磁碟 12 ↔ 相簿 12,完全對齊。

### 測試

```
$ pytest tests/test_stackchan_gallery.py -q
21 passed, 1 skipped
```

全套回歸有做**基準線比對**(把改動前的 main.py 放進另一棵樹跑同一批):

```
改動前:5 failed
改動後:5 failed, 365 passed   ← 同樣那 5 個,零新增失敗,+17 條新測試
```

那 5 個既有失敗是 dashboard×2、screenshot_worker×1、version_bridge_runtime_patch×2,
與本工單無關(其中 version_bridge 那兩個也順帶證明:9/2 早上為方案 B 改的
`claude.py` 沒有弄壞它們——它們改動前就在失敗)。

---

## 三件與工單描述不同的事實(實測)

### 1. 那筆「7/20 遺留」不是孤兒

工單寫「相簿內唯一 1 筆 stackchan(7/20)為遺留」。實際上它**有 `source_ref`
(`20260720T165515Z_1e58bbd3fd`),而且檔案還在 `saved/`**。
對帳正確地把它認出來:沒有重複新增,也沒有誤刪。

不過測試仍保留 `test_legacy_row_without_source_ref_is_never_touched`,
鎖住「沒有 source_ref 的資料列不准被當成『磁碟上被刪掉的』而移除」——
那是這支程式最容易造成不可逆傷害的地方。

### 2. R1 的「永久收藏」相簿早就有了

`App.tsx:7718` 的 `togglePermanent` 已經在做 `PATCH {permanent}`,
lightbox 也已顯示「永久收藏／暫存」,分組選項也已經有「來源」與「收藏狀態」。

所以 **R1 真正缺的新 UI 只有「刪除」一個**。本次已把後端補齊:
`PATCH` 現在會把 stackchan 照片的永久／暫存寫回實體檔,
`DELETE /api/v2/gallery/photos/{id}` 也建好了,按鈕在第二段補上。

### 3. ⑤ 的文案現在已經名副其實,建議不改

空狀態那句是「還沒有收藏照片。聊天照片與 StackChan 照片都會集中在這裡。」
工單自己寫的是「功能接上後 7708 那句才名副其實;若第 1 項延後,先改文案」。
第 1 項已經接上,這句話現在是**真的**。

依「只改她點名的」這條紀律,我沒有動它。要不要改語氣請糯糯裁示。

---

## 幾個我自己下的判斷(都可以推翻)

* **`DELETE` 端點只開放 `source_type='stackchan'`**,其他來源回 400。
  相簿本來就沒有任何刪除功能;chat 照片還牽涉訊息附件,開放與否是另一個決定,
  不該搭本工單的便車偷渡進去。
* **「改為暫存」會重設檔案 mtime。** stackchan-mcp 的 60 天清除比對的是
  **檔案 mtime,不是 `expires_at`**。不重設的話,一張放很久的照片被改回暫存,
  下一次清除就會直接消失——那不是「改回暫存」該有的意思。改成從現在起重算 60 天。
* **安全閥:照片目錄整個讀不到時,對帳直接放棄。** 掛載掉、路徑改了、服務搬家
  都會讓掃描結果變成空的,照著做就是把相簿裡的 StackChan 照片全部刪光。
  分不出「真的一張都沒有」和「根本讀不到」的時候,寧可什麼都不做。
* **照片根目錄改成讀 `STACKCHAN_PHOTO_ROOT`。** 這不是為了好看:
  第一版把路徑寫死在 import 當下,結果背景對帳迴圈在**測試啟動 app 時**
  去讀了真正的 `/srv/mumu-server/photos`,把 12 張生產照片灌進測試資料庫,
  弄壞三個既有測試。背景工作不該伸手到設定範圍以外。
  `backend/tests/conftest.py` 加一行把它指到 tmp。

## 已知限制

* **不是即時,是幾十秒。** 後端對帳 30 秒一輪、前端輪詢 20 秒,最壞約 50 秒。
  要真的即時就得在拍照當下推一筆,那會回到「改動 StackChan 既有行為」的問題。
* **對帳目前是靜音的。** app 沒有設定 logging,root logger 預設 WARNING,
  所以 `logger.info` 的那行對帳摘要不會進 journal。一個會刪資料列的工作
  完全沒有紀錄並不理想,但補 logging 設定會影響整個 backend,不在本工單範圍
  ——列為後續小單。
* **軟上限:塞不下就跳過,下一輪再試。** 不硬塞,更不會因為塞不進相簿就去刪磁碟。

---

## 為什麼分兩段

`CLAUDE.md` 的工程/視覺工作紀律(糯糯 9/1 立,硬規定):

> 視覺部分是糯糯的雷點:謹慎、嚴肅、仔細。流程是打樣(mock)→ 她蓋章 → 才上線;
> 只改她點名的。

R1 剩下的三件事都是畫面:

1. 相簿裡的「刪除」按鈕(唯一真正新增的 UI)
2. `StackChanPanel`(App.tsx:8065)與 `view==="stackchan"`(10059)移除
3. `/api/v2/stackchan/photos*` 端點下線(需先確認無其他呼叫者)

第 1 項先打樣給糯糯蓋章(她選了 B 案,見下)。第 2、3 項工單自己也寫了
「**於相簿功能驗收通過後**移除」——要等她先在真機上確認拍照真的會進來、
能收藏能刪,才動舊面板。

---

# 第二段:畫面(糯糯 9/2 蓋章後上線)

打樣先發,糯糯裁定 **B 案**、**動作鍵只留 icon 不要文字**、**刪除鍵放最左**
(她是右撇,拇指自然落在右側,最左最不容易誤觸)。文案確定不改。

## 做了什麼

| 項目 | 內容 |
|---|---|
| 刪除鍵 | `previewPhoto.source.kind === "stackchan"` 才出現,放在動作列最前 |
| 確認 | 展開 `.photo-delete-confirm`,寫明「StackChan 上的檔案也會一起消失」 |
| icon 化 | 四顆動作鍵移除 `<span>` 文字,名稱改走 `aria-label` + `title`,觸控面積維持 46×46 |
| 換照片 | `previewPhoto.id` 一變就把確認收起來,不讓上一張按到一半的狀態黏過去 |

`trash` icon 與「icon-only + aria-label + title」的寫法都是 codebase 既有的
(`App.tsx:5439` 的捨棄草稿鍵就是這樣),沒有新造。

## 糯糯回報的真問題:要殺 app 重開才看得到新照片

這代表**驗收其實沒過**——她的標準是「零操作就看到」。

根因:相簿只在元件掛載時抓一次(`useEffect(..., [load, onStatus])`),之後不再抓。
所以她盯著相簿看,照片也不會自己出現。她的測試照片
(`早安拍照測試！看看眼前有什麼！`)其實**早就進到相簿資料裡了**,只是畫面沒更新
——管線是通的,卡在前端。

修法照 2026-08-18 聊天視圖那次的既有做法(`App.tsx:9276` 的註解寫的正是同一個問題:
「只能殺掉重開」),回前台就重載;**再加一個看得見時的輪詢**,因為驗收情境是
「拍一張,什麼都不做,盯著相簿看它出現」,那時 `visibilitychange` 根本不會觸發。

* 前端輪詢 20 秒(只在 `visibilityState === "visible"` 時打)
* 後端對帳從 60 秒改成 30 秒
* 最壞情況約 50 秒會出現,通常 25 秒左右

輪詢是我加的,糯糯沒點名。理由是不加就達不到她說的「零操作」;不想要的話拿掉一行就好。

## 測試

新增 `frontend/src/stackchanGalleryUi.test.ts`,5 條合約測試鎖住:
刪除鍵只對 StackChan 出現且在最左、動作鍵沒有文字但有 aria-label/title、
確認條與換照片時的狀態重設、自動刷新的三個 listener、後端只讓 stackchan 被刪。

```
$ npx --prefix frontend vitest run --root frontend
Test Files  65 passed (65)
     Tests  307 passed (307)
```

(基準線是 64 檔 302 條;新增 1 檔 5 條,零回歸。)

**測試要從專案根 `/srv/chatnest-next` 跑**,不是從 `frontend/`——那些合約測試用
`resolve(process.cwd(), "frontend", "src")` 找檔案,在 `frontend/` 底下跑會有 16 個檔
ENOENT 失敗,那是跑錯目錄不是真的壞掉。

## 佈版

`sw` 版號 **v158 → v159**,兩處都要改,`pwa.test.ts` 會擋:

```
public/sw.js   SHELL_CACHE = "chatnest-next-shell-v159"
src/main.tsx   register("/sw.js?v=159")
```

我第一次只改了 `sw.js`,合約測試立刻抓出來——這條測試存在的意義就在這裡。

回滾點:`frontend/dist.prev-sw158-preticketh`、
`src/App.tsx.bak-ticketh-*`、`src/styles.css.bak-ticketh-*`、
`backend/app/main.py.bak-ticketh-*`。

## 還沒做:舊面板下線

`StackChanPanel`(App.tsx:8065)與 `view==="stackchan"` 分支、
`/api/v2/stackchan/photos*` 端點的移除,工單寫明要「相簿功能驗收通過後」才動。
等糯糯在真機上確認拍照會自己出現、能收藏能刪,再拆。

---

## 第三輪(9/2 驗收後的兩點修改,已上線)

糯糯真機驗收:**「測過了！立刻出現✦」**——第一段的驗收標準過了。
同時提兩點修改,都已照做上線(sw v159 → **v160**)。

### 1. 確認卡片的框線:整條刪掉

原話:「提示的這個框線要刪喔！完全不能出現！就是純平面 無邊框的卡片」

`.photo-delete-confirm` 的 `box-shadow: inset 0 0 0 1px var(--nest-line)` 移除。

### 2. 按鈕:拿掉新擬態突起

原話:「按鍵再縮小一點 或者直接刪除新擬態突起也可以 icon完全不用動」

二擇一,選了**拿掉突起**——跟她同一則訊息裡要的「純平面」方向一致,
而且拿掉之後按鈕的視覺份量自然就輕了,不必再縮尺寸。

層次改成只靠色階,不用陰影也不用邊框:

* 動作鍵 → `--nest-surface`(比 lightbox 的 `--nest-bg` 亮一階)
* 確認卡片 → `--nest-surface`
* 卡片**裡面**的兩顆按鈕 → 反向用 `--nest-bg`,一樣靠色階分層

拿掉突起之後補了三件事,不補會出問題:

| 補什麼 | 為什麼 |
|---|---|
| 按壓回饋改成底色加深 | 原本的凹陷 inset 陰影也是新擬態,一起拿掉了 |
| 鍵盤聚焦改用 `outline` | 既有規則有 `outline: 0`,靠陰影表示聚焦;沒有陰影就完全看不出焦點在哪 |
| 尺寸維持 46×46、icon 維持 19px | 她說「icon完全不用動」;二擇一已經選了拿掉突起 |

實作放在既有規則**之後**覆寫(特異性相同、靠順序取勝),回滾只要刪掉那一段。
`.collection-photo-action` 全檔只用在相簿 lightbox 這一處,確認過不會波及別的元件。

### 測試

合約測試補一條 `動作鍵與確認卡片是純平面`,鎖住:確認卡片區塊內不得出現
`box-shadow` 或 `border`(`border-radius` 除外)、按鈕的 `box-shadow: none`、
以及聚焦的 outline 有補上。

```
Test Files  65 passed (65)
     Tests  308 passed (308)
```

### 範圍

糯糯:「更進一步的美化是美化窗的工作」——所以只做這兩點,沒有順手調別的。
