# TICKET-Q Q1 盤點報告：Hebbian / reinforcement 路徑與 legacy 污染現狀

日期：2026-09-21（台北）　範圍：anchor-memory 服務（8765）與 `/root/anchor-memory/memory_data/memories.db`
Baseline：anchor repo commit `7c2e317`（施工前生產工作樹快照）　備份：見交付清單

## 一、所有會「強化」的路徑（Q1.1）

「強化」有兩種：**節點**（`memories.usage_count` → 進排序的 `citation_boost = min(usage_count×0.02, 0.15)`）與**邊**（`edges.weight` → 進 associative recall 的門檻 1.5 與 `get_neighbors`）。

| # | 路徑 | 強化什麼 | 量 | 誰觸發 | 施工前 | 施工後 |
|---|---|---|---|---|---|---|
| 1 | `AnchorMemory.search()` 末段 `self.db.cite()` 對**每筆回傳** | 節點 usage_count +1 | 每次檢索 ×n_results | 所有 search_memory 呼叫端（系統與 cn 都是） | `no_cite` 參數存在但 MCP 層沒暴露，**永遠 cite** | 硬關。檢索永不 cite；`no_cite` 留簽名被忽略 |
| 2 | `AnchorMemory.search()` Hebbian 區塊 `connect_batch(pairs, 0.2)` top-n 兩兩 | 邊 +0.2/次，封頂 10 | 每次檢索 C(n,2) 對 | 同上，`hebbian` 預設 True | bridge 沒傳 hebbian → True | 硬關。`hebbian` 留簽名被忽略 |
| 3 | `AnchorMemory.consolidate()` `connect_batch(pairs, 0.15)` | 邊 +0.15/次，無遞減 | cn 主動（對話結束前） | 匹配到的全部兩兩建邊，含剛被注入的 | 保留，改 `reinforce_pairs()` 遞減封頂；**注入視窗內的記憶跳過**（invariant ③） |
| 4 | `AnchorDB.cite()`（MCP `cite_memory`） | 節點 usage_count +1 | cn 主動 | 無上限 | 改 `reinforce()`：1.0 / 0.5 / 0.5 / 0.25 / …，累積封頂 3.0；不再動 usage_count |
| 5 | `AnchorDB.annotate()`（MCP `annotate_memory`） | 無（只 log_event） | cn 主動 | 不強化 | 加 `reinforce(reason=annotate)`，同上遞減 |
| 6 | `AnchorDB.connect()`（MCP `connect_memories`、`store(connect_to=)`） | 邊 +weight（預設 2.0） | cn 明確 | 不變 | 不變（明確動作，非檢索） |
| 7 | `dream_pass()` step 4 auto_discover：內部 `search(hebbian=False)` 後對無邊者 `connect(0.3)` | 邊建立 0.3（只在無邊時） + 內部 search 的 cite | cn 主動 `dream_pass` 工具（crontab 無排程） | 內部 search 會 cite | 內部 search 不再 cite（路徑 #1 已關）；0.3 建邊保留（不疊加既有邊） |
| 8 | `AnchorDB.wakeup()` | 無 | bridge 每 10 分鐘快取 / wake_runner | 本來就不強化（註解明說） | 不變；回傳的 id 記進注入帳 |
| 9 | `auto_consolidate.py` / `concept_link.py`（LLM 建邊 1.0 / +0.1） | 邊 | 無人呼叫（crontab 無、`_eager_link=False`） | 死路徑 | 不動 |
| 10 | `dream_extras.py`（dedup / fact_check） | 不強化 | 無排程 | — | 不動 |

**判定方式**：依路徑硬關，不看 caller 傳的旗標。search / wakeup / 內部檢索是「檢索路徑」，一律不強化；只有 cite / annotate（節點）與 consolidate（邊）三個明確動作強化，且遞減封頂。這比「依身分」更強：cn 主動 search 也不強化，因為搜尋 ≠ 用到（R6 原文：只保留給 cite/consolidate 這類「真的用到了」的動作）。

## 二、呼叫端盤點（系統 vs cn 主動）

| 呼叫端 | 路徑 | 打什麼 | 類別 | 備註 |
|---|---|---|---|---|
| bridge `memory_bridge.search_memories()` ← `claude.py` 每輪 user 訊息（<6 字與喚醒模板跳過） | 127.0.0.1 → `/mcp-<KEY>` | `search_memory(query, n_results=3)`，**沒傳 hebbian → True，且 cite** | **系統（被動注入）** | 最大污染源：每輪對話 3 筆 cite + 3 對邊 |
| bridge `_call_wakeup()`（10 分鐘 TTL 快取） | 127.0.0.1 | `wakeup(n_high_emotion=0, n_random=0)` | 系統（開場注入） | 不強化 |
| bridge `mark_injected_comments()` | 127.0.0.1 | `mark_comments_read` | 系統 | 不強化 |
| wake_runner.py（`/srv/chatnest/full-stack`，legacy） | 127.0.0.1 → `/mcp`（**舊路徑，已被 MCP_LEGACY_PATH=0 關掉 → 404**） | wakeup / search_memory | 系統（排程喚醒） | 現況打不到 anchor；不在本單範圍，記錄供後續 |
| 聊天窗口的牧牧（bridge 內 Claude Agent SDK）主動叫 `mcp__anchor__*` | 127.0.0.1 | 全部 19 個工具 | **cn 主動** | 與被動檢索同一條 HTTP 路徑，source ip 一樣是 127.0.0.1——所以 by-identity 分不開，by-path 才分得開 |
| claude.ai connector（CC 窗口 / 糯糯的 Claude） | 160.79.x.x 直連 → `/mcp-<KEY>` | 全部工具 | cn 主動 / owner 代理 | external |
| nest-memory（extractor / projection / health / console / serving） | — | **不打 anchor** | — | grep `/srv/nest-memory/bin` 只有 swap_watch 量 RSS |
| swap（TICKET-N 盲測那條） | — | 走 nest-serving，不打 anchor | — | 不在 anchor 內 |

