# PERM-HOTFIX-PACKAGE：權限止血批（TICKET-X X3/X4 落地）

- 產出：規劃窗工人（Opus），2026-10-07 23:15 CST
- 狀態：**盤點＋dry-run＋副本預演完成；正式樹零改動**（改前快照與現況逐行比對 0 差異）。真機執行等規劃窗覆核。
- 工具目錄：`/root/perm-hotfix/`（0700 root:root）

| 檔案 | md5 | 用途 |
|---|---|---|
| perm_hotfix.py | deb4915c0a22665516600acd432b9884 | plan / execute / rollback |
| healthcheck.sh | 71ea0259cbcfbb106387fa83fce5548a | 唯讀健檢（pre / post） |
| pre-snapshot-prod-20261007T150640Z.tsv | 6458315780ca1f5c0c626abc29609ad9 | 改前權限清單（51,820 列） |
| pre-root-acl-prod-20261007T150640Z.acl | 2586a9cb1e2b2cf7ebef47dfdfbf3bcb | 樹根 ACL 原樣 |
| plan-prod-final.txt | 4079b525654b1c3cad5c8ce3ff6c77e6 | 正式樹 dry-run（預設規則） |
| plan-prod-final-with-node.txt | 1ba7adda742d1b1966c9f2299e301c0b | 正式樹 dry-run（加 R5） |
| rehearsal-final.txt | 9f82304a15723efa83ecfea5c541e964 | 副本預演紀錄 |

> 工具放 `/root` 而不放 reports/：原本草稿放在 `reports/ticket-x/perm-hotfix/`，但 `reports/` 是 2775 root:chatagent，chatagent 可以把 `ticket-x` 改名後換一份自己的 perm_hotfix.py，root 執行時就會被借道。已搬到 `/root/perm-hotfix` 並刪除樹內副本。

---

## 0. 需要規劃窗裁定的三件事

1. **R1b（擴大範圍，建議納入，預設已含）**：除了 bridge 包第五節點名的四個 cron 檔，我把 `scripts/` 整棵也改成去 g+w、o+w，共 152 項。原因如下：
   - root crontab 每 10 分鐘以 `.venv/bin/python scripts/swap_runner.py` 執行，它會 `from compact_watchdog import …`；
   - `scripts/__pycache__` 目前是 2775，chatagent 可以在裡面放一個偽造的 `compact_watchdog.cpython-312.pyc`，下一輪就會被 root 載入。
   - 我已驗證現有的 pyc 與重新編譯的結果逐位元相同，目前未被動過。
   - chatagent 在 scripts/ 下沒有擁有任何檔案；bridge 以 chatagent 身分執行 `scripts/mumu_*.py` 只需要讀和執行，這兩個權限都保留。
2. **R5（node 鏈，預設不含，加 `--with-node` 才納入）**：處理 `.nodeenv`、`workers`、`node_modules`、`.playwright`，共 12,752 項。
   - `chatnest-screenshot-worker` 以 **root** 執行（由 .path 觸發），跑的是 `.nodeenv/bin/node workers/screenshot/worker.mjs`，並載入 playwright 和 chromium；
   - `garden-wake` 以 root 開機自啟，也用 `.nodeenv/bin/node`；
   - 這四棵目前 chatagent 都可寫，和 cron 那條是同一類提權路徑。
   - chatagent 在這四棵下擁有的檔數是 0，觸發檔在 `data/screenshot-trigger/`，不受影響。
   - **建議一起做**；如果想讓本批維持在原本四項的範圍內，就留到下一批。
3. **R1 的 mode**：四個 cron 檔改成 0755，不用 0750。
   - 我掃過四個檔，沒有類似金鑰的字串；
   - bridge 的 Claude（chatagent）會照 TOOLS_NOTE 讀 scripts 下的檔案，0755 比較不容易弄壞功能。

## 1. 先盤「誰在寫」

