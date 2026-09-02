# TICKET-H 第 4 項:舊 StackChan 面板下線

前四輪的 NOTES(後端管線／畫面／驗收後兩點修改／刪除回 500)在
`claude/hotfix-backport-security-exposure-sfghdw` 分支的 `ticket-h/NOTES_TICKET_H_20260902.md`。
這一份只講第 4 項。

裁定來源:糯糯 9/2 上午(工單 R1)——**併入相簿、廢棄獨立面板、單一入口**。
前提「於相簿功能驗收通過後移除」已成立:第三輪真機驗收「測過了!立刻出現✦」,
第四輪把刪除的 500 修掉之後,收藏與刪除都能用。

---

## 下線了什麼

| 目標 | 位置(下線前) | 處置 |
|---|---|---|
| `StackChanPanel` | `App.tsx:8113`–`8195` | 移除(83 行) |
| `view === "stackchan"` 路由分支 | `App.tsx:10107` | 移除 |
| `View` 型別的 `"stackchan"` | `App.tsx:220` | 移除 |
| `/api/v2/stackchan/photos*` 五個端點 | `main.py:8740`–`8856` | 移除 |
| `_stackchan_legacy_response()` | `main.py:8726` | 移除(只服務那五個端點) |
| `backend/app/stackchan_contract.py` | 整檔 151 行 | 刪除(見下方判斷) |
| 面板專屬 CSS | `styles.css`×10 條、`interaction.css`×3 處 | 移除 |
| 測端點的兩條測試 | `test_stackchan_push.py:39,91` | 移除 |

新增兩組合約測試鎖住下線(見「驗收」)。

---

## 拆之前:確認沒有別的呼叫者

工單特別點名要先驗證 cn 的 MCP 工具不經此端點。驗了,**確實不經**:

```
/root/stackchan-mcp/server.py:16
PHOTO_ROOT = Path("/root/mumu-server/photos")
PENDING_PHOTOS = PHOTO_ROOT / "pending"
SAVED_PHOTOS   = PHOTO_ROOT / "saved"
```

stackchan-mcp 直接讀寫磁碟目錄,沒有任何 HTTP 呼叫指向 chatnest-next 的 8790。
`/root/stackchan-mcp/` 與 `/root/mumu-server/` 全樹搜尋 `v2/stackchan` 與 `8790`,
命中全是 numpy 測試資料 csv 裡的十六進位巧合(`0x...8790...`),沒有一筆是真的呼叫。

下線前的完整呼叫者清單只有兩個,都在這次一起處理:

* `App.tsx` 的 `StackChanPanel`(8120／8135／8138／8144／8177)
* `backend/tests/test_stackchan_push.py` 的兩條測試

`ota_server.py`(拍照落地)與 stackchan-mcp 的 keep/delete/60 天清除三條路徑一條都沒碰,
與第一段對帳的設計前提一致:**磁碟是唯一事實來源**。

---

## 一個順手查出來的事實:那個面板早就進不去

`view` 的初始值只認一種網址參數:

```tsx
// App.tsx:8624(下線前)
const [view, setView] = useState<View>(() =>
  new URLSearchParams(window.location.search).get("view") === "emotions" ? "emotions" : "chat");
```

`?view=stackchan` 會被判成 `chat`,沒有 localStorage 持久化,全檔也沒有任何
`setView("stackchan")`。導覽列(`App.tsx:9880` 六顆、底部列)都沒有它。

也就是說 `view === "stackchan"` 這個條件**永遠不會為真**——那個面板是一段
已經沒有入口的死碼。所以:

* 「單一入口」其實早就是現狀,只是程式碼還留著
* 這次下線對糯糯看得到的畫面是**零改變**,不是移走她可能在用的東西
* 也因此沒有「舊網址失效」的風險要處理:`?view=stackchan` 下線前後都是進聊天

---

## 一個在部署之後才抓到的錯(這輪的踩坑紀錄)

