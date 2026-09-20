# TICKET-Q 測試輸出（先破後立）與重啟前後健康證明

測試檔：`prod/tests/test_ticketq.py`（VPS 正本 `/root/anchor-memory/tests/test_ticketq.py`）。
跑法：`systemd-run -p MemoryMax=800M -p MemorySwapMax=0`，先 baseline（`git worktree` 7c2e317）再新碼，序列跑。
假 embedder（見 INCIDENT）：測儲存層與強化邏輯，不測向量品質。

## 一、破：baseline 7c2e317（施工前生產碼）—— 0 PASS / 11 FAIL+ERROR

```
ANCHOR_SRC=/root/anchor-memory-baseline
FAIL  Q1-T1 系統路徑 search 同一筆 100 次 → 節點權重、邊權重、排序分數皆不變
      節點權重被檢索改了：{'B_broccoli_welcome': {'usage_count': 1}, 'A_broccoli_gift': {'usage_count': 1}} → {'B_broccoli_welcome': {'usage_count': 102}, 'A_broccoli_gift': {'usage_count': 102}}
FAIL  Q1-T2 cn cite 同一筆 5 次 → 前 3 次遞增、之後趨平且有上限
      cite 沒有回傳 reinforcement（baseline 無此欄）
FAIL  Q1-T3 注入後複述不算（invariant ③ Golden）：search 注入 A → consolidate(A 的複述) → A 不變；未注入的 C/D 仍會建邊
      注入後複述改了 A 的邊：[] → [{'source_id': 'A_broccoli_gift', 'target_id': 'B_broccoli_welcome', 'weight': 0.15}, {'source_id': 'A_broccoli_gift', 'target_id': 'C_stackchan', 'weight': 0.15}, {'source_id': 'A_broccoli_gift', 'target_id': 'D_limen', 'weight': 0.15}]
FAIL  Q1-T3b consolidate 邊強化遞減：同一對重複 5 次 → 增量遞減、封頂
      邊增量沒有遞減：ws=[0.15, 0.3, 0.45, 0.6, 0.75] incs=[0.15, 0.15, 0.15, 0.15, 0.15]
FAIL  Q1-T4 MCP 層 search_memory(hebbian=True) 也不強化（工具簽名相容、行為硬關）
      MCP search 改了節點：{'B_broccoli_welcome': {'usage_count': 2}, 'A_broccoli_gift': {'usage_count': 2}} → {'B_broccoli_welcome': {'usage_count': 52}, 'A_broccoli_gift': {'usage_count': 52}}
ERROR Q1-T5 wakeup 不強化，且回傳的 id 進注入帳
      AttributeError: 'AnchorDB' object has no attribute 'record_injection'
ERROR Q1-T6 migration：污染期快照（legacy_usage_count / legacy_weight / pollution_cutoff）只做一次，之後新記憶 legacy=NULL
      OperationalError: no such column: legacy_usage_count
ERROR Q2-T1 memory_tasks 狀態機：open→resolved 合法；無 reason 拒；終態不可再轉；沒有刪除路徑
      AttributeError: 'AnchorDB' object has no attribute 'task_create'
ERROR Q3-T1 非 owner 建卡拒；owner 建卡成；fact 更新 → 舊列 valid_until + superseded_by；affected_by 查得到
      AttributeError: 'AnchorDB' object has no attribute 'card_create'
ERROR Q4-T1 digest 無 derived_from 拒；有則寫入；lineage 雙向；刪 source 後仍查得到受影響 digest
      TypeError: AnchorMemory.store() got an unexpected keyword argument 'kind'
FAIL  Q-extra 同 id 覆蓋（跨窗近況卡）不再清空 pinned / reinforcement / edges / comments
      {'memory_id': 'A_broccoli_gift', ..., 'usage_count': 0, ..., 'pinned': 0, ...}   ← REPLACE 把 pinned 清成 0
== 0 PASS / 11 FAIL+ERROR / 11 total ==
EXIT=11
```

讀法：T1 在 baseline 搜 100 次 usage_count 1→102（每次 search 都 cite），這就是被動注入每輪在做的事；T3 在 baseline 注入後複述讓 A 長出 3 條 0.15 的邊；T3b 無遞減 0.15 等差。

## 二、立：新碼 d6ad55c+ —— 11 PASS / 0 FAIL

