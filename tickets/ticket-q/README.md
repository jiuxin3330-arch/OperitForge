# TICKET-Q：記憶優化 P1a——止血 + 儲存層（2026-09-21 交付）

工單正本：VPS `/root/nest-memory/TICKET_Q_memory_p1a.md`（md5 825ee4dd…）；規格 `PLAN_memory_20260920.md`（md5 9d6eed91…）。
施工範圍：只碰 anchor-memory 服務（8765）與其 DB。沒碰 bridge / prompt / cn 工具描述 / chatnest-next / 檔案室抽取器。

## 交付清單

| 工單要求 | 檔案 |
|---|---|
| 盤點報告（Q1.1 強化路徑 + Q1.3 污染現狀） | `REPORT_Q1_hebbian_audit.md` |
| migration | 程式碼內 `prod/anchor_ext.py::_migrate_ticketq`（冪等，啟動時跑）；SQL 對照版 `migration_ticketq_001.sql` |
| diff | VPS anchor repo `7c2e317`（baseline）→ `3834bdd`；生產現行版逐檔在 `prod/`，md5 見 `MD5SUMS_prod.txt`（逐位元對生產） |
| 備份檔名 | `/root/anchor-memory/memory_data/memories.db.bak-ticketq-20260921_041130`（md5 0f921b3c…，schema 為舊版）、`chroma.bak-ticketq-20260921_041130.tar.gz`（md5 011f3c1f…） |
| 測試輸出（先破後立） | `TEST_OUTPUT.md`（baseline 0/11、新碼 11/11） |
| 重啟前後健康證明 | `TEST_OUTPUT.md` 第三、四節 |
| 事故 | `INCIDENT_20260921_oom_during_tests.md`（測試把 2GB 機器壓到 OOM，anchor 被殺、意外重啟載入新碼） |
| 日後刻意重啟的程序 | `deploy_restart.sh`（本次沒跑到） |

## 做了什麼（對照工單）

**Q1 止血**：`search()` 不再 cite、不再 Hebbian 建邊；`hebbian` / `no_cite` 參數留簽名被忽略——依路徑硬關，不看 caller 旗標。只有 `cite_memory` / `annotate_memory`（節點）與 `consolidate`（邊）強化，1.0 / 0.5 / 0.5 / 0.25 / … 遞減、累積封頂，參數在 `anchor_config.py`。注入帳（`injections` 表）記 search / wakeup 回傳過的 id；`consolidate` 命中視窗內（預設 180 分鐘）的記憶一律跳過（invariant ③）。legacy 污染只快照（`legacy_usage_count` / `legacy_weight`）+ 標記 `pollution_cutoff=2026-09-20`，不回滾。

**Q2 memory_tasks**：表 + 三個工具（create / list / resolve）。open → resolved | dismissed；resolve 必填 resolved_by 與 reason；終態不可再轉；沒有刪除路徑。

**Q3 entity_cards + card_facts**：建卡 / 改狀態要 `owner_token`（`/root/anchor-memory/owner.key`，root 0600；bridge 以 chatagent 跑讀不到 = 系統路徑天然拿不到）；`update_card_fact` 任何身分可用，舊 fact 補 `valid_until` + `superseded_by`；`cards_affected_by(source_id)` 反查。20 張不寫 schema cap。

**Q4 digest schema**：`memories.kind`（memory | daily_digest | letter_digest | digest）+ `derived_from`（JSON）；derived 類缺 provenance 直接拒、不碰 chroma；`memory_lineage` 表雙向索引，`memory_lineage(id)` 工具給 digest 回 sources、給 source 回 digests；刪 source 後 lineage 保留，`delete_memory` 回傳受影響數。

**附帶必要修正（工單沒寫，附理由）**：`AnchorDB.insert` 由 `INSERT OR REPLACE` 改 UPSERT。REPLACE 是 DELETE+INSERT，經 ON DELETE CASCADE 會清掉該記憶的 edges / comments / annotations 並把 pinned 歸零（memory_bridge 註解「同 id 覆蓋 + pin_memory 重釘兩步都要」就是這個坑）。不改的話新加的 `reinforcement` 每次跨窗近況卡覆蓋就歸零，Q1 的儲存目標不成立。有測試（Q-extra）。

## 工具數

既有 20 個（工單寫 19，實數 20 含 graph_stats）全在、簽名向後相容；新增 9 個：`memory_task_create` / `memory_task_list` / `memory_task_resolve` / `create_entity_card` / `set_entity_card_status` / `update_card_fact` / `get_entity_card` / `cards_affected_by` / `memory_lineage`。共 29。

## 沒做到 / 要糯糯或小踢裁的

1. **重啟沒有先問糯糯**：OOM 逼出來的意外重啟，不是刻意執行；服務已在新碼上健康運行，我沒有再刻意重啟第二次。要不要再做一次「正式」重啟（跑 `deploy_restart.sh`，含重啟前備份），糯糯決定。
2. **owner_token 怎麼交到糯糯手上**：現在只有 root 讀得到 `/root/anchor-memory/owner.key`。CC 窗口（exec_vps 是 root）可以代她建卡；如果她要自己從 claude.ai 建卡，需要把 token 給她。這是身分設計的一部分，先問她。
3. **P1a 期間 `cite_memory` 對排序沒有即時效果**：排序的 `citation_boost` 仍讀凍結的 `usage_count`（不動排序公式是 P1a 的界線）；新的 `reinforcement` 欄只儲存，等 P1b ranker 接。小踢若認為應該現在就切，是一行的事，但那就碰了排序。
4. `wake_runner.py`（legacy full-stack）還在打舊路徑 `/mcp`，MCP_LEGACY_PATH=0 之後那條是 404。不在本單範圍，盤點報告有記。
5. 檢查表候補一條（INCIDENT 末段），待覆核裁定才收進正本。

## 後續單（本單不做）

P1b ranker（R1 + invariant ② trace）、P1c retrieval / selection（R5 + invariant ⑤ 去重）、P2 語氣打樣（MEM-1 注入行、MEM-2 夜間 writer、MEM-5 開啟）。