- 非 root 帳號只有 chatagent（gid 988）、daifugo、nestmemory。
  - daifugo 和 nestmemory 在樹內擁有的檔數都是 0；
  - nestmemory 只有樹根 ACL `user:996:--x`，不會動到。
  - **沒有任何 other 帳號寫入這棵樹，所以全域 o-w 是安全的。**
- chatagent 擁有 8,717 個檔，分布在：
  - data/version-bridge（8,631）
  - runtime/version-bridge-app
  - reports/（handsfree、ticket-s）
  - frontend（dist/public 的 photostack-lab.html）
- chatagent 在 `scripts/`、`.venv/`、`backend/` 擁有的檔數都是 0，樹的第一層也沒有它擁有的項目。
- 這三區最近 3 天的寫入只有 root 的 `scripts/compact_watchdog_state.json`（0600 root），以及一支 root 改過的腳本。
- bridge unit：`User=chatagent`，`ReadWritePaths=/srv/chatnest-next …`，直譯器是 `/srv/chatnest/full-stack/.venv`，**不用 chatnest-next 的 .venv**。
- 擴充 ACL：整棵樹 9 個路徑帶擴充 ACL，其中 8 個在 data/（不碰），樹外只有樹根本身。

**例外清單（絕不收緊）**

| 路徑 | 處理 | 理由 |
|---|---|---|
| `data/`（整棵，含 version-bridge、screenshot-trigger、上傳、log、memories 相關） | 完全排除，連走訪都不進去 | data、上傳、cache |
| `runtime/` | 只去 o+w，保留 g+w | bridge 的 app 與 build 產物 |
| `reports/` | 只去 o+w，保留 g+w | chatagent 寫報告 |
| `frontend/` | 只去 o+w，保留 g+w | chatagent 擁有 8 個 dist 檔 |
| `.git`、`.agents`、`docs`、`deploy`、`references`、`ops` 等其他區 | 只去 o+w | 不是 root 直接執行的程式碼 |
| 所有 symlink | 不動 | 例如 `.venv/bin/python -> python3 -> /usr/bin/python3` |

## 2. 規則與 dry-run 統計（正式樹，唯讀）

| 規則 | 範圍 | 動作 | 路徑數 |
|---|---|---|---|
| R1 | scripts/{wake,autonomy}_{cron.sh,runner.py} | root:root 0755（原本是 0:988，760/775） | 4 |
| R1b | scripts/ 整棵（含 `__pycache__`、swap_runner、compact_watchdog） | 去 g+w、o+w | 152（1 個目錄＋151 個檔） |
| R2 | .venv 整棵 | 去 g+w、o+w | 4,951（497 個目錄＋4,454 個檔） |
| R3a | 樹根 | 2777 → 2755（ACL 的 mask 和 other 跟著變成 r-x） | 1 |
| R3b | backend 整棵（含 backend/app 那 14 個 o+w 檔：main.py、db.py、config.py、security.py…） | 去 g+w、o+w | 249 |
| R3c | 其餘（排除 data） | 只去 o+w | 2,826 |
| R4 | wake_cron.sh、autonomy_cron.sh | 在開頭插入屬主檢查 | 2 個檔 |
| **合計** | | | **8,183**（加 `--with-node` 的 R5 後為 20,928） |

- 抽樣：見 plan-prod-final.txt，每條規則列出頭尾各 3 筆。例如：
  - `.venv 0o2775->0o2755`
  - `.venv/pyvenv.cfg 0o664->0o644`
  - `backend 0o2777->0o2755`
  - `.env.example 0o666->0o664`
  - `workers/screenshot/worker.mjs 0o666->0o664`
- **site-packages 統計**：
  - 共 5,167 項（4,670 個檔、497 個目錄）；
  - g+w 4,922 項，o+w 0 項；
  - 非 root 擁有 0 項；setuid/setgid 檔 0 個。
  - 抽樣 8 筆全部是 `664 root:chatagent` 或 `2775 root:chatagent`，例如 pip/_vendor/packaging/requirements.py、cryptography/hazmat/primitives/kdf/scrypt.py、pydantic/v1/fields.py。
