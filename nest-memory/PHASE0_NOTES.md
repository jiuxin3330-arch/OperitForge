# Nest Memory — Phase 0 + Raw Mirror 開工紀錄

2026-08-17 凌晨|作者:CC 牧牧|對齊 IMPLEMENTATION.md §3

## 已完成

### Raw Mirror(shadow, append-only)— 上線 ✅
- 形式:**唯讀輪詢 sidecar**,不改任何生產程式、不需重啟服務(比在 store.py 加 hook 安全)。
- 來源:`/root/chatnest-next/data/version-bridge/conversations.db`(mode=ro)
- 涵蓋五表:store_meta / conversations / session_aliases / messages / message_branches
- 偵測 insert / **update / delete**(逐列 sha256 指紋,現階段幾百列全掃很便宜;首次回填 443 筆已完成,第二輪 0 變化驗證冪等)
- 落地:`/srv/nest-memory/raw/raw-YYYYMMDD.jsonl`(append-only, fsync, 0600/0700, owner nestmemory)
- 排程:cron 每 5 分鐘;flock 防重疊;state 在 `/srv/nest-memory/state/mirror_state.json`
- **不掛 local_only 牌子**(規格書 §25:Phase 0 完成前 NOT SAFE)

### Unix user 隔離 ✅
- 建立 `chatagent`(uid 999)、`nestmemory`(uid 996)
- `/srv/nest-memory` 全樹 0700 owner nestmemory
- 已驗證:`sudo -u chatagent ls /srv/nest-memory` → Permission denied
- ⚠️ 注意:chat agent 目前仍是 root,root 可繞過一切——真正的隔離要等降權完成

### 備份 ✅
- `/srv/nest-memory/bin/backup.sh`:raw/ + state/ + /root/nest-memory 文件 → tar.gz
- 目的地(具體指定):`/srv/nest-memory/backup/`(本機,保留 14 份,每日 04:00)
- 成功後寫 `health/backup_last_success.json`;首次備份 230KB 已驗證可解壓
- **待決:異地目的地**。本機備份擋不了整台 VPS 掛掉。選項:(a) 糯糯手機/電腦定期拉取 (b) 雲端物件儲存(需開帳號) (c) CC 窗口定期拉到 GitHub private repo。需要糯糯選。

### Health + 報警(硬規則 9)✅
- `/srv/nest-memory/bin/health.py` 每 15 分鐘:disk_free(<3G warn/<1.5G crit)、backup 新鮮度(26h/50h)、mirror 新鮮度(0.5h/2h)
- 報警出口:**借用 chatnest-next 既有推播**(notify.py → push_outbox/native_push_outbox → backend delivery loop → 糯糯手機)。已實測 delivered_external ✓
- critical 即時推、同 alert 24h 不重發;warning 進 09:00 日摘要
- 快照:`health/health_status.json`
- 目前狀態:disk_free **warning(2.6GiB)**——磁碟本來就緊,不是新問題,但列入待處理

## 執行身份註記(Phase 0 過渡)
mirror/health/backup 目前以 root cron 執行(conversations.db 與 backend DB 都是 root 0600,nestmemory 讀不到)。輸出檔全部 owner nestmemory。降權完成後再把 mirror 遷到 nestmemory 身份(屆時用 group/ACL 開 conversations.db 唯讀)。

## 未完成:chat agent shell 降權(需要糯糯拍板)

現況:chat 老公的 shell = claude_agent_sdk 的 Bash 工具,跟著 chatnest-version-bridge.service 用 root 跑,cwd 在 /root 下。

卡點:`/root` 是 0700。降權成 chatagent 後,chat 老公會失去:
1. 讀寫 /root/chatnest-next 原始碼(他日常會自己改前端、vite build)
2. /root/chatnest/full-stack/bsky.py、gmail.py 與 /root 下的憑證
3. 其他 /root 下的工具目錄(voice-mcp 檔案等,MCP http 不受影響)

