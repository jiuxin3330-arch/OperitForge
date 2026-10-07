# Bridge 重啟批（原排給 coco，規劃窗＋施工子代理接手）

> 轉錄註記（規劃窗）：正本在 VPS `/root/nest-memory/reports/BRIDGE-RESTART-PACKAGE.md`，md5 `be6e6ea1e340e02f2878527740db7e2e`；本檔為轉錄本，施工以正本為準。規劃窗 10/7 已覆核（紅測先紅 9/9 後綠 9/9、mutation 11/11 含 MX11 補靶重殺、b7 雜湊鏈、部署預演逐位回歸、runbook 與回退完整）。**第二節兩段 cn-visible 文案待 Owner 貼小踢快審，審過才重啟。**

對象：`chatnest-version-bridge.service`（cn 的對話橋，User=chatagent，現行 MainPID **1291078**，自 9/26 06:40 起沒有重啟過）。

- 施工目錄：`/srv/chatnest-next/reports/ticket-x/bridge-batch/`，權限 0700。目錄內有含密鑰的原始碼副本，不要放寬權限。
- 紀律：
  - 工人只讀程式碼與 metadata，正式檔一個字都沒動；
  - 所有試套都在副本上；
  - 重啟由規劃窗在 Owner 在場、非喚醒時段時執行。

---

## 〇、結論先講

| 件 | 狀態 | 一句話 |
|---|---|---|
| ① b7/bridge-pending | **就緒** | 正式檔仍在 b7 的 before 雜湊，乾淨套上，after 雜湊和 b7 manifest 逐位相同；b7 的紅綠測試在本批重跑：舊版 3 紅、新版 6/6 綠 |
| ② tts v4 | **就緒（已在位）** | runtime 的 tts.py 是 `eleven_v4`，備份 `tts.py.bak-v3-20261001-044317` 在；重啟即生效 |
| ③ TOOLS_NOTE 索引 | **程式就緒；文案待小踢快審** | 找不到既有的已審擬稿。最終文案放在第二節，**待 Owner 貼給小踢快審**；有紅測鎖住「索引分類＝help 工具分類」 |
| ④ X1 argv 藏密 | **就緒（本批新寫）** | coco 沒有留下修法。系統提示改走 0600 私有檔，外部 MCP 的 URL／金鑰／Bearer 改走 0600 JSON 檔（第二個 `--mcp-config`）；紅測 9/9 先紅後綠；變異 11/11（第一輪 1 存活，已補專屬靶） |
| ⑤ C 門 caller | **併入（不作用）** | 改動只有一行：被動注入的 search_memory 帶上 `cooldown: True`。anchor 現行 ANCHOR_COOLDOWN=0，參數被忽略；等 C 門開時才生效 |
| wake_runner 壞檔清空 | **不在本批，只記錄** | b7 NOTES 第 105 行：修法不在 b7 包內，不擴 scope |
| X3／X4 | **未退化，但治本不在本批，而且現況比單據寫的更嚴重**（見第五節） | 建議規劃窗盡快另批 |

**預估停機**：bridge 停止（SIGINT，TimeoutStopSec=20）加上 uvicorn 啟動，**通常 5–10 秒，最壞約 25 秒**。只有正在進行中的那一輪回覆會中斷，所以重啟前要先確認 cgroup 裡沒有 Claude CLI 子行程（見第三節步驟 3）。重啟後，cn 的第一輪會冷啟動一個新的 CLI，多花幾秒。

---

## 一、各件的就緒狀態與證據

### ① b7/bridge-pending（wake_tool 失敗不靜默、保權限、runtime_patch 同步）
- 內容：
  - `wake_tool.py`：排程檔存在卻讀不到時，回「暫時讀不到」，並設 is_error；拒絕把讀不到的排程覆寫成空的；寫檔保留 chatagent 群組、0640。
  - `version_bridge_runtime_patch.py`：同步的建置轉換，具冪等性、錨點有守門。
