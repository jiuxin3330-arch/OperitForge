# 第三批:VPS 瘦身(2026-09-06,盲測期,純服務層)

規格:`/root/nest-memory/VPS_AUDIT_20260901.md` 第二、三節,以覆核後的訂正為準。
邊界:不碰 bridge、不碰 prompt、不重啟 bridge。實際只重啟了 `chatnest-next`(backend),
其餘都是服務層開關與 unit 設定。

起因回顧:9/1 逛街時連續兩次 `adapter_unavailable`,2GB RAM 已用 1.2GB、swap 吃掉 1.4GB。
第一批處理了對外暴露(比記憶體更嚴重),第二批是方案 B,這一批才輪到記憶體本身。

---

## 前後對照

| | 施工前 23:00 | 完工 23:50 | 差 |
|---|---|---|---|
| Mem used | 973 MB | **635 MB** | **−338 MB** |
| Mem available | 988 MB | **1326 MB** | +338 MB |
| free | 266 MB | 524 MB | +258 MB |
| Swap used | 1390 MB | 1337 MB | −53 MB |

**swap 只降 53MB 是預期的,不是沒效**:已經換出去的分頁不會因為記憶體變寬鬆就自己換回來,
它們要等下次被存取才回到 RAM。swap 真正會不會降下來、會不會再爬回去,得看一週曲線
(見下方「一週觀察」),不是看今晚這一格數字。尖峰 508MB 的那個常駐 chromium 已經不在了,
這是這次最大的一筆——它不會出現在「當下 used」裡,但會出現在「尖峰時會不會爆」裡。

單一服務的 `MemoryCurrent` 前後不宜直接相減:施工過程中跑了兩輪完整 pytest,
核心在壓力下回收了不少頁,anchor 從 297MB 掉到 57MB 再回到 172MB 都只是這個效應。
會逐時記錄的 `swap_watch.csv` 才是判斷依據。

---

## ① 停用服務 + 收回 ufw

一律 `stop` + `disable`,**沒有刪除任何檔案**。

