# 預覽修法(乙):artifact 三路不同源

規格:`/root/nest-memory/VPS_AUDIT_20260901.md`「預覽修法:糯糯裁定 **(乙) 正式修法**」節。
糯糯 9/2 裁定執行。五項全部完成並上線。

起因是糯糯 9/1 15:41 那句「看不了…預覽失敗…可能是之前改了什麼通道卡住ㄌ」——
她的直覺是對的,8/17 搬家降權之後 artifact 的三條路各自為政:

| 位置 | 路徑 | 內容(修之前) |
|---|---|---|
| cn 實際存檔 | `$HOME/artifacts/` | catch-butterfly.html(9/1) |
| bridge 端點讀 | runtime app 目錄旁 | 不存在 |
| legacy 端點讀 | `full-stack/artifacts/` | 4 個歷史檔,停在 8/20 |

cn 沒做錯:他的 `HOME` 是 `<data>/version-bridge/home`,cwd 是 runtime app 目錄,
寫相對路徑 `artifacts/x.html` 就落在 HOME 下。是端點找錯地方。

---

## ① bridge:`_ARTIFACT_DIR` 改由 env 取 `$HOME/artifacts`

```python
# 之前
_ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts"
# 之後
_ARTIFACT_DIR = Path(os.environ.get("HOME") or Path(__file__).resolve().parent.parent) / "artifacts"
```

沒有 `HOME` 時退回原本的相對路徑,不會變成讀根目錄——這條有測試鎖住。

**熱修同步進 patch 源碼**(工單要求):新增
`scripts/version_bridge_runtime_patch.py` 的 `patch_main_artifact_dir_source()`,
掛進 `build_version_bridge_runtime.py` 的 main.py patch 鏈,
manifest 加旗標 `artifact_dir_from_home`。

runtime 那一份**不是手打的**,是直接呼叫同一支 patch 函式改的
(`patch_main_artifact_dir_source(runtime_source)`),
所以 runtime 與 patch 源碼逐字一致,不會出現「兩邊看起來像但差一個空格」。

---

## ⚠ 施工中發現:runtime 與 patch 源碼已經漂移,現在重 build 會炸生產

這件事比本工單本身重要,**請規劃窗優先處理**。

我原本想用 `build_version_bridge_runtime.py` 重 build 一份、直接換掉 runtime,
那是最乾淨的做法。動手前先 build 到臨時目錄比對——**對不上**:

| 檔案 | 差異 |
|---|---|
| `app/main.py` | 5 個 hunk。其中包含 Swap MVP(8/31)的 `fresh_session` 欄位與冷啟邏輯、`PHOTO_ROOT` 的 `/srv` vs `/root` |
| `app/claude.py` | 54 行 |
| `app/memory_bridge.py` | 57 行 |
| `app/easter_egg.py` | 48 行 |
| `app/usage.py` | 4 行 |
| `app/autonomy_tool.py` | **只在 runtime 有,build 出來沒有** |
| `PERSONA.md` | 26 行 |

也就是說:**現在任何人執行 `build_version_bridge_runtime.py`,
Swap MVP 的換窗機制與 autonomy_tool 會當場消失。**

「runtime 熱修一律同步進 patch 源碼」這條規矩是對的,但現況是它沒被完全遵守,
債累積到「重 build = 生產事故」的程度。這不在本工單範圍,我沒有動它——
把未同步的熱修一條條補進 patch 源碼是一張獨立的單,而且要逐條確認意圖,
不是我能順手做的。

**所以本工單的 runtime 改動是針對性熱修,不是重 build。**臨時 build 目錄已刪。

---

## ② backend:`/api/v2/artifact/{name}` 改轉打 bridge

新增 `VersionBridgeGateway`(`backend/app/gateways.py`),端點改用它。

保留了規格要求的兩件事:`ARTIFACT_NAME_RE`(`^[\w.-]{1,160}\.html$`,防路徑穿越)
與 `MAX_ARTIFACT_CHARS` 截斷,`fake_models` 分支也原樣不動。