- 可套性：正式檔現況 `wake_tool.py ae19b1c8…`、`runtime_patch 2f466eaf…`，等於 b7 manifest 的 before；`patch --dry-run` 乾淨；套用後 `4732037f…`、`d40f5d39…` 等於 b7 的 after。
- 紅綠（本批重跑 b7 自帶的 `test_b7_wake.py`）：
  - 現行版本：3 failed／3 passed（`b7-wake-on-live-baseline.txt`）；
  - 套用後：6 passed（`b7-wake-on-stage.txt`）；
  - b7 原始的 mutation 38–40 見 `ticket-u2/b7/mutations.log`。
- cn 看得到的新句子：**「排程檔暫時讀不到（不是沒有時段），請告訴糯糯。」** b7 的快審清單沒有列它，**一併送小踢快審**。
- 注意：**不要**另外執行 `b7/bridge-pending/deploy.py`，本批的 deploy 已經把它包進來，而且 runtime_patch 是疊加後的版本。

### ② tts.py v4
- `runtime/version-bridge-app/app/tts.py`（sha `bf87273f…`）第 41 行是 `"model_id": "eleven_v4"`；備份 `tts.py.bak-v3-20261001-044317`（`51d5547a…`），和現行只差這一行。
- **重建風險（TICKET-I）**：legacy 來源 `/srv/chatnest/full-stack/app/tts.py` 仍是 v3，`build_version_bridge_runtime.py` 會整份複製 legacy app。好在 build 有漂移守門，不加 `--overwrite-drifted-runtime` 就會拒絕；但日後重建前要先把 v4 回填進建置鏈。本批不處理。

### ③ TOOLS_NOTE 能力索引
- 現況：claude.py 第 166 行的 `可查分類` 少了 schedule、friends、gallery，而 help 工具（`mumu_tool_help.py list`）有這三類。
- 改法：分類順序和 help 工具一致，另加一句防混淆（**文案原文見第二節，待小踢快審**）。
- 建置鏈同步：`_TOOLS_NOTE_NEW` 同步修改。
- 紅測 N1：索引分類必須和 help 工具的分類一一對應、順序相同，含防混淆句，建置鏈也要同步。現行 FAIL，套用後 OK。變異 MX8（漏 friends/gallery）、MX9（拿掉防混淆句）都 killed。

### ④ X1 argv 藏密（TICKET-X）
**問題的實際樣貌**（只看程式碼）：bridge 主行程本身的 argv 很乾淨（12 個參數、171 bytes，只有 uvicorn 參數）。暴露點在 **每輪對話由 Claude Agent SDK 叫起的 Claude CLI 子行程**：SDK 0.2.97 會把 system prompt 以 `--system-prompt <全文>` 傳入，並把 `--mcp-config <JSON>` 整段放進 argv，JSON 裡含 anchor／stackchan 的 path key（`mcp_local_url`）、toy 與 daifugo 的 path key，以及 galatea 的 Bearer。對話進行時，這個 CLI 子行程是常駐的（warm actor）。

**修法**（新模組 `app/argv_safety.py`，claude.py 在 `ClaudeAgentOptions(**option_values)` 之前呼叫 `argv_safe()`）：
- system prompt → 寫進服務私有目錄的 **0600 檔**，argv 只剩 `--system-prompt-file <路徑>`。
  - 目錄是 `/tmp/cn-bridge-private`，權限 0700；服務有 `PrivateTmp=true`，這個 /tmp 只有本服務看得到。
  - 檔名用內容的 sha256，同一份提示重複使用；超過 24 小時的舊檔會順手清掉。
- 外部 MCP（http／sse）→ 整段寫進同目錄的 **0600 JSON 檔**，以第二個 `--mcp-config <路徑>` 傳入；SDK 行程內的 server（voice、persona、wake 等）原樣不動。
- **不用環境變數**：先試過 `${VAR}` 展開，可行，但 env 會被 cn 的 Bash 子行程繼承，cn 只要跑一次 `env`，密鑰就會進到對話裡，所以改用檔案。
- 已用 bundled CLI 2.1.173 實測：`--system-prompt-file` 受支援；多個 `--mcp-config` 會合併。