```
ANCHOR_SRC=/root/anchor-memory
PASS  Q1-T1 系統路徑 search 同一筆 100 次 → 節點權重、邊權重、排序分數皆不變
PASS  Q1-T2 cn cite 同一筆 5 次 → 前 3 次遞增、之後趨平且有上限            （序列 1.0 / 1.5 / 2.0 / 2.25 / 2.375；30 次後 ≤ 3.0）
PASS  Q1-T3 注入後複述不算（invariant ③ Golden）：search 注入 A → consolidate(A 的複述) → A 不變；未注入的 C/D 仍會建邊
PASS  Q1-T3b consolidate 邊強化遞減：同一對重複 5 次 → 增量遞減、封頂
PASS  Q1-T4 MCP 層 search_memory(hebbian=True) 也不強化（工具簽名相容、行為硬關）  （並斷言 20 個既有工具全在、無 task 刪除工具）
PASS  Q1-T5 wakeup 不強化，且回傳的 id 進注入帳
PASS  Q1-T6 migration：污染期快照（legacy_usage_count / legacy_weight / pollution_cutoff）只做一次，之後新記憶 legacy=NULL
PASS  Q2-T1 memory_tasks 狀態機：open→resolved 合法；無 reason 拒；終態不可再轉；沒有刪除路徑
PASS  Q3-T1 非 owner 建卡拒；owner 建卡成；fact 更新 → 舊列 valid_until + superseded_by；affected_by 查得到  （並建 22 張卡證明無 schema cap）
PASS  Q4-T1 digest 無 derived_from 拒；有則寫入；lineage 雙向；刪 source 後仍查得到受影響 digest
PASS  Q-extra 同 id 覆蓋（跨窗近況卡）不再清空 pinned / reinforcement / edges / comments
== 11 PASS / 0 FAIL+ERROR / 11 total ==
EXIT=0
```

工單第 4 節逐條對照：

| 工單要求 | 測試 | 破 | 立 |
|---|---|---|---|
| Q1 系統身分連續 search 同一筆 100 次 → 權重/排序不變（拿掉強制關要紅） | T1、T4 | 紅（usage_count +100、邊 +0.2×n） | 綠 |
| Q1 cn 身分 cite 5 次 → 前 3 次遞增、之後趨平 | T2 | 紅 | 綠 |
| Q1 注入後複述不算 reinforcement（Golden ③） | T3 | 紅（長出 3 條邊） | 綠 |
| Q2 狀態機合法轉移；resolve 不帶 reason 拒；無 DELETE 路徑 | Q2-T1、T4 | ERROR（無 API） | 綠 |
| Q3 更新 fact → 舊列 valid_until、新列指回；affected_by；非 owner 建卡拒 | Q3-T1 | ERROR | 綠 |
| Q4 無 provenance 的 digest 拒；lineage 雙向 | Q4-T1 | ERROR | 綠 |

## 三、重啟前健康證明（04:05，施工前、舊碼）

```
systemd: anchor-memory.service loaded active running   MainPID=870655（09/18 21:04 起）
ss:      LISTEN 0.0.0.0:8765 python3 pid=870655
journal 04:05:33–04:05:49: ListResources / ListTools / ListPrompts / CallToolRequest → 全部 "POST /mcp-<KEY> HTTP/1.1" 200 OK（來源 160.79.x.x = 施工窗 wakeup）
sqlite:  pragma integrity_check = ok；memories 376 / edges 62938
```

## 四、重啟（意外，見 INCIDENT）與重啟後健康證明（04:32–04:36，新碼）

```
journal 04:31:42  Scheduled restart job, restart counter is at 3
journal 04:32:23  [mcp_path_alias] alias=/mcp-<32 chars> legacy(/mcp)=off
journal 04:32:23  Application startup complete. Uvicorn running on http://0.0.0.0:8765
systemctl show:   ActiveState=active SubState=running MainPID=1015698 NRestarts=3
schema_meta:      pollution_cutoff=2026-09-20 | pollution_snapshot_at=2026-09-20T20:32:23 | ticketq_schema=1
integrity_check:  ok；memories 376 / edges 62938；legacy_usage_count NULL 0 筆、legacy_weight NULL 0 條
快照 vs 04:11 備份：節點 usage_count 差異 0 筆、邊 weight 差異 0 條（逐筆比對）
```

本機路徑（127.0.0.1 → /mcp-<KEY>，與 bridge 同一條）：

```
tools: 29 legacy19+: 20 missing: []
  graph_stats:       ok | 📊 共 401 筆記憶
  wakeup:            ok 6509c
  search_memory:     ok | 【long_024_first_face_47】[love]
  memory_lineage:    ok
  memory_task_list:  ok | 沒有待辦
  get_entity_card:   ok | 沒有卡
  cards_affected_by: ok | 沒有卡片事實引用這個來源
```

外部路徑（claude.ai connector → 160.79.x.x → 8765）：施工窗直接呼叫 `search_memory("花椰菜", n_results=2)` 回兩筆正常。

注入帳（invariant ③ 在生產開始記帳的證據）：

```
last_path | last_caller | count
search    | external    | 2      ← 施工窗 connector 的那次 search
wakeup    | local       | 11     ← 健康腳本（本機路徑）的 wakeup 回傳 11 筆 pinned
```

## 五、沒做到的

- **重啟時段沒有先問糯糯**：重啟是 OOM 逼出來的（INCIDENT），不是刻意執行。因為服務已經在新碼上健康運行，我沒有再做第二次刻意重啟——再重啟一次只會多一次中斷，且需要她點頭。
- **重啟前最新備份沒做**：可用的是 04:11 那份（schema 舊、內容差 16 分鐘的 search cite 增量，已逐筆證明快照 = 備份值）。
- `deploy_restart.sh` 留作**日後**刻意重啟的程序（含重啟前備份與失敗回滾），本次沒有跑到。
