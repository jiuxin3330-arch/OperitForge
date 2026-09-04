# TICKET-I B1:工具層回填

工單:`/root/nest-memory/TICKET_I_runtime_drift_backport.md`,糯糯 9/2 裁定 B1 開工。
A 段(護欄)見 `NOTES_TICKET_I_A_GUARD_20260902.md`。

目標是讓 patch 源碼能重現 runtime 已經在跑的東西,這樣 build 腳本不再是地雷。
**runtime 一個位元組都沒動**,本段只改 patch 源碼、build 腳本,以及新增 `bridge-extras/`。

---

## 成果:漂移從 7 個降到 4 個

```
回填前:autonomy_tool.py / PERSONA.md / claude.py / easter_egg.py
        main.py / memory_bridge.py / usage.py            ← 7 個

回填後:PERSONA.md / claude.py / easter_egg.py           ← B2,9/15 之後
        main.py(只剩檔尾哨兵的排列,實質內容已相同)
```

`usage.py`、`memory_bridge.py`、`autonomy_tool.py` 現在與 runtime **逐字相同**。

---

## 四條回填

| 條目 | patch 函式 | manifest 旗標 |
|---|---|---|
| usage TOKEN_FILE | `patch_usage_token_file_source` | `usage_token_from_bridge_home` |
| memory_bridge 留言注入 | `patch_memory_bridge_comment_injection_source` | `comment_injection_auto_marked` |
| main PHOTO_ROOT | `patch_main_photo_root_source` | `photo_root_srv_default` |
| main fresh_session | `patch_main_fresh_session_source` | `swap_fresh_session` |

都照 `patch_main_artifact_dir_source()` 的模式:哨兵/目標狀態判冪等、
legacy 形狀變了就 `RuntimeError` 拒絕、runtime 由同一支函式產生。

### `memory_bridge` 那條不只是一行

工單寫的是「memory_bridge 的密鑰路徑」,實際 diff 裡沒有密鑰路徑——
是**裁定①③的整套留言注入機制**(55 行),糯糯裁定時用的詞(COMMENT_CAP)才對得上:

* `_call_wakeup()` 改成回傳 `(text, injected_ids)`,`_refresh()` 跟著收兩個值
* `COMMENT_CAP`(`NEST_WAKEUP_COMMENT_CAP`,預設 0=關)超出上限就折疊,下輪輪替注入
* 檔尾新增 `_call_mark()` 與 `mark_injected_comments()`
* MEMORY_GUIDE 文案跟著改:「只讀不標已讀」→「絕不手動標已讀(注入送達時系統自動標)」

一支 patch 函式做完整套,任一區塊形狀對不上就整條拒絕——半套上去比沒上去更糟。

### usage TOKEN_FILE 是忠實回填,不是改良

runtime 寫死 `/srv/chatnest-next/data/version-bridge/home/.claude_token`。
改成 `os.environ["HOME"]`(像 `_ARTIFACT_DIR` 那樣)明顯更好,但那會讓 runtime 也得跟著改,
而本段的邊界是 runtime 不動。**回填的職責是重現,不是順手改良。**
想改的話那是另一條,列在後續。

---

## diff = 0 逼出來的兩個細節

驗收標準訂成「逐字為零」是對的——它逼出了兩件光看行為看不出來的事。

### 一、哨兵不能想加就加

我第一版照 `artifact_dir` 的模式,在 `usage.py` 檔尾加了
`# CHATNEST_VERSION_BRIDGE_USAGE_TOKEN_V1`。但 runtime 的 `usage.py` **沒有哨兵**
(`memory_bridge.py` 也沒有),加上去之後,重建版與 runtime 的差異就變成
**恰好是那行宣稱兩者相同的註解**。

改成用「目標狀態是否已存在」判冪等。`main.py` 的兩條同理——它只有原本那四個哨兵,
加第五個就會製造出新的漂移。

### 二、main.py 只剩哨兵排列,那要等一次授權重 build

```
build 產出:  CONTEXT → ARTIFACT_DIR → HEARTBEAT → RUNTIME_V1
runtime 現況:CONTEXT → RUNTIME_V1 → HEARTBEAT → ARTIFACT_DIR
```

runtime 的排列是「build 一次、之後熱修兩次」留下的歷史痕跡
(heartbeat 與 artifact_dir 都是後來追加的);build 產出的順序才是規範的。

要對齊只有三條路,兩條走不得:改 build 的 patch 順序會逼 `RUNTIME_V1` 這個
「這份是 build 產物」的總標記不能放最後,結構變得不自然;動 runtime 重排是工單禁止的。

