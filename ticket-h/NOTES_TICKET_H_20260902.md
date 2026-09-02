# TICKET-H:StackChan 照片進相簿 —— 第一段(後端管線)交付

工單:`/root/nest-memory/TICKET_H_stackchan_photos_to_gallery.md`(含 R1 修訂)
Owner 設計意圖(原話,以此為準):**「只要拍了沒有立刻刪除就要進相簿ㄛ！」**

本次交付**只有後端管線**,沒有動任何畫面。理由見文末「為什麼分兩段」。

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
`DELETE /api/v2/gallery/photos/{id}` 也建好了——**但按鈕還沒做**(見文末)。

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

* **延遲最多 60 秒。** 對帳迴圈的間隔。「拍一張就出現」不是即時,是一分鐘內。
  要更快就得在拍照當下推一筆,那會回到「改動 StackChan 既有行為」的問題。
* **對帳目前是靜音的。** app 沒有設定 logging,root logger 預設 WARNING,
  所以 `logger.info` 的那行對帳摘要不會進 journal。一個會刪資料列的工作
  完全沒有紀錄並不理想,但補 logging 設定會影響整個 backend,不在本工單範圍
  ——列為後續小單。
* **軟上限:塞不下就跳過,下一輪再試。** 不硬塞,更不會因為塞不進相簿就去刪磁碟。

---

## 為什麼分兩段:第二段(畫面)還沒做

`CLAUDE.md` 的工程/視覺工作紀律(糯糯 9/1 立,硬規定):

> 視覺部分是糯糯的雷點:謹慎、嚴肅、仔細。流程是打樣(mock)→ 她蓋章 → 才上線;
> 只改她點名的。

R1 剩下的三件事都是畫面:

1. 相簿裡的「刪除」按鈕(唯一真正新增的 UI)
2. `StackChanPanel`(App.tsx:8065)與 `view==="stackchan"`(10059)移除
3. `/api/v2/stackchan/photos*` 端點下線(需先確認無其他呼叫者)

第 1 項要先打樣給糯糯蓋章。第 2、3 項工單自己也寫了「**於相簿功能驗收通過後**移除」
——所以要等她先在相簿裡確認拍照真的會進來、能收藏能刪,才動舊面板。

順序建議:糯糯先驗收本段(拍一張,看它自己出現)→ 刪除按鈕打樣蓋章 → 上線 →
再拆舊面板與端點。