**證據**（`bridge-batch/`）：
- 紅測（`test_x1_bridge_batch.py`，unittest，用 bridge venv 跑）：
  - 現行版本 **9/9 紅**（`red-x1-on-live.txt`）；套用後 **9/9 綠**（`green-x1-stage.txt`）。
  - X1_1：用現行寫法組出 SDK 的 argv，檢查器必須抓到內嵌提示、明文 URL、Bearer。
  - X1_2：修後的 argv 乾淨，假的提示、金鑰、token 都不在 argv 裡，有兩個 `--mcp-config`，SDK server 物件原樣保留。
  - X1_3：私有檔 0600、目錄 0700、同內容重用、舊檔清除。
  - X1_4：claude.py 在 ClaudeAgentOptions 之前呼叫 argv_safe（AST 檢查）。
  - X1_5：**真的啟動 bundled CLI**，接一個假的 MCP server——讀 `/proc/<CLI pid>/cmdline` 確認乾淨（只做模式比對、不輸出），而且 MCP server 收到的請求路徑和 Authorization 是真值，證明功能沒壞。
  - P1、P3：建置轉換冪等，而且建置鏈（legacy → claude_source → toolbox → visible_thinking）會帶出 X1。
- 檢查器 `argv_findings()` 只回傳布林值和計數，從不回傳 argv 內容。
- 變異（`run_mutations.py`，`mutation-results.json` 的 replay 欄可逐字重跑）：**11/11 killed**。第一輪 **MX11 存活**（拿掉建置鏈的串接，P1 只測轉換函式本身），照實記錄在 `mutations-round1.log`；補上專屬斷言 P3，重放後 killed（`mutation-MX11-replay.log`）。
- 建置鏈一致性：以 legacy 為來源、在副本上各自重建，比對「現行→本批」和「重建現行→重建本批」兩組差異：claude.py、memory_bridge.py、wake_tool.py **逐行相同**，argv_safety.py 重建結果和 stage **逐位相同**。
  - 註：claude.py、memory_bridge.py、tts.py 的 runtime 本來就和重建結果有差（TICKET-I 既有漂移）；既有測試 `test_b1_comment_injection_backport_reproduces_the_runtime` 也本來就是紅的，本批不新增任何失敗（`runtime-patch-tests-on-*.txt`）。
- 匯入冒煙：把現行 runtime app 全份複製，覆蓋本批四個檔之後，用 bridge venv 匯入 `app.claude`、`app.memory_bridge`、`app.wake_tool`，全部成功（argv_safe 已接上、TOOLS_NOTE 含 schedule、wake_tool 有新句）；副本隨即刪除。
- 部署預演：在副本根目錄上 install → 雜湊和 stage 相同、權限屬主保留（新檔 root:chatagent 0640）→ rollback → 逐位回到基線（`rehearsal-*.txt`）。

**殘留（不擋本批，照實寫）**：
- cn 以 chatagent 身分本來就讀得到金鑰檔與這個私有目錄，X1 擋的是「同機其他帳號看 argv」，不是 cn。
- **原始碼內嵌的密鑰**（galatea Bearer、toy／daifugo 的 path key）仍然寫死在 claude.py 和 legacy 原始碼裡（0660 root:chatagent）。X1 只解決 argv；建議另開 X5，改成和 anchor 一樣讀 mcp-keys 檔。
- **誠實揭露**：工人盤點 claude.py 時，遮罩正規式只遮 20 字元以上的字串，**toy 與 daifugo 兩把 16 字元的 MCP path key 曾出現在工人的工具輸出裡**。沒有寫進任何檔案或報告。規劃窗裁定：記入 X5 一併輪換（該兩把 key 本就寫死原始碼，輪換需改碼，與 X5 同場處理）。

### ⑤ C 門 caller 參數
- bridge 呼叫 anchor 的身分是 anchor 依來源 IP 判定的（local），不需要另傳 caller。C 門真正需要 bridge 配合的是：**被動注入的 search_memory 帶 `cooldown: True`**（Y2c 設計）。
- 改動：`memory_bridge.py` 一行，加上建置鏈同步（`patch_memory_bridge_c_gate_source`，冪等）。
- **現在不改變任何行為**：anchor 的 `_y2c_filter` 只有在 `ANCHOR_COOLDOWN=1` 時才看這個參數，現行是 0。C 門開時，只需要開 anchor 的旗標，bridge 不必再重啟。
- 紅測 P2；變異 MX10 killed。
- 規劃窗裁定：**留在批內**（現在不作用、省 C 門時一次重啟）。