**剩下那條是對的:B 全部收工後跑一次帶 `--overwrite-drifted-runtime` 的重 build。**
那時 runtime 與 build 內容等價,重 build 只是讓註解排列歸位,而且需要重啟 bridge
——所以它是 B 段的收尾動作,不是我現在該做的。

測試裡的比對因此對哨兵排列不敏感(`_sentinel_insensitive`),但對其他每一行都逐字比。

---

## `autonomy_tool.py`:採裁定(乙)

新增 `/srv/chatnest-next/bridge-extras/`,build 多一步把裡面每個 `.py`
複製進 `staging/app/`,並在 manifest 記 sha:

```json
"bridge_extras": {
  "autonomy_tool.py": "ec45e8cf2b1567214ad8ae82fa0153e3b26e757c6b8a2d3a2fc41fced3c50203"
}
```

目錄裡放了 `README.md` 說明它是什麼、為什麼不塞進 patch 源碼的字串
(266 行程式碼該以程式碼的形式存在,能被 import、lint、diff)、
為什麼不回填進 legacy(那邊用不到,只會多一個沒有呼叫者的檔)。

---

## claude.py 留給 B2 —— 這件事要講清楚

`claude.py` 的 54 行差異裡,有些**看起來**屬於 B1:

* `from app.autonomy_tool import autonomy_server, consume_pending_note`
* `from app.memory_bridge import ..., mark_injected_comments, ...`
* `_TOUCH_LOG_PATH` / `_TOUCH_LOCK_PATH` 的 `/root` → `/srv`
* `mcp_servers` 加上 `"autonomy": autonomy_server`

但它們的落點是問題:`asyncio.create_task(mark_injected_comments())` 就在
`build_system_prompt()` **裡面**,緊貼著 `_nest_state_snapshot()`
——那個函式的 docstring 自己寫著「人格敏感區(IMPLEMENTATION 硬規則 15/16)」。
`consume_pending_note()` 同樣在 prompt 組裝的路徑上。

也就是說 B1/B2 的界線在同一個函式內部交錯,要靠行號挑出「這行是接線、那行是語感」,
然後寫兩支保證不重疊的 patch 函式。**在人格區旁邊動刀,出錯的代價和 13 天的等待不成比例。**
整檔留給 B2。

### 由此而來的一件事:B1 完成 ≠ build 產物可以上線

接線在 `claude.py` 裡。沒有它,`autonomy_tool.py` 雖然進了產物卻不會被載入,
`mark_injected_comments()` 也不會被呼叫。

所以現在的 build 產物**仍然不能直接換上去**——而這正好是 A 段護欄在做的事:
現在跑 build 依然會被擋,因為 `claude.py` 還漂移著。護欄不是擋在「全部做完」,
是擋在「還有東西沒回填」,這次它擋對了。

---

## 驗收

### 回填後的 build 比對(實跑)

```
$ python3 scripts/build_version_bridge_runtime.py --target /tmp/final
$ diff -rq /tmp/final runtime/version-bridge-app

Files … app/claude.py differ        ← B2
Files … app/easter_egg.py differ    ← B2
Files … PERSONA.md differ           ← B2
Files … app/main.py differ          ← 只有檔尾哨兵的排列
```

護欄自己報的是 diff 的 +/- 總行數,所以 main.py 那一行顯示「8 行」
——就是那 4 個哨兵各算一加一減:

```
漂移檔案(4 個):
  PERSONA.md —— 內容不同(24 行)
  app/claude.py —— 內容不同(52 行)
  app/easter_egg.py —— 內容不同(46 行)
  app/main.py —— 內容不同(8 行)
```

`usage.py`、`memory_bridge.py`、`autonomy_tool.py` 已不在清單上。

### 測試

`test_version_bridge_runtime_patch.py` 新增 4 條:

* usage / memory_bridge 的回填結果**與 runtime 逐字相同**(不是「看起來對」)
* main 的兩條:套用乾淨、冪等,且 `fresh_session` 必須帶著
  `await get_registry().invalidate(conv_id)`——冷啟不是選配,
  warm actor 會沿用既有 SDK session,讓 `resume=None` 失效
* 四支都要在 legacy 形狀變了時拒絕(沉默略過等於悄悄拿掉一條回填)

`test_version_bridge_build_guard.py` 新增 2 條:

* **B1 驗收**:真跑 build,斷言三個回填檔逐字相同、main.py 忽略哨兵排列後相同、
  剩餘漂移不超出 B2 待辦。這條會隨 B2 收工自然收斂——到時候剩餘漂移是空的,
  斷言仍然成立,不需要回來改測試。