三個設計選擇:

* **白名單只有一條** `VERSION_BRIDGE_PREFIXES = ("artifact",)`。
  這條 gateway 是為預覽開的,不是通用 bridge 代理。有測試鎖住
  `chat` / `sessions` / `profile` 都會被擋成 404。
* **從 `LEGACY_PREFIXES` 移除 `"artifact"`**。留著它,
  `/api/v2/legacy/artifact/...` 就還是一條通往舊目錄的回頭路——
  那正是這次要修掉的「同一個檔名兩個來源」。查過前端與測試都沒有人用。
  這一項規格沒點名,是我加的,理由如上,可推翻。
* **401 自動重新認證**(見下方踩坑二,理由跟我一開始寫的不一樣)。

理由(規格原話):bridge 以 chatagent 讀自己的 HOME 天經地義,
**不需要讓 root 的 backend 跨界讀 cn 的 0700 私有目錄**——不新增權限走廊。

---

## ③ 歷史檔:複製過去,原檔留著

4 個檔(`anniversary_4months` 7/17 四個月紀念、`mumu_phone` 8/19 手機模擬器、
`qixi_late_gift` 8/20 七夕遲來禮物、`test`)已進
`$HOME/artifacts/`,`chown chatagent:chatagent`、`chmod 600`,
與既有的 catch-butterfly.html 對齊。`cp -p` 保留原始 mtime。

**規格寫「搬」,我做的是「複製」**,legacy 那邊的原檔沒有刪。理由:

1. 9/1 決策紀錄有一條「只停服務,**不刪任何檔案**」,這幾個是糯糯的紀念品
2. 新路徑萬一有問題,原檔還在,回滾只是改回一行
3. 「搬」要達成的目的是讓新端點讀得到,複製就達成了
4. 不會有「兩份分歧」的老問題:legacy 那條路已經沒有呼叫者了(見 ② 白名單)

要真的刪原檔請規劃窗明示,我不會自己決定刪糯糯的東西。

---

## ④ 驗收

`verify_artifact_chain.py`:用**生產同一支 gateway、同一組憑證**,
實際打 bridge 取檔。不是 monkeypatch。
VPS 上在 `/srv/chatnest-next/scripts/verify_artifact_chain.py`,
與本目錄那一份 md5 相同(`ef86b095225a2bbe69be8636802c69f0`),隨時可重跑。

```
PASS catch-butterfly.html          10687 chars — 9/1 新檔,原本打不開的那張
PASS mumu_phone.html               16834 chars — 8/19 手機模擬器(回歸)
PASS anniversary_4months.html       4893 chars — 7/17 四個月紀念(回歸)
PASS qixi_late_gift.html            6233 chars — 8/20 七夕遲來禮物(回歸)
PASS test.html                       230 chars — test
PASS 白名單擋下 chat / sessions / profile (404)
PASS 不存在的 artifact 回 404
RESULT=OK
```

bridge 端點層另外直接驗過:5 個檔全 200,
`../../etc/passwd` → 404、`notes.txt` → 400(檔名規則仍在擋)。

**糯糯還沒在真機上點過。**技術面通了,她那一關才是驗收。

### 測試

```
後端全套:383 passed / 4 failed / 1 skipped
          4 個是既有失敗(dashboard×2、version_bridge_runtime_patch×2),零新增
本工單新增 6 條,全綠
```

反向對照:改動前 `test_real_artifact_proxy_filters_contract` 打的是
`legacy_gateway`,改完立刻紅(`assert 503 == 200`)——證明端點真的換了來源,
不是改了註解而已。

前端零改動(端點路徑沒變,`MarkdownView.tsx:127` 照舊)。

---

## ⑤ chatnest.service:**仍有活躍依賴,不可停用**

規格寫「HTML 預覽是它目前唯一已知的活躍用途」。**實測推翻這個假設。**

近 24 小時 legacy(8787)的真實請求:

```
    105  /api/models          ← 來自 127.0.0.1(backend)
     16  /api/usage
      9  /api/auth
      3  /
      2  /api/stackchan/photos  ← 今天上午下線前的殘留
      1  /api/voice/<key>
```

backend 還有 6 個 `legacy_gateway.request` 呼叫點:通用 proxy
(`/api/v2/legacy/{path}`)、`voice/{key}`、`models`、`usage`、`growth`、`growth/review`。
`models` 每天上百次,是活的。

順帶一個佐證:`/api/artifact` 七天內只有 6 次,而且全都發生在預覽壞掉的期間
——那是糯糯試著點開卻失敗的次數。修好之後這條路也不會再回到 legacy 了。

**結論:維持啟動。**要停 chatnest.service,得先把 models/usage/voice/growth
這四條搬走或本地化,那是另一張單。

---

## 兩個踩坑(都是我自己實測抓到的,不是糯糯撞到)

### 一、build 從錯的目錄跑

`vite build` 那次是上一張單的,這次是 `build_version_bridge_runtime.py`——
差點就直接重 build 覆蓋 runtime。**先比對再套用**救了這一次,
比對出來的東西見上面那段紅字。

### 二、我給 401 重試寫了一個錯的理由

我加了「token 被拒就重新認證」,註解寫的是「bridge 會重啟並換發 token」。
聽起來很合理,所以我差點就這樣交出去了。

實測:真的把 bridge 重啟一次,再用同一個 gateway 取檔——**成功,而且 token 沒換**。

查源碼才知道 bridge 的 token 是 `HMAC(CHAT_SECRET, "chat-v1")` 的固定值,
沒有效期,重啟會算出同一個。我的理由是錯的。

那段邏輯我留著,因為真正會讓 token 失效的情境確實存在(輪替 `CHAT_SECRET`),
而且那時沒有它就得重啟 backend 才能修好。但**註解與測試名稱都改成真的**了:

```python
# The bridge token is HMAC(CHAT_SECRET, "chat-v1"): no expiry, and a restart
# re-derives the same value. What does invalidate it is rotating CHAT_SECRET —
# and without this retry the cached token would then stay wrong until this
# process restarts too.
```

留一個理由是錯的註解,比沒有註解更糟——下一個人會照著錯的心智模型往下推。

(`LegacyGateway` 有一模一樣的「快取 token 不處理 401」問題,是既有債,
不在本工單範圍,列為後續小單。)

---

## 佈版與回滾

改動檔案:

```
scripts/version_bridge_runtime_patch.py        + patch_main_artifact_dir_source()
scripts/build_version_bridge_runtime.py        + 掛進 patch 鏈 + manifest 旗標
runtime/version-bridge-app/app/main.py         熱修一行(用上面那支函式產生)
backend/app/gateways.py                        + VersionBridgeGateway,- LEGACY_PREFIXES 的 artifact
backend/app/main.py                            端點改打 bridge
backend/tests/test_artifacts.py                改 1 條 + 新增 4 條
backend/tests/test_version_bridge_runtime_patch.py  新增 2 條
```

回滾點(VPS):`*.bak-preview-1788340030`
(patch 腳本、build 腳本、gateways.py、backend main.py、runtime main.py、兩個測試檔)。

歷史檔的原檔仍在 `/srv/chatnest/full-stack/artifacts/`,回滾不需要動它們。

重啟過:`chatnest-version-bridge.service`、`chatnest-next.service`。
`chatnest.service` 依 ⑤ 維持啟動。

---

## 後續小單(不在本工單,列給規劃窗)

1. **runtime ↔ patch 源碼的漂移**(最優先,見上方紅字)。在補完之前,
   `build_version_bridge_runtime.py` 等同於一顆地雷。
2. `LEGACY_PREFIXES` 還留著 `stackchan/photos`,而那些端點今天上午已下線,
   現在是條死路。
3. `LegacyGateway` 的 token 快取同樣不處理 401。
4. 要停 chatnest.service 的話,先處理 models / usage / voice / growth 四條。