---

## 二、cn 看得到的文字（待 Owner 貼小踢快審）

**③ TOOLS_NOTE（claude.py 系統提示中的能力索引）：只改兩處，其餘逐字不變**

改前：
> 可查分類：diary、calendar、collection、work-mail、versions、screenshot、desire、memory、stackchan、voice、persona、wake、easter-egg、web、social、gmail、daifugo。

改後：
> 可查分類：diary、**schedule**、calendar、collection、work-mail、versions、screenshot、desire、memory、stackchan、voice、persona、wake、easter-egg、web、social、gmail、**friends**、**gallery**、daifugo。

新增一句（緊接在既有的「工具用途不要混淆：StackChan camera…」那一行之後）：
> 課表、今天行程與待辦用 schedule；calendar 是身心日曆（情緒與頭像），不是行程表。

**① wake_tool 新句（b7 原稿，之前沒列入快審）**：
> 排程檔暫時讀不到（不是沒有時段），請告訴糯糯。

如果小踢改了文案：改 `stage/runtime/version-bridge-app/app/claude.py` 和 `stage/scripts/version_bridge_runtime_patch.py`（N1 測試會同時檢查兩邊），重跑綠測與變異，再交給規劃窗。

---

## 三、重啟 runbook（規劃窗執行；Owner 在場、非喚醒時段）

喚醒時刻現讀自 `/srv/chatnest-next/data/version-bridge/wake_schedule.json`，目前是 09:00、14:00、22:00、23:30（Asia/Taipei）。建議避開每個時刻的前 30 分鐘到後 45 分鐘。

```
cd /srv/chatnest-next/reports/ticket-x/bridge-batch || exit
# 1. 唯讀前檢（六個目標檔都在基線、新檔不存在、tts 已是 v4）
python3 deploy_bridge_batch.py check
# 2. 記下舊 PID
OLD=$(systemctl show -p MainPID --value chatnest-version-bridge.service); echo $OLD
# 3. 確認 cn 不在回覆中：bridge cgroup 裡沒有 Claude CLI 子行程（只數，不印 argv）
for p in $(cat /sys/fs/cgroup/system.slice/chatnest-version-bridge.service/cgroup.procs); do readlink /proc/$p/exe; done | sort | uniq -c
#    只有一行 python3.12 → 閒置，可以重啟；有其他行（CLI 子行程）→ 等 cn 回完再來
# 4. 換檔（自動備份到 pre-install-<UTC>/，保留原屬主／權限）
python3 deploy_bridge_batch.py install --apply
# 5. 重啟（停機通常 5–10 秒，最壞約 25 秒）
systemctl restart chatnest-version-bridge.service
# 6. 驗證
python3 verify_bridge_batch.py --old-pid $OLD
```

**重啟後驗證清單**（第 6 步自動做大半，手動的部分標 ☐）：
- 六個檔的已安裝雜湊等於 stage；tts 是 v4；TOOLS_NOTE 三分類加防混淆句；memory_bridge 帶 cooldown。
- 服務 active、MainPID 變了、行程在換檔之後才啟動、`/api/models` 回 200。
- **wake_tool 實呼**：以 chatagent 身分載入新的 wake_tool 並讀排程，`unavailable=0`、排程數 > 0。只輸出計數；重啟前的基準是 0／4。
- ☐ **cn 對話通路**：Owner 傳一句話給 cn，確認正常回覆。
- ☐ **argv 乾淨**：cn 回完一輪後執行 `python3 verify_bridge_batch.py --argv-only`。每個 cgroup 行程（含 Claude CLI 子行程）都要 `argv clean`，私有目錄 0700、檔案全是 0600。
- ☐ **TOOLS_NOTE 生效**：請 cn「列一下你可查的能力分類」，應該看得到 schedule、friends、gallery。
- ☐ **tts v4 出聲**：請 cn 傳一則語音（voice 工具），Owner 確認有聲音、音色正常。
- ☐ **wake 工具**：請 cn 跑一次 `list_wake_schedules`，應該看得到時段（b7 NOTES 的原驗收項）。