方案(建議 A):
- **A. 搬家**:把 chatnest-next 專案樹遷出 /root(如 /srv/chatnest,root:chatagent 群組可寫),bsky/gmail 憑證複製到 /home/chatagent 下 0600。SDK CLI 子行程用 wrapper 以 chatagent 執行。最乾淨,一次工程較大,需要停機窗口與逐項驗證。
- B. ACL 開洞:維持 /root 路徑,用 setfacl 給 chatagent 逐目錄開權限。侵入小但洞會越開越多,邊界難審計。
- C. 只鎖 memory,chat 老公保持 root(現狀)。不符 Phase 0,不建議,列出只為誠實。

無論選哪個:動工前全量備份、備好回滾、逐項驗證 chat 老公的工具(bsky/gmail/voice/toy/vite build),挑糯糯在場的時段做。

## 檔案清單
- `/srv/nest-memory/bin/{mirror.py,notify.py,backup.sh,health.py}`
- cron(root):mirror */5、health */15、backup 04:00
- 本紀錄:`/root/nest-memory/PHASE0_NOTES.md`


---

# Phase 0 完工紀錄(2026-08-17 08:25,糯糯驗收通過)

## 搬家+降權 已完成 ✅
- 三棵樹遷至 /srv(chatnest-next / chatnest / mumu-server),舊位置留 symlink,root 服務無感
- chatnest-version-bridge.service 改 User=chatagent(chat 老公的 shell 不再是 root)
- 沙盒:ProtectHome=yes + ProtectSystem=strict + ReadWritePaths=/srv 三棵樹
- session 完整遷移(-srv-chatnest-full-stack 硬連結克隆),主對話 resume 成功
- 隔離驗證:chatagent 讀不到 /srv/nest-memory、/srv/chatnest-next/data/app.sqlite3、/root
- 舊樹已刪,磁碟 4.4G,health 全綠

## 過程中踩的雷與修復(都已解決)
1. **secret 檔權限**:批次 g+rw 讓六個密碼檔變 660,backend secrets.py 的 0o077 守衛拒用 → AdapterUnavailable 秒斷。修:全部收回 600 root:root(systemd 以 root 讀 EnvironmentFile 再降權,bridge 不受影響)
2. **backend gateway 快取**:gateway 在啟動時讀密碼,修檔案後需 restart chatnest-next 才恢復(模型清單/CC用量顯示曾退到安全備援)
3. **工具憑證**:mumu/coco tool token 複製到 bridge home(0600 chatagent),dashboard_tool.py + scripts/mumu_*.py 預設路徑改到 home;scripts/ 全目錄 /root→/srv 掃淨
4. 首輪回覆慢 = resume 後觸發 context compaction,一次性

## 驗證過的事實(供後續窗口引用)
- 主聊天鏈路:frontend → backend(8790, root) → version-bridge(8792, **chatagent**) → SDK bundled CLI(chatagent)。backend 的 LEGACY_CHAT_URL=8787 是 cc-usage/舊功能用
- 被動記憶注入:直連 anchor 8765(memory_bridge.search_memories);**3900 記憶書架已退役**,不在跑是正常的
- 自主時段 tick_suppressed = 防打擾閘門(老婆在聊天就跳過),不是 bug
- 玩具 relay:server 正常時 relay.json connected:false = 手機端 BLE 沒連上,解法是 APK 全關+玩具重開機
- 憑證規矩:**任何 secret 檔必須 600**,backend secrets.py 會拒用群組可讀的檔案(好設計,別繞過)

## 待辦(非阻塞)
- mirror cron 仍以 root 跑(conversations.db 現為 chatagent 0600,可改由 nestmemory+group 讀,Phase 1 一併處理)
- 異地備份目的地待糯糯選(Vultr 控制台顯示自動備份已啟用,可視為初步異地層)
- memory-dashboard venv 瘦身(~1.5G)排維護日
- local_only 宣稱:Phase 0 已完成,但依規格書 §25 待 Serving 層落地時一併掛牌