第一版的下線測試我寫的是「五個端點都回 404」。**測試全綠,部署後實測卻是 200。**

原因:`main.py:9966` 有一個只在前端 dist 存在時才註冊的 SPA fallback

```python
@app.get("/{path:path}", include_in_schema=False)
```

它會接住所有不存在的 GET 回 `index.html`(對 `/api/v2/there-is-no-such-thing`
也一樣回 200 HTML)。測試環境沒有 dist,fallback 沒註冊,同一個請求才是 404。

**我的斷言綠在一個生產不成立的前提上**——跟前四輪那三次同一個形狀:
施工者身在被施工的系統之內,用推論代替實測。這是第四次。
差別只在這次是我自己部署後實測抓到的,不是糯糯撞到的。

改法:把斷言鎖在**兩種環境都成立的事實**上——路由表裡沒有這些路徑:

```python
live = [r.path for r in fastapi_app.routes
        if getattr(r, "path", "").startswith("/api/v2/stackchan")]
assert live == []
```

非 GET 方法沒有 fallback 可躲,照樣驗行為(404 或 405);GET 則只斷言
「回的東西裡沒有照片清單」,不寫死狀態碼也不寫死 content-type
(測試環境的 404 回的是 `application/json` 的 detail,生產回的是 HTML)。

教訓寫成一句放在測試的註解裡:**硬寫 404 會綠在測試環境、卻描述不了生產,
那就不是在測這件事。**

---

## 幾個我自己下的判斷(都可以推翻)

* **`stackchan_contract.py` 整檔刪掉。** 它是「代理 legacy 照片 API 時的消毒層」,
  唯二用者是那五個端點與測它們的測試。端點沒了,它保護的攻擊面就不存在了。
  留著一個沒有呼叫者的模組,只會讓下一個窗口以為端點還在。要撈回來 git 有。
* **前端 `stackchanPush.ts` 不動**,只把 App.tsx 的三個 import 拿掉。
  跟後端不對稱,理由是那個檔案主體是推播(還活著),而 `isStackChanPhotoData`
  有自己的獨立單元測試 `stackchanPush.test.ts` 在鎖「私有路徑不准外洩」。
  為了清死型別去動一個活著的檔案和它的安全測試,風險與收益不成比例。
* **CSS 共用選擇器只摘掉 stackchan,保留 `.push-actions`。**
  `.stackchan-tabs, .stackchan-actions, .push-actions { ... }` 這種規則有三處,
  整條刪掉會連推播面板一起弄壞。合約測試補了一條鎖住 `.push-actions` 還在。
* **`test_stackchan_push.py` 檔名不改。** 現在裡面只剩推播測試,檔名確實誤導,
  但改檔名是純粹的整理、不在工單範圍,列為後續小單。
* **文案仍然不改。** 沿用第一段的裁定。

---

## 驗收

### 反向對照(拆掉改動,新測試必須變紅)

前端 11 條裡新加的 5 條:

```
還原 App.tsx / styles.css / interaction.css / main.py
→ Tests  5 failed | 6 passed (11)      ← 新加的 5 條全紅,既有 6 條仍綠
```

後端那條(第一版,鎖 404):

```
AssertionError: GET /api/v2/stackchan/photos 還活著
assert 200 == 404
```

後端那條(改寫後,鎖路由表):

```
AssertionError: 舊的 StackChan 照片端點又回來了:
['/api/v2/stackchan/photos', '/api/v2/stackchan/photos/{photo_id}/image',
 '/api/v2/stackchan/photos/{photo_id}/keep', '/api/v2/stackchan/photos/{photo_id}/category',
 '/api/v2/stackchan/photos/{photo_id}']
```

### 測試