`verify-before-install.txt` 是現行狀態的對照（應該 FAIL 的項目都如預期 FAIL）。

## 四、回退

- **整包回滾**：`python3 deploy_bridge_batch.py rollback --backup pre-install-<UTC> --apply`，接著 `systemctl restart chatnest-version-bridge.service`。它會還原四個被換掉的檔、刪掉兩個新檔，預演結果逐位回到基線。
- **只退某一件**（從 `pre-install-<UTC>/` 取原檔）：
  - ① wake_tool：還原 `runtime/.../wake_tool.py`。runtime_patch 屬於建置鏈，可以留著，它只影響日後的重建。
  - ③ TOOLS_NOTE、④ X1：都在 claude.py 裡，還原 claude.py 就兩件一起退。argv_safety.py 留著也無害，因為沒有人 import 它。
  - ⑤ C 門：還原 memory_bridge.py。
  - ② tts：`cp -p tts.py.bak-v3-20261001-044317 tts.py`。這不屬於本批的 deploy，是規劃窗之前就改好的。
  - 每一種都要重啟才生效。
- 私有目錄 `/tmp/cn-bridge-private` 在 PrivateTmp 裡，服務重啟時由 systemd 自動清掉，不需要另外處理。

## 五、X3／X4 現況核對（治本不在本批，留給 coco 覆核時決定；但建議規劃窗盡快另批止血）

- **止血未退化**：`/srv/chatnest-next/scripts` 仍是 2755 root:chatagent。
- **但是止血不完整**，以下是 root 會執行、chatagent（甚至任何人）可寫的路徑，只列 metadata：
  - root cron 每分鐘執行的 `wake_cron.sh`、`wake_runner.py` 是 **0760**（群組可寫），`autonomy_cron.sh`、`autonomy_runner.py` 是 **0775**。目錄雖然鎖了，**檔案內容仍可被 chatagent 改寫**，提權路徑還在。
  - root cron 用的直譯器 `/root/chatnest-next/.venv`：bin 和 site-packages 是 **2775**（群組可寫，site-packages 有 4,454 個群組可寫檔）。換掉 `bin/python` 連結或 runner import 的套件，就能讓 root 執行任意程式碼。
  - **`chatnest-next.service` 以 root 執行**（User 未設），它的程式碼目錄 `/srv/chatnest-next/backend/app` 是 **2777**，`/srv/chatnest-next` 本身是 2777 加 ACL other::rwx。backend/app 有 **14 個 other 可寫的檔**，`main.py`、`db.py` 都還是 0666。**同機任何帳號都能改 root 服務的程式碼**，比 X3 單據寫的「全機可寫」更嚴重，因為執行者是 root。
  - bridge 自己用的 bundled CLI 是 0775 root:chatagent，但 bridge 本身就以 chatagent 執行，不構成提權。
- 建議（不在本批、未施工）：另開一批由規劃窗或 coco 處理——
  1. root 執行的四個檔改 0750 root:root（或 0755）；
  2. `.venv` 收回 root-only 寫入；
  3. backend/app、`/srv/chatnest-next` 拿掉 o+w 和 ACL 的 other 寫權限；
  4. cron 入口加上屬主檢查。

  每一步都要先列清單、改完跑全服務健檢；涉及 chatnest-next 重啟時，比照 Owner 授權。

## 六、未在本批、只記錄

- `wake_runner.load_schedule` 在 JSON 壞掉時回傳空清單，接著 `mark_ran` 存檔會把排程清空（b7 NOTES 第 105 行）。runner 由 root 執行，權限問題不會觸發這條路徑，只有檔案內容壞掉才會。不在 b7 包內，不擴 scope。
- TICKET-I：tts v4、claude／memory_bridge 的既有漂移，日後重建前要回填進建置鏈。