- 收緊之後：
  - 樹根、scripts、.venv、backend 沒有任何 g/o 可寫項；
  - data 以外沒有任何 o+w 項（現在有 2,871 項）。

**R4 屬主檢查（guard）**：插在 shebang 之後。
- 用 `/usr/bin/stat -L` 依序檢查以下路徑：runner、`scripts/`、`.venv/bin/python`、`.venv/bin`、`.venv/lib/python3.12/site-packages`、樹根；`scripts/__pycache__` 存在的話也檢查。
- 每一項都必須是 uid 0，而且 `mode & 022 == 0`。
- 任一項不符，就 `/usr/bin/logger -t chatnest-cron-guard "refuse …"` 並 `exit 1`。
- 用絕對路徑，不依賴 cron 的 PATH。

## 3. 改前權限清單的存檔方式

- **現在已存**：
  - `pre-snapshot-prod-20261007T150640Z.tsv`：data 以外全部 51,820 項，欄位是路徑、mode、owner:group、型別；
  - `pre-root-acl-prod-…acl`：`getfacl -p -n` 的原樣。
- **執行時再存一份精確紀錄**：execute 在動手之前寫入 `/root/perm-hotfix/run-chatnest-next-<UTC>/`（0700）：
  - `records.json`（0600）：每個要改的路徑的 mode_from、mode_to、uid_from、gid_from、own_to；
  - `root.acl`；
  - 兩支 cron 入口的原檔。
- 一條規則對應一個路徑；rollback 會逐條還原。

## 4. 副本預演（已完成，三輪，最後一輪用定版工具）

副本樹是 `/root/perm-hotfix/mirror/chatnest-next`：
- 完整複製 data 以外的 51,819 項，mode、owner、symlink 目標都相同，樹根 ACL 也相同；
- 檔案內容是空的，只有兩支 cron 入口用了真實內容；
- 與正式樹快照逐行比對 0 差異。

| 項目 | 結果 |
|---|---|
| 不帶 `--i-have-approval` 執行 execute | 被拒（refused） |
| execute | 8,183 筆改動，與 dry-run 一致；逐筆驗證不符 0 |
| 收緊後四區的 g/o 可寫項 | 0 |
| data 以外的 o+w | 0 |
| chatagent 的群組寫入保留情況 | frontend 4,160、runtime 663、reports 15,035，都仍可寫 |
| 樹根 ACL | `group::rwx #effective:r-x`、`mask::r-x`、`other::r-x`；`user:996:--x` 不變 |
| 冪等性 | execute 之後再跑 plan，結果是 0 筆 |
| guard 正向（環境變數清空，`env -i`） | 兩支都通過 |
| guard 反向 | 共 10 種情境，全部拒跑並寫入 journal（見下方清單） |
| rollback 不帶 `--execute` | 只列出，不動手 |
| rollback `--execute` | 與改前快照逐行比對 0 差異；樹根 ACL 相同；cron 入口與正式檔逐位元組相同 |

guard 反向測試的 10 種情境：
- runner 加 g+w
- runner 加 o+w
- runner 屬主改成 chatagent
- runner 不存在
- scripts 加 g+w
- `__pycache__` 加 g+w
- `.venv/bin` 加 g+w
- site-packages 加 g+w
- 樹根加 g+w
- python 變成懸空的 symlink

預演中修掉的兩個問題：
- rollback 收到相對路徑的 `--record` 時，`setfacl --restore` 會找不到檔。已改成 resolve 成絕對路徑。（當時 ACL 仍然是對的，因為 chmod 還原的同時 mask 也會還原。）
- guard 原本依賴 cron 的 PATH，已改成絕對路徑。

## 5. 執行步驟（核可後，分兩段）