* bridge-extras 會進產物且 manifest 有記 sha

後端全套:**396 passed / 4 failed / 1 skipped**,4 個是既有失敗
(dashboard×2、version_bridge_runtime_patch×2),零新增。

### runtime 沒動

```
app/main.py           84235a5022fb…(本段前 = 本段後)
app/autonomy_tool.py  ec45e8cf2b15…(本段前 = 本段後)
chatnest-version-bridge.service:active,未重啟
```

---

## 回滾點

```
scripts/version_bridge_runtime_patch.py.bak-b1-1788362651
scripts/build_version_bridge_runtime.py.bak-b1-1788362651
```

`bridge-extras/` 是新增目錄,回滾直接刪掉即可(runtime 裡那份才是服役中的)。

## repo 這邊收了什麼

| 檔案 | 說明 |
|---|---|
| `NOTES_TICKET_I_B1_BACKPORT_20260902.md` | 本份 |
| `bridge-extras-README.md` | 新增目錄的設計說明。md5 `58ad540e47134a9e5214dba971b8c316`,與 VPS 上 `bridge-extras/README.md` 相同 |
| `test_version_bridge_build_guard.py` | A 段護欄 + B1 驗收,共 9 條。md5 `567c5fead031c26ea4d3142068700bd8`,與 VPS 相同 |

四支 patch 函式(約 220 行)沒有搬進 repo:它們活在
`scripts/version_bridge_runtime_patch.py` 裡,有 `.bak-b1-1788362651` 回滾點,
每條做了什麼、為什麼這樣做,上面都寫了。
`autonomy_tool.py`(266 行)同理——它在 `bridge-extras/` 是活的,
與 runtime 逐字相同(sha 見上方 manifest 段)。

---

## 後續

1. **B2**(9/15 之後,硬規則 15):`claude.py`、`PERSONA.md`、`easter_egg.py`。
   claude.py 的接線 hunk 一併在那時處理。
2. **B 收尾**:全部回填完之後跑一次帶 `--overwrite-drifted-runtime` 的重 build,
   讓 main.py 的哨兵排列歸位、manifest sha 重簽。要重啟 bridge,請排時間。
3. `usage.py` 的 TOKEN_FILE 可以改用 `$HOME`(與 `_ARTIFACT_DIR` 一致),
   但那會動到 runtime,是獨立的一條。

---

## 補件一(2026-09-05):三支完整檔進 repo

B1 覆核指出「版控」在當時是空話——`/srv/chatnest-next` 的 git 沒有任何 commit,
`bridge-extras/autonomy_tool.py` 與兩支 build/patch 腳本從未 commit 到任何地方,
OperitForge 這邊只有片段。(乙)的意義是「資產在版控」,而現況只做到「資產在磁碟上另一個目錄」。
護欄本身也一樣只活在 VPS 上——它是這顆雷的唯一保險。

比照 `hotfix-20260901/prod/` 慣例,收生產現行版逐位元副本:

| 檔案 | 生產路徑 | md5 |
|---|---|---|
| `prod/autonomy_tool.py` | `/srv/chatnest-next/bridge-extras/autonomy_tool.py` | `76a625380746f00adadb3c5af86aeed4` |
| `prod/build_version_bridge_runtime.py` | `/srv/chatnest-next/scripts/build_version_bridge_runtime.py` | `fe907da60af2e3e72af39305fb1d0311` |
| `prod/version_bridge_runtime_patch.py` | `/srv/chatnest-next/scripts/version_bridge_runtime_patch.py` | `d9e12a7a55154c236ddead43629dce86` |

`autonomy_tool.py` 的 md5 與 B1 覆核親手核對的三份(bridge-extras / staging / runtime)相同,
也就是這份副本同時等於現行 runtime 那一份。
三檔取回後逐位元核對過 md5 與檔案大小(13104 / 14234 / 39933 bytes)。

`prod/` 是副本不是新的事實來源;生產仍在 `/srv/chatnest-next/`。
重新部署或災後重建時以 `prod/` 為準覆蓋回去,md5 對得上就代表沒有漂移。

既有的 `build_guard.added.py` 保留:它帶著「三處接線各插在哪」的說明,
是給讀的人看接法用的,完整檔則是給機器對帳用的。兩者並存不衝突。

**這一項完成後,TICKET-I 才進入「可重 build」狀態**(B2 與收尾重 build 仍排 9/15 後)。