| 服務 | 施工前 | 現在 | 備註 |
|---|---|---|---|
| mumu-panel | 23 MB | inactive/disabled | 近 5 天全部是掃描器 |
| mumu-chat | 11 MB | inactive/disabled | 同上 |
| multipathd | 19 MB | inactive/disabled | 另停 `multipathd.socket`(見下) |
| fwupd | 23 MB | inactive/**masked** | 見下 |
| udisks2 | 2.6 MB | inactive/**masked** | 見下 |
| upower | 0.8 MB | inactive/**masked** | 見下 |
| ModemManager | 0.5 MB | inactive/disabled | |
| memory-dashboard | — | 本來就已停 | 3000 埠一併收回 |

**自己驗過才停**,沒有只照工單:撈 mumu-panel / mumu-chat 近 5 天的日誌,
請求全是 `zgrab`、`/boaform/admin/formLogin`、`/geoserver/web/`、vite 探測這類掃描,
來源 IP 沒有一個是糯糯家的 42.70.9.248。

### 兩件工單沒寫、但不做就等於沒做的事

1. **`multipathd.socket`**:`disable --now multipathd` 時 systemd 自己提醒
   「triggering units are still active: multipathd.socket」。socket 還開著,
   有人連就會把服務叫回來。一併停掉,服務才真的停住。
2. **`fwupd` / `udisks2` / `upower` 是 dbus-activated**:`disable` 只擋開機自啟,
   擋不住「有人查 dbus 就拉起來」。停完當下三個都是 inactive,但 50 分鐘後回頭看,
   udisks2 與 upower 又活了。工單寫的是 disable,而 disable 達不到工單要的效果,
   所以改用 `mask`——它是建立一個指向 /dev/null 的 symlink,**不刪任何檔案、可 unmask**,
   與工單「不刪檔案、留回滾指令」的意圖一致。fwupd 本身是 `static`(根本不能 disable),
   也只能用 mask。VPS 沒有韌體、磁碟陣列、電池可管,mask 掉沒有副作用。

### ufw

收回 `3000`、`8080`、`8888`;`8000`、`8003` 保留(StackChan 實體裝置從糯糯家 IP 打進來)、`22` 保留。

```
現在:22/tcp、8000/tcp、8003/tcp(v4 + v6),Status: active
```

---

## ② screenshot-worker 改按需啟動

**功能沒有停用**(8/07 起 6 筆 job 全部 completed,是好的);停掉的是「24 小時常駐 + 每 15 秒輪詢」。

### 做法

```
backend 派 job → 立觸發檔 /srv/chatnest-next/data/screenshot-trigger/pending
              → chatnest-screenshot-worker.path 拉起 worker
              → worker 跑完 queue、空閒 60 秒 → exit 0
```

- **backend**(`_signal_screenshot_worker`):建 job 的 transaction 之後立觸發檔。
  只有一處 `INSERT INTO screenshot_jobs`,先 grep 過確認沒有第二處。
  立不起來不擋 job 建立,但一定 `logger.warning` ——TICKET-K 的教訓是 except 自吞會沒人發現。
- **worker.mjs**:多一個 `idleExitMs`(預設 60 秒)。連續空閒滿 60 秒就跳出迴圈、正常結束。
  留這 60 秒是為了讓連續幾張截圖共用同一個 chromium,不必每張重開。
- **`.path` 用 `PathExists` 而不是 `PathModified`**:事件型觸發會在 worker 執行期間漏掉
  (systemd 在 unit 啟動後就停止監看);狀態型不會——worker 退出時檔案若還在,會立刻再啟動一次。
  worker 的 `ExecStartPre` 負責把觸發檔收掉,讓下一次派 job 能重新觸發。
- **`Restart` 改 `no`**:按需模式下,啟動即失敗(例如 backend 正在重啟)會變成每 3 秒一次的重試迴圈。
- **安全網 timer**(每 30 分鐘):用唯讀連線數一次 `state='queued'`,有才立觸發檔。
  成本是一次 sqlite SELECT,不是把 chromium 叫起來。它存在的理由是:
  觸發檔那條路徑若壞掉,job 會安靜卡在 queued——不能只有一條路徑,而且不能沒人發現。

### 驗收

| 驗證 | 結果 |
|---|---|
| 端到端(打 cn 用的同一支工具 API `/api/v2/tools/mumu/screenshots`) | job 6 秒內 `completed` |
| 閒置時無 worker / node / chromium | ✅(見下方量測方式) |
| 空閒後自動退出 | 62 秒後 `inactive`,exit code 0 |
| worker 執行中再派一個 job | 兩個都 completed(PathExists 的重來機制有效) |
| 安全網 | 見下 |

**安全網驗了兩次,因為第一次不算數。** 第一次「停掉 .path、刪掉觸發檔、跑安全網、job 完成」看起來過了,
但當時 worker 還活著(前一個測試的 60 秒空閒期內)——job 可能是那個還活著的 worker 自己撿的,
安全網的功勞沒有被證明。重驗:先等 worker 完全退出、確認沒有任何 node 進程,再造同樣的故障,
**靜置 40 秒確認 job 一直是 queued**(先證明「真的沒人會撿」),然後才放安全網進來 → 立回觸發檔 → 6 秒完成。
綠得太快先懷疑自己,對自己寫的驗證也適用。

### 施工中抓到自己造成的回歸

改完之後跑完整 pytest,途中 `pgrep` 看到 worker 與 chromium 活著。
原因:觸發檔路徑寫成 **import 時就定案的常數**,測試 `monkeypatch` 不掉,
於是測試替生產立了觸發檔,systemd 把生產 worker 拉起來對著生產 backend 空轉 60 秒。

同一支 conftest 早就把 `STACKCHAN_PHOTO_ROOT` 指到 tmp,理由寫得很清楚
(「不指到 tmp 的話,測試啟動 app 就會把生產照片灌進測試資料庫」)。同一種坑我又踩了一次。
修法:路徑改成**呼叫時才讀環境變數**,conftest 加一行指到 tmp。修完重跑,測試期間生產側乾淨。

---

## ③ memory-dashboard 目錄 1.6G(只評估,不刪,交糯糯裁定)

```
/root/memory-dashboard           1.6 G
└── venv/lib/python3.12/site-packages   1.6 G
    ├── torch                     746 M
    ├── scipy                     111 M
    ├── transformers               98 M
    ├── sympy                      74 M
    ├── chromadb_rust_bindings     57 M
    ├── onnxruntime                55 M
    ├── sklearn                    47 M
    ├── numpy + numpy.libs         70 M
    └── kubernetes                 36 M
非 venv 的部分合計 < 1 MB(main.py、diary.json 94K、mood.json、notes.json、幾個 .bak)
```

- **1.6G 幾乎全是 venv**,而且是 chromadb 拖進來的一整套 ML 依賴(torch 就佔了 746M)。
- 服務已停用,**這 1.6G 不佔記憶體,只佔磁碟**。磁碟現況 `52G 用 19G(38%)`,不緊張。
- 資料檔(diary/mood/notes)是內容資產,很小,不動。查過沒有別的程式讀它們。

**三個選項,等糯糯裁定:**

| | 做法 | 省下 | 代價 |
|---|---|---|---|
| 甲 | 什麼都不做 | 0 | 磁碟還很寬裕,這是合理的預設 |
| 乙 | venv 打包成 `venv.tar.zst` 移到 backups/,原目錄留資料檔 | 約 1.0–1.2 G | 要復活服務時得解壓 |
| 丙 | 刪掉 venv(保留 requirements) | 1.6 G | 要復活得重建 venv(需要網路、下載 torch) |

我的意見:**甲**。磁碟壓力不存在,而 lantern 這類 ML 依賴重建一次很貴。
真的要清,乙 比 丙 好——差別只是「解壓」和「重下載 746M」。

---

## ④ 清理

### backend/app 的 .bak

13 個 `.bak-*` 移走 10 個到 `/root/chatnest-next/backups/app-bak-20260906/`(**移動,不是刪除**,共 2.7M)。
原地保留 3 個而不是工單寫的 2 個:

- `main.py.bak-slim3-1788707128` —— 本次施工的回滾點,必須留在原地
- `main.py.bak-preview-1788340030`、`gateways.py.bak-preview-1788340030` —— 9/2 預覽修法那批,最近的既有回滾點

(`cp -a` 會保留 mtime,所以 `ls -t` 排序會騙人;是照檔名裡的時間戳與「哪一批」判斷的。)

### 陳舊測試

施工前:**395 collected + 2 collection error + 6 failed**。
施工後:**400 passed, 1 skipped, 0 failed, 0 error**。

| 問題 | 真正的原因 | 修法 |
|---|---|---|
| 2 個 collection error | `from scripts import migrate_legacy_*`——那兩支腳本住在專案根 `scripts/`,但從 backend/ 起跑時 `scripts` 解析到 `backend/scripts/` | 照同目錄既有寫法把根 scripts 加進 sys.path 再 import |
| dashboard mood ×2 | 8/25 糯糯裁定 emoji 通道關閉(端點回 410),測試沒跟上 | 改成鎖「已關閉」:410 + detail 指向 emotions,並斷言 DB 真的沒寫進去 |
| worker.mjs 讀不到 | 用相對路徑 `Path('workers/screenshot/worker.mjs')` | 改成相對於測試檔的絕對路徑 |
| runtime_patch ×2 | 期待產物含 `/root/chatnest-next/...`,但 8/17 搬家後 patch 寫的是 `/srv/...` | 測試改鎖 `/srv`(功能沒壞,runtime 裡兩段都在,是測試鎖著搬家前的字面值) |
| build_guard ×1 | 漂移多了 `models.json` | 加進 B2_PENDING 並註明它是「待部署」不是「待回填」(TICKET-I 補件二) |

**沒有一條是用 skip 混過去的**——五條都查到真因才改。

### legacy_preview_smoke.py:226

`ANCHOR_MCP_URL` 預設值停在方案 B 之前的 `/mcp`,現在打會 404
(實測:`/mcp-<KEY>` → 200,`/mcp` → 404)。改成跟 bridge 的 `mcp_local_url()` 同一套規則:
讀 `runtime/mcp-keys/`,讀不到才退回舊路徑並印警告(不靜默)。兩條路徑都實測過。

---

## ⑤ chatnest.service

**保留,沒動。** 9/2 覆核已推翻「可停」的假設(`/api/models` 每日近百次來自 backend)。

---

## 一週觀察

`nest-swap-watch.timer`(每小時)→ `/srv/nest-memory/health/swap_watch.csv`:

```
ts,mem_used_mb,mem_avail_mb,buffcache_mb,swap_used_mb,swap_free_mb,anchor_mb,bridge_mb,next_mb,worker_mb,hands_mb
```

以 `nestmemory` 身分跑,寫進 health/——那個目錄底下的檔案身分要一致
(TICKET-K 第五種形狀:root 建的檔在 nestmemory 的目錄裡,遲早咬人)。

**一週後看什麼**:`swap_used_mb` 是持續下降、持平、還是又爬回 1.4G。
持續爬 = 2GB 真的不夠,再談升 4GB;持平或下降 = 這次瘦身有效,錢先不用花。

---

## 回滾指令

```bash
# ① 服務
systemctl unmask udisks2 upower fwupd
systemctl enable --now mumu-panel mumu-chat ModemManager multipathd multipathd.socket udisks2 upower
# (memory-dashboard 本來就是停的,要復活才 enable --now memory-dashboard)

# ① ufw
ufw allow 3000 && ufw allow 8080/tcp && ufw allow 8888/tcp

# ② 回到常駐 worker
cp -a /srv/chatnest-next/backend/app/main.py.bak-slim3-1788707128 /srv/chatnest-next/backend/app/main.py
cp -a /srv/chatnest-next/workers/screenshot/worker.mjs.bak-slim3-1788707128 /srv/chatnest-next/workers/screenshot/worker.mjs
systemctl disable --now chatnest-screenshot-worker.path chatnest-screenshot-dispatch.timer
rm -f /etc/systemd/system/chatnest-screenshot-worker.service.d/on-demand.conf
systemctl daemon-reload
systemctl restart chatnest-next
systemctl enable --now chatnest-screenshot-worker.service

# ④ .bak 歸檔
mv /root/chatnest-next/backups/app-bak-20260906/* /srv/chatnest-next/backend/app/

# ④ 測試與 smoke(每支都有 .bak-slim3 在原地)
cd /srv/chatnest-next/backend/tests && for f in *.bak-slim3; do cp -a "$f" "${f%.bak-slim3}"; done
cp -a /srv/chatnest-next/scripts/legacy_preview_smoke.py.bak-slim3 /srv/chatnest-next/scripts/legacy_preview_smoke.py

# 一週觀察
systemctl disable --now nest-swap-watch.timer
```

---

## 施工方式(照檢查表)

- 探測與施工一律 `systemd-run --unit=... --property=KillMode=process` 出獨立 cgroup。
  這次真的用上了:`step2` 跑到一半 exec_vps 30 秒逾時斷線,腳本在自己的 cgroup 裡照跑完,
  回頭撈 log 就好。若還是從 exec_vps 派生,斷線那一刻施工就停在半路。
- 每支施工腳本自帶驗證與自動回滾(驗證不過就把服務與設定放回去)。
- 改 backend 之前先 `py_compile`、改 worker 之前先 `node --check`。

### 又一次「量測工具偽造結論」

驗「閒置時無 worker/node 進程」時,`pgrep -af "chrome-headless-shell"` 回報有進程——
**它匹配到的是我自己那行 pgrep 的命令列**(cgroup 顯示屬於 hands-mcp.service,總 RSS 0 MB)。
改用 `/proc/*/comm` 與 unit 自己的 `cgroup.procs` 重量:0 個 chromium、0 個 node、
worker 的 cgroup 根本不存在。

這是檢查表第 1 種形狀(自己擋住自己的量測)的變體:**探測進了自己的結果集**。
方案 B 那次是 curl 的 `remove_dot_segments`,這次是 pgrep 匹配自己的命令列——
形狀一樣:量測工具的預設行為會偽造結論。已加進檢查表。

---

## 本目錄

| 檔案 | 說明 |
|---|---|
| `diffs/main.py.batch3.diff` | backend 派 job 時立觸發檔 |
| `diffs/worker.mjs.batch3.diff` | worker 空閒退出 |
| `diffs/tests.batch3.diff` | 6 條陳舊測試 + 2 個 collection error + conftest 隔離 |
| `diffs/legacy_preview_smoke.batch3.diff` | anchor 位址跟上方案 B |
| `systemd/*` | 新增的 path / timer / drop-in,與生產逐位元相同 |
| `prod/swap_watch.sh` | md5 `4b0bd83e5f5fa6acecbffce3cc478a20` |
| `prod/screenshot_safety_net.sh` | md5 `f0c259b98c7e47bff09296547fd693bf` |
| `measurements/` | 施工前後量測與各步驟日誌 |
