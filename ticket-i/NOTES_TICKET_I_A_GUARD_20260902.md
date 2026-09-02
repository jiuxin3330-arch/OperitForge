# TICKET-I A 段:build 腳本的漂移護欄

工單:`/root/nest-memory/TICKET_I_runtime_drift_backport.md`
本份只涵蓋 **A 段(護欄)**。B 段回填未動。

那顆雷是預覽修法(乙)施工中發現的:`runtime/version-bridge-app` 領先 patch 源碼很多,
而 `build_version_bridge_runtime.py` 沒有任何護欄——任何人跑一次,
Swap MVP 的換窗機制與 `autonomy_tool.py` 就當場消失。

今天沒炸,是因為我動手前先 build 到臨時目錄比對。**這次把那個動作變成腳本自己會做的事。**

---

## 做法:比對「將要寫入的內容」與「現行 runtime」,不是只比 manifest sha

工單寫的是「比對 runtime 各檔 sha 與 manifest」。照字面做**達不到驗收要求**:

`runtime-manifest.json` 只記四個檔的 sha(`main` / `actor` / `claude` / `store`)。
實測現行 runtime,只有 `main.py` 與 `claude.py` 兩個對不上——**抓到 2 個,
而驗收要的是 ≥7**。更要命的是 `autonomy_tool.py`:它只存在於 runtime,
manifest 裡根本沒有它的位置,靠比 sha 永遠看不見它,
而它正是「這次寫入會被刪掉」的那一個。

所以護欄比的是 staging(即將寫入的內容)與 target(現行 runtime)本身:

| 情況 | 判定 |
|---|---|
| 兩邊都有、內容不同 | 漂移,報幾行 |
| 只在 runtime 有 | 漂移,「這次寫入會刪掉它」 |
| 只在 staging 有 | 不是漂移(新增) |

`manifest` 的 sha 比對留著當**補充信號**——manifest 自己說謊這件事本身值得講,
而且那是規劃窗當初發現問題的線索。

### 備份檔不進主清單

第一版跑出來 21 個漂移檔,其中 15 個是 `.bak-*`。
build 本來就用 `ignore_patterns("__pycache__", "*.pyc", "*.bak*")` 排除它們,
staging 裡沒有是**預期行為**,不是漂移。混進主清單只會讓十幾個施工回滾點
淹掉真正該看的那幾個。

改成:主清單排除備份檔,另外用一行摘要提「另有 N 個 .bak 也會一起消失,
build 本來就不收它們,不算漂移,但那是別人的回滾點」。

移出之後正好是 **7 個**,與工單列的清單完全吻合。

---

## 拒絕時長什麼樣(對現行 runtime 實跑)

```
拒絕覆蓋:現行 runtime 領先 patch 源碼,這次寫入會弄丟下面這些改動。

漂移檔案(7 個):
  app/autonomy_tool.py —— 只在 runtime 有,這次寫入會刪掉它
  PERSONA.md —— 內容不同(24 行)
  app/claude.py —— 內容不同(52 行)
  app/easter_egg.py —— 內容不同(46 行)
  app/main.py —— 內容不同(19 行)
  app/memory_bridge.py —— 內容不同(55 行)
  app/usage.py —— 內容不同(2 行)

manifest 自己記的 sha 也已經對不上:
  app/main.py —— manifest 記 db312efc57d3…,實際 84235a5022fb…
  app/claude.py —— manifest 記 a12d5a76e513…,實際 4da5036b047c…

(另有 19 個 .bak 備份檔也會一起消失。build 本來就不收它們,不算漂移,
 但那是別人的回滾點。)

這些差異要先回填進 patch 源碼(每條一支 patch 函式 + manifest 旗標,
runtime 由同一支函式產生,不要手打),回填完這裡自然就不再擋。
詳見 TICKET-I:/root/nest-memory/TICKET_I_runtime_drift_backport.md

要對照差異,build 產物留在:/srv/chatnest-next/runtime/version-bridge-app.staging
確定要覆蓋(差異都已回填)才加 --overwrite-drifted-runtime。
```

離開碼 1。訊息指向工單,也指出 staging 在哪——B 段每條回填都要
「臨時 build diff runtime 為零」,那份產物正好拿來對照。

---

## 驗收:三條路徑都實跑過

| 情境 | 結果 |
|---|---|
| 對**現行生產 runtime** 跑,不帶旗標 | 被擋,列出 7 個漂移檔(上方原文),離開碼 1 |
| target 不存在(首次 build) | 放行,離開碼 0,runtime 正常建立 |
| 有漂移 + `--overwrite-drifted-runtime` | 放行並確實覆蓋掉漂移內容 |

後兩條用臨時 target(`/tmp/ti-test`)做,沒碰生產。

**生產 runtime 全程未動**,前後 sha 相同:

```
app/main.py           84235a5022fb…(跑護欄前 = 跑護欄後)
app/autonomy_tool.py  ec45e8cf2b15…(跑護欄前 = 跑護欄後)
```

被擋的那次也驗過 target 內容原封不動(漂移的檔還在、改動還在)。

### 測試

新增 `backend/tests/test_version_bridge_build_guard.py`,7 條:

* 內容相同 → 無漂移
* target 不存在 → 無漂移(首次 build 不該被擋)
* 內容不同 → 報出檔名與行數
* 只在 runtime 有 → 報「會刪掉它」(`autonomy_tool.py` 那一類)
* `.bak` / `.pyc` 不算漂移但要計數
* manifest 說謊要被指出來
* **端到端**:真的用 subprocess 跑腳本三次(建立 → 製造漂移被擋 → 帶旗標放行),
  並斷言被擋那次 target 原封不動

端到端那條只花 0.19 秒,我一開始不信,查了才確認:source 是 2.6MB,
SSD 上就是這麼快,而且產物有 5 個 patch 哨兵。
不過我還是把「產物必須是 patch 過的」寫成斷言了——不然它可能哪天變成
一條「空跑也會過」的測試,而我不會知道。

後端全套:**390 passed / 4 failed / 1 skipped**,4 個是既有失敗
(dashboard×2、version_bridge_runtime_patch×2),零新增。

---

## 邊界

照工單:**純腳本層,沒有重 build、沒有重啟任何服務、runtime 一個位元組都沒動。**

`/srv/chatnest-next/runtime/version-bridge-app.staging` 留著沒刪
(護欄擋下時的 build 產物)。服務指向的是 `version-bridge-app`,不會誤用到它;
B 段回填時每條都要跟它 diff,留著比較省事。要清掉隨時可以 `rm -rf`。

回滾點:`scripts/build_version_bridge_runtime.py.bak-ticketi-1788350391`

repo 這邊 `ticket-i/` 收了兩份:

| 檔案 | 說明 |
|---|---|
| `build_guard.added.py` | 護欄本體與三處接線(檔頭 import、插入位置、main() 裡的擋法) |
| `test_version_bridge_build_guard.py` | 7 條測試。md5 `ce4aff9f802a3bb942020ef2b4bc8dc6`,與 VPS 上 `backend/tests/` 那份相同 |

---

## B 段還沒做

- **B1 工具層**(盲測期可做):`autonomy_tool.py`、`usage.py`、
  `memory_bridge.py` 的密鑰路徑、`PHOTO_ROOT`、Swap MVP `fresh_session`。
  `artifact_dir` 已於預覽修法(乙)完成,可作範本。
- **B2 人格敏感區**(9/15 之後、硬規則 15):`claude.py` 的 prompt 組裝、
  `PERSONA.md`、`easter_egg.py`。

A 段上線之後,那顆雷已經踩不到了——B 段可以照自己的節奏做,不必再趕。