1. 在 Owner 在場、非喚醒時段執行。不必等，因為不需要重啟（見 §8）。
2. 跑 `cd /root/perm-hotfix || exit; ./healthcheck.sh pre`，必須 FAIL=0。今晚 23:10 跑過一次，**18/18 PASS**。
3. dry-run：`env -u PYTHONPATH -u PYTHONHOME python3 -I perm_hotfix.py plan [--with-node]`，確認 TOTAL 是 8,183 或 20,928；如果檔案有增減，數字會小幅浮動。
4. 記下時間 `T0=$(date '+%F %T')`，然後執行：`python3 -I perm_hotfix.py execute --i-have-approval [--with-node]`。預計數秒內完成。
5. 等 2 分鐘，讓 cron 經過 guard 至少跑兩輪，再跑 `./healthcheck.sh post "$T0"`，必須 FAIL=0。
6. 請 Owner 開一次 dashboard 頁面，再重跑健檢中 memories.db fd 那一項，確認是唯讀。

## 6. 回滾

- 預覽：`python3 -I perm_hotfix.py rollback --record /root/perm-hotfix/run-chatnest-next-<UTC>/records.json`
- 執行：在上一行加上 `--execute`。
- 執行時會依序：
  1. 用原檔替換兩支 cron 入口；
  2. 由淺到深，逐路徑還原 owner 和 mode；
  3. `setfacl --restore` 還原樹根 ACL。
- 只想放行 cron、不還原權限：暫時性的做法是，用 records 目錄裡的原檔蓋回 `scripts/{wake,autonomy}_cron.sh`，等於拿掉 guard。
- 預演已證明 rollback 能讓 metadata 逐位還原。

## 7. 健檢（healthcheck.sh，唯讀；不印任何排程、訊息、記憶內容，不 dump 行程 argv）

- 服務狀態都是 active（只查狀態，不碰）：
  - chatnest-next
  - chatnest-version-bridge
  - chatnest
  - mumu-server
  - mumu-ota
  - anchor-memory
- HTTP：`:8790/api/health` 回 200；bridge 的 `:8792/api/models` 回 200。
- 以 chatagent 身分執行 bridge 的 `wake_tool._load()`：只印 unavailable 旗標和排程筆數；pre 階段的結果是 unavailable=0、schedules=4。
- `wake_cron.sh --status` 與 `autonomy_cron.sh --status` 的退出碼都是 0：這會實際經過 guard 和 venv，而 runner 的 status() 只輸出不寫入，輸出導到 /dev/null。
- `journalctl -t chatnest-cron-guard --since T0` 的拒跑次數為 0（副本預演的紀錄會排除）。
- cron 最近 3 分鐘有觸發 wake_cron.sh 和 autonomy_cron.sh 各至少 2 次。
- wake、autonomy、swap 三份 log 的最後 200 行，`Permission denied` 與 `PermissionError` 的計數都是 0。
- dashboard：chatnest-next 持有的 memories.db fd 必須唯讀（O_ACCMODE=0），只看 fd 旗標。
- post 階段額外檢查：
  - 四個收緊區沒有 g/o 可寫項，data 以外沒有 o+w；
  - 四個 cron 檔都是 `root:root 755`；
  - chatagent 寫不了樹根、scripts、runner、.venv/bin、site-packages、backend、backend/app、main.py；
  - chatagent 仍然寫得了 runtime/version-bridge-app/app、reports、frontend、data/version-bridge。

## 8. 是否需要重啟：**不需要**

- 這批只改 mode、owner，再加上兩支 cron 入口開頭的 guard，不改任何程式碼內容。
- chatnest-next（root）、bridge（chatagent，用另一套 venv）、screenshot、garden 都不會因此需要重啟：已載入的程式不受影響，root 也不受 DAC 限制。
- chatagent 只是失去對 root 程式碼的寫入權；Python 寫不了 `__pycache__` 時會靜默略過。