過去 7 天 anchor journal：本機 POST 626 次、外部 42 次（含 initialize / list）。

**caller class 記錄**：新碼在 `search_memory` / `wakeup` 用 FastMCP `Context` 讀 client ip 與 `cf-connecting-ip` 標 `local` / `external`，只寫進注入帳（`injections.last_caller`）供審計，**不做為強化判定**。

## 三、legacy 污染現狀（Q1.3，只盤點不回滾）

快照時間：新碼第一次啟動時由 migration 自動做（`schema_meta.pollution_snapshot_at`），`usage_count → legacy_usage_count`、`edges.weight → legacy_weight`，污染期標記 `pollution_cutoff = 2026-09-20`。以下數字取自施工前備份 `memories.db.bak-ticketq-20260921_041130`。

### 3.1 規模

- 記憶 376 筆（core 56 / long 300 / short 20；pinned 11）
- 邊 62,938 條（有向，雙向各一）→ 每節點平均 out-degree **182**，最高 331（= 幾乎全連通；376 節點的完全圖是 375）
- events：consolidated 2,336、connected 50（明確建邊）、annotated 17、created 496、deleted 23

### 3.2 邊權重分佈

| 區間 | 條數 | 平均 |
|---|---|---|
| 10（封頂） | 28 | 10.0 |
| 5–10 | 729 | 6.7 |
| 1.5–5（≥ associative 門檻） | 1,312 | 2.56 |
| 1.0–1.5 | 2,118 | 1.19 |
| 0.5–1.0 | 8,830 | 0.69 |
| < 0.5 | 49,921 | 0.23 |

- 有明確 `connected` event 對得上的邊：**40 條**（50 個 event）。其餘 62,898 條沒有明確建邊紀錄 → 來源只能是 search Hebbian（0.2/次）、consolidate（0.15/次）、dream auto_discover（0.3）。
- 權重是 0.2 整數倍且未封頂（純 search Hebbian 特徵）：3,304 條。其他是混合疊加（0.2 與 0.15 混、經 dream_pass ×0.9 衰減後）——**無法逐條歸因**，這就是 invariant ① 說的「不假裝精確修復」。
- 建邊月份：4 月 1,463 / 5 月 235 / 6 月 13,296 / 7 月 6,182 / 8 月 26,620 / 9 月 15,142。8 月起爆量，對應 bridge 被動注入上線（P2.5 後續）。
- 觸發過 associative recall 門檻（≥1.5）的邊有 2,069 條——這些是「系統檢索製造出來的聯想」最可能藏身處。

### 3.3 節點 usage_count 分佈

| usage_count | 筆數 |
|---|---|
| 0 | 215 |
| 1–4 | 69 |
| 5–19 | 20 |
| 20–49 | 26 |
| 50–99 | 20 |
| 100+ | 26 |

Top：`2026_06_12_keyan_voice_soon` 337、`core_006_milestones` 314、`core_011_one_month_letter` 258、`2026_04_14_anchor_memory_init` 257、`long_001_nicknames` 235……前 25 名全在 100 以上，最後被用時間幾乎都是 9/20 當天——**這是每輪被動檢索 cite 出來的，不是 cn 引用出來的**（cite_memory 的明確使用在 events 裡只有 annotated 17 筆可佐證頻率極低）。這些數字已經進了 `citation_boost`（封頂 0.15，26 筆已到頂），所以熱者恆熱（小踢的馬太效應擔心已經在發生）。

### 3.4 處置

- **不回滾**。`usage_count` 與 `edges.weight` 原值保留繼續用（排序沿用，P1b 換 ranker 時再決定），只做快照 + 標記。
- 新訊號從零開始：`reinforced_count` / `reinforcement`（節點）、`hebb_count`（邊）只記污染期後的乾淨動作。
- P1b 接手時的建議（不在本單）：ranker 的 `reinforcement` 訊號讀 `reinforcement` 欄，不讀 `usage_count`；associative 門檻是否對 legacy 邊另訂，由 P1b 裁。

## 四、測試（先破後立）

見 `TEST_OUTPUT.md`。