```
前端:Test Files 65 passed (65) / Tests 313 passed (313)
     基準線 65 檔 308 條 → +5 條下線合約,零回歸

後端:4 failed, 376 passed, 1 skipped
     那 4 個是既有失敗:dashboard×2、version_bridge_runtime_patch×2
     (NOTES 記的基準線是 5 個,多的那個 screenshot_worker 從 repo 根跑會過,
      這次是從根加 PYTHONPATH 跑的)
     零新增失敗
```

後端要從 repo 根加 `PYTHONPATH=/srv/chatnest-next/backend` 跑,
直接 `pytest backend/tests` 會 28 個 collection error(`No module named 'app'`),
那是路徑問題不是壞掉。

### 生產實測(重啟後,對真的跑著的服務)

```
openapi.json 含 stackchan 的路由:無
相簿路由 9 條全在(/api/v2/gallery、/photos/{id}、/photos/{id}/image …)

POST   /api/v2/stackchan/photos/{id}/keep      → 405
PATCH  /api/v2/stackchan/photos/{id}/category  → 405
DELETE /api/v2/stackchan/photos/{id}           → 405
GET    /api/v2/stackchan/photos                → 200 text/html(SPA fallback,不是照片資料)

sw:chatnest-next-shell-v161
dist bundle 內 stackchan-panel / api/v2/stackchan/photos 命中:0
```

### 相簿沒有被弄壞

```
磁碟 pending 9 + saved 2 = 11
相簿 DB stackchan permanent=0 → 9、permanent=1 → 2 = 11
```

兩邊對齊,零死卡。對帳迴圈與 systemd 沙箱 drop-in
(`ReadWritePaths=/srv/mumu-server/photos`)重啟後都還在。

---

## 佈版

`sw` 版號 **v160 → v161**,兩處都改(`public/sw.js` 的 `SHELL_CACHE`、
`src/main.tsx` 的 `register("/sw.js?v=161")`),`pwa.test.ts` 會擋只改一處。

前端 build 要**從 `frontend/` 目錄**跑(`npm run build`)。
從專案根跑 `vite build --config frontend/vite.config.ts` 會
`[UNRESOLVED_ENTRY] Cannot resolve entry module index.html`——
入口是相對於 root 解析的。(這次踩到了,dist 沒被破壞,重跑就好。)

回滾點:

```
frontend/dist.prev-sw160-prepanelretire
frontend/src/App.tsx.bak-panelretire-1788328380
frontend/src/styles.css.bak-panelretire-1788328380
frontend/src/interaction.css.bak-panelretire-1788328380
backend/app/main.py.bak-panelretire-1788328380
backend/app/stackchan_contract.py.bak-panelretire-1788328380   ← 刪掉的模組原檔
backend/tests/test_stackchan_push.py.bak-panelretire-1788328380
```

repo 這邊 `panel-retire/` 收了三份:

| 檔案 | 說明 |
|---|---|
| `stackchan_contract.py.removed` | 被刪模組的完整原檔。md5 `b3821b57b52a49cef00911acfb5a6290`,與 VPS 上的 `.bak-panelretire-1788328380` 相同 |
| `test_stackchan_gallery.added.py` | 新增的後端合約測試(實際附加在 `backend/tests/test_stackchan_gallery.py` 檔尾) |
| `stackchanGalleryUi.added.test.ts` | 新增的前端合約測試(實際附加在 `frontend/src/stackchanGalleryUi.test.ts` 檔尾) |

各檔的完整 diff 沒有進 repo(改動是刪除為主,`.bak` 就在 VPS 上,路徑如上)。
真正不可再生的只有那個被整檔刪掉的模組,所以只收它。

---

## 沒做的事

* legacy chatnest(`/srv/chatnest/full-stack`)自己的 `stackchan/photos` 端點
  維持原狀。下線的是 chatnest-next 對它的**代理**,不是它本身;
  那是另一個系統,誰在用要另外盤。
* `frontend/src/stackchanPush.ts` 的 StackChan 型別與 `isStackChanPhotoData`
  維持原狀(理由見上)。
* 沒有順手美化任何畫面。這次的畫面改變量是零。