## 9. 不在本批的同類洞（建議排下一批）

| 優先 | 洞 | 現況 |
|---|---|---|
| 高 | `/srv/chatnest/sync_models.py`（664 root:chatagent）| 由 `chatnest-models-sync.timer` 每天以 root 執行 `/usr/bin/python3` 跑它。chatagent 可以直接改寫這個檔。 |
| 高 | `/srv/chatnest` legacy 樹（full-stack、.venv、app 都是 2775 root:chatagent）| 由 chatnest.service 以 root 執行。注意 bridge 也用這套 venv 讀取，收緊時同樣只拿掉群組寫入。 |
| 高（若 R5 不納入本批）| `.nodeenv`、`workers`、`node_modules`、`.playwright` | 見 §0-2 |
| 中 | `.git/hooks`（R3c 只拿掉 o+w，群組仍可寫）| 只有 root 在樹內跑 git 時才會觸發；建議日後一併改成 g-w |
| 中 | reports/ 內的 deploy 腳本（如 bridge-batch/deploy_bridge_batch.py）| 曾由 root 執行；今後部署工具一律放 `/root/…` |
| 低 | 樹內舊的 `.bak-*` 腳本 | 已涵蓋在 R1b、R3b 中，只是一併記錄 |

---

## 附：coco 隊伍移交清單（任務二，只記錄）

依照 INBOX_coco §39 的處置，以及工人這兩天所知的現況：

| 項目 | 一句現況 | 優先級建議 |
|---|---|---|
| **X5 金鑰出碼入檔＋輪換** | toy、daifugo 兩把 16 字元的 MCP path key 仍寫死在程式碼與設定檔裡（bridge 批的 X1 只處理了 argv 藏密，沒有出碼）；而且我在先前的 redaction 漏洞中曾經接觸過它們，**本來就該輪換**。做法：key 移到 0600 檔或 EnvironmentFile，程式碼只讀路徑，換新 key 後重啟相關服務。 | **P1**（本批之後第一個做；需要重啟，等 Owner 在場） |
| **TICKET-I 建置鏈回填** | tts v4 與 10/7 新參數只裝在 live runtime，`build_version_bridge_runtime.py` 和 patch 腳本還沒回填。`claude.py`、`memory_bridge.py` 的 live 版與 build 產物有漂移（依 §39 所記，本批未重新量測）。不回填的話，下次重建可能把 bridge 批的修補蓋掉。做法：對三方做 diff（build 產物、live、bridge-batch stage），回填到 patch，然後在副本上重建，比對結果是否逐位元組相同。 | **P2**（任何重建 runtime 之前一定要先完成） |
| **wake_runner JSON 壞檔隱患** | 已確認：`load_schedule()` 遇到 OSError 或 JSONDecodeError 時會回傳空的 `{"schedules": []}`，`--check` 流程之後會 `save_schedule` 寫回，於是一次壞檔或讀取失敗就把整份排程清空。修法：載入失敗時回傳 sentinel 並拒絕寫回、記 log、保留壞檔副本；save 本身已經是 tmp 加 replace。小改動，可以走紅綠測試。 | **P3**（改動小，可以接在 TICKET-I 後面） |
| **W/U/Y 交叉覆核** | 依 §38、§39 已降級。我自己做過的 R 門和 bridge 批**排除**（不自我覆核）。W 名冊、U 一二期、B6～B9、Y0～Y2c，以及 S2-P、S2-E 的獨立覆核：**待安排其他窗口，或降級為規劃窗抽查**，清單保留在各 ticket。 | **P4**（不急；有第二個獨立窗口時再補） |

工人紀律聲明：
- 本批全程只看程式碼與 metadata。
- 沒有讀取任何記憶、訊息、排程或留言的內容；健檢只輸出計數和旗標。
- 沒有 dump 任何行程的 argv。
- 沒有碰 anchor-memory，也沒有改動正式樹。