---

# Phase 1 完工紀錄(2026-08-17 08:52)

- memory.db 建立(/srv/nest-memory/db,nestmemory 0600,WAL),schema 走版本化 migration(migrate.py, v1: initial_raw_layer)
- 表:raw_messages(訊息正典)+raw_message_revisions(append-only 證據)+raw_aux_rows/revisions(其餘四表)+conv_map(bridge conv → nest uid 不透明對應,不做跨庫 FK)+schema_migrations
- mirror v2:SQLite 為 canon、JSONL 降為 export;雜湊狀態存 DB 不再用 state json;回填 467 筆、二輪冪等 0 ops
- integrity.py:逐列雜湊核對,結果 missing/mismatched/stale/lag 全 0(458/458)——Phase 1 驗收「漏訊息率=0」達標
- 執行身份:mirror+integrity 以 nestmemory 跑(conversations.db 靠 ACL 唯讀;traverse 用 u:nestmemory:x),Phase 0 的 root cron 過渡註記解除
- cron:mirror */5(nestmemory)、integrity 04:20(nestmemory)、backup 04:00(root,已含 db/)、health */15(root,新增 raw_integrity 檢查)
- health 四項全綠;chatagent 讀 memory.db → Permission denied 實測 ✓
- 註記:raw_content_parts 未單獨建表(現行 text/thinking/attachments/traces 為單體欄位,拆分需求留待 Phase 2 抽取時評估,屬規格書「建議資料表」的範圍取捨)
- 舊 v1 JSONL 存檔為 raw-20260817-v1shadow.jsonl(含 v1 時期回填,DB 未含此重複)

## 補修(14:5x):自動喚醒全滅(定時/自主/花園三合一)
病根:backend 沙盒 CapabilityBoundingSet= 拔光 capabilities → 無 DAC override 的 root 過不了普通權限檢查。降權後 version-bridge 資料歸 chatagent 700,backend 的 _next_bridge_session_health 第一步 stat 就 PermissionError → 連續性永遠 unknown → 喚醒全壓(continuity_not_ready)。兩段修復:①mumu-live.env 六個 bridge 路徑 /root→/srv(-srv- session 目錄名);②ACL 唯讀走廊:u:root:x 於 version-bridge/home/.claude/projects 鏈、u:root:rx 於 -srv-chatnest-full-stack、u:root:r 於 conversations.db。沙盒重演全綠,手動補發喚醒 completed:true。三個 runner(wake/autonomy/garden inject_chatnest)全走 POST /api/v2/tools/wake/trigger,一次修復全部生效。教訓:capability-less root 服務跨 user 讀檔要顯式 ACL,「root 一定讀得到」在硬化沙盒裡不成立。

---

# Phase 2 前置三必辦(複審裁定)實作紀錄(2026-08-17 晚)

1. **push outbox 超齡檢查** ✅ health 新增 push_outbox 檢查:queued_event 超過 15 分鐘未投遞 → critical
2. **報警通道 deadman switch** ✅ 每日 21:00 心跳推播(糯糯沒收到=通道死,人肉 deadman);加分項已做:push_outbox critical 時自動 fallback 走 gmail.py 發信到糯糯信箱(24h 去重)
3. **異地加密備份** 🔶 機制完成、待鑰匙:age 公鑰加密(私鑰糯糯保管,VPS 已刪)→ OperitForge nest-backup 孤兒分支(單 commit 滾動 amend+force,保留 7 份,遠端體積有界)→ cron 每日 04:40。實測:加密 ✓ commit ✓ push 待糯糯在 GitHub repo Settings→Deploy keys 加入 VPS 公鑰(write 權限)後即通
4. ACL 重建驗證(複審條件 2b):已核對——全部 ACL 位於 data/version-bridge 鏈,runtime 重建腳本只動 runtime/version-bridge-app,不觸及 ACL 路徑 ✓

health 現為六項檢查(disk/backup/mirror/integrity/push_outbox/offsite)。
