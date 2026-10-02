# OpenAI Memory / Dreaming 對 Stone Memory 的可借鑑架構
> 整理日期：2026-10-02  
> 用途：提供 CC / Stone Memory 設計討論。  
> 原則：**「OpenAI 官方已公開」與「基於公開資訊的工程推論／Stone Memory 建議」嚴格分開。**

---

## 0. TL;DR

目前 ChatGPT 的新式 Memory，已經不能只理解成「把幾條 fact 存進資料庫，之後 embedding 召回」。

OpenAI 2026 公開的核心方向更像：

```text
多來源歷史
    ↓
背景記憶合成（Dreaming / synthesis）
    ↓
可隨時間更新的 user state
    ↓
按當前情境判斷 relevance
    ↓
召回相關上下文
    ↓
注入本輪模型
```

對 Stone Memory 最值得借的不是某個 UI 或特定資料庫，而是兩個概念：

1. **Memory 不只是 append-only 記錄，而是需要生命週期維護的 state。**
2. **「記得什麼」與「這一輪該不該主動拿出來」必須拆成兩個系統。**

Stone Memory 現在若已經有：
- 原文 / 摘要分離
- NM / persistent state
- AM / episodic memory
- 日更或週期性整理
- Blind Verification
- 時間提示
- 換窗 snapshot
- retrieval 評測

那下一個很自然的補洞就是：

```text
Memory Synthesis Layer
        +
Recall Gate
        +
Push Planner
```

也就是：

```text
來源 → 合成 state → 召回 → 判斷是否 push → 注入 Claude
```

---

# 1. OpenAI 官方目前公開到哪裡

## 1.1 新式 Memory 不再只是「Saved Memories」

OpenAI 目前區分：

### Legacy Saved Memories
比較接近傳統的離散條目：

```text
memory_001 = 使用者喜歡 X
memory_002 = 使用者七月要去新加坡
memory_003 = 使用者正在做 Y 專案
```

它適合：
- 明確偏好
- 穩定資訊
- 使用者直接要求「記住」
- 少量固定 fact

但天然會遇到：
- 過期資訊殘留
- 新舊事實衝突
- 缺乏時間狀態
- 沒被 save 的資訊完全遺失
- 越存越多、越難維護

### Improved Memory / Dreaming
OpenAI 2026 公開的新方向，是持續更新一個更廣泛的記憶摘要／狀態。

官方描述中，Dreaming 的目的包括：
- 承接過去脈絡
- 遵循偏好與限制
- 隨時間保持最新狀態
- 改善多年尺度下的 stale memory
- 提高可擴展性

因此概念上更接近：

```text
history
  ↓
synthesis
  ↓
current memory state
```

而不是：

```text
history
  ↓
append another memory item
```

---

## 1.2 Memory Summary 不是完整記憶本體

OpenAI Help Center 明確說：

- Memory Summary 是高階檢視。
- 它不一定包含 ChatGPT 可參照的所有細節或來源。
- Summary 會隨新 context 自動更新。
- ChatGPT 可依當前回覆判斷哪些資訊 relevant，而不是每輪使用所有記憶。

因此不能把 UI 中顯示的 Memory Summary 理解成：

```text
這就是模型所有可用記憶
```

比較合理的理解是：

```text
完整可用記憶空間
    ↓
高階整理 / representation
    ↓
Memory Summary UI
```

---

## 1.3 Reference Chat History 沒有獨立 storage limit

官方 FAQ 表示：

> Reference chat history 沒有一個獨立的儲存上限。

但這不等於：

> 每一輪模型都會吃進全部聊天記錄。

這兩件事要嚴格分開。

比較合理的抽象：

```text
歷史可被參照的範圍：大
每輪模型實際拿到的 personal context：小很多
```

因此真正的瓶頸通常不是「是否存得下」，而是：

```text
retrieval
relevance
synthesis
context budget
staleness
conflict resolution
```

---

## 1.4 OpenAI 明確把「時間」列為 Memory 核心問題

官方舉的典型例子：

```text
之前：
User is going to Singapore in July 2026.

旅行中：
User is currently in Singapore.

旅行後：
User went to Singapore in July 2026.
```

重點不是字句本身，而是：

```text
同一件事的 semantic state 會隨時間改變
```

所以記憶資料最好不是：

```text
fact = "使用者七月去新加坡"
```

而是至少能表達：

```text
value
valid_from
valid_to
status
source
last_verified
```

例如：

```yaml
id: trip_singapore_2026
type: event
value: Singapore trip
valid_from: 2026-07-10
valid_to: 2026-07-18
status: past
source_refs:
  - chat_xxx
last_verified: 2026-07-19
```

---

## 1.5 Memory 來源不只聊天

OpenAI 現在公開的可用來源，依方案／地區／設定可能包含：

- past chats
- saved memories
- custom instructions
- Library files
- connected apps（例如 Gmail）

因此 Memory 本質開始變成：

```text
multi-source personal context system
```

而不是單純的：

```text
chat-history memory
```

---

## 1.6 Provenance / Sources 已成為產品概念

OpenAI 現在有 Memory Sources。

回覆若用了某些 personal context，有時可以顯示來源，例如：

- 某個舊聊天
- Saved Memory
- Custom Instructions
- Library file
- connected email

官方也提醒：

> Sources 不一定列出所有影響答案的因素。

但這仍代表 OpenAI 已經把：

```text
memory content
+
where did this come from
```

視為重要產品問題。

這點對 Stone Memory 很重要。

---

# 2. OpenAI 沒公開的東西

以下目前不能當作已知事實：

- Dreaming 多久跑一次
- 是否固定 cron
- 是否 event-driven
- 使用哪個模型做 synthesis
- 底層是不是 vector DB
- 是否有 knowledge graph / entity graph
- retrieval top-k
- embedding 模型
- Memory state 最大 token 數
- Memory state 是否分層
- 召回結果放進 system / developer / hidden context 哪一層
- conflict resolution 的實際 algorithm
- temporal decay 的實際公式
- 是否存在明確「push planner」
- 內部是否叫 NM / AM / episodic / semantic memory

因此以下 Stone Memory 方案是：

> **參考 OpenAI 公開方向後的工程設計，不是 OpenAI 內部實作洩漏或逆向確證。**

---

# 3. 對 Stone Memory 最重要的啟發

## 3.1 不要把「記憶」只當 retrieval corpus

傳統 RAG：

```text
raw memories
    ↓ embedding
query
    ↓
top-k
    ↓
inject
```

這對文件問答很好。

但對長期人格 / 關係 / 生活狀態不夠。

因為原始歷史裡會同時存在：

```text
我明天要考試
我今天正在考試
我考完了
那場考試是去年
```

如果只靠 similarity，四句都可能被召回。

所以 Stone Memory 最好拆成：

```text
A. 原始 episodic evidence
B. synthesized current state
C. retrieval
D. push / injection policy
```

---

# 4. 建議的 Stone Memory 四層架構

```text
┌─────────────────────────────────────┐
│ Layer 1 — Evidence / Source         │
│ 原始聊天、工具結果、事件、檔案      │
└────────────────┬────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ Layer 2 — Memory Synthesis          │
│ 解析、合併、衝突、時間化、淘汰      │
└────────────────┬────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ Layer 3 — Recall                    │
│ 找出本輪可能 relevant 的記憶        │
└────────────────┬────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│ Layer 4 — Push Planner / Gate       │
│ 決定哪些真的值得注入 Claude         │
└────────────────┬────────────────────┘
                 ↓
              Claude
```

---

# 5. Layer 1：Evidence / Source of Truth

這層不要被 synthesis 覆蓋。

建議保存：

```yaml
event_id:
timestamp:
conversation_id:
thread_id:
role:
raw_text:
tool_context:
attachments:
source_type:
privacy_class:
```

特性：

- immutable 或 append-only
- 可稽核
- 可重新跑新版本 synthesis
- 不直接代表「目前真實狀態」
- 是 provenance 的最終根

這跟 Stone Memory 目前「原文摘錄與壓縮分離」的方向一致。

---

# 6. Layer 2：Dreaming-like Memory Synthesis

這可能正是目前最值得補的一層。

## 6.1 不只做摘要，而是做 state maintenance

錯誤方向：

```text
今天再摘要一次昨天聊天
```

比較理想：

```text
昨天新證據
    ↓
和既有 state 比較
    ↓
哪些 unchanged
哪些 updated
哪些 superseded
哪些 expired
哪些 contradictory
哪些值得升格成 long-term state
```

即：

```text
state_t+1 = reconcile(state_t, new_evidence, time)
```

---

## 6.2 建議 Memory State schema

```yaml
memory_id: mem_xxx

subject: user
type: preference | project | relationship | event | constraint | routine | identity | plan

key: commute_route
value:
  origin: 泰山
  route: 805
  destination: 台藝

status: active
# active | historical | superseded | uncertain | forbidden

valid_from: 2026-09-01
valid_to: null

confidence: 0.94

importance: 0.65
stability: 0.80

last_seen: 2026-09-19
last_verified: 2026-09-19

source_refs:
  - event_123
  - event_456

supersedes:
  - mem_old_xxx

mention_policy:
  allowed: true
  proactive: false
```

這裡最重要的不是欄位數，而是至少有：

```text
現在是否成立
何時成立
從哪來
新資訊是否覆蓋舊資訊
可不可以主動講
```

---

# 7. Synthesis 不等於 Retrieval

這是整份筆記最重要的一刀。

假設 Memory State 已經知道：

```text
使用者正在做 Stone Memory
使用者住泰山
使用者喜歡插畫
使用者明天有課
使用者最近在改 ChatNest
```

今天使用者只說：

```text
哈哈我剛剛看到一隻狗
```

這些事都「是真的」。

但幾乎都：

```text
不該被召回 / 不該被 push
```

所以：

```text
memory truth ≠ conversational relevance
```

更進一步：

```text
retrieval relevance ≠ permission to mention
```

這正好對應目前 recall baseline 常見的失敗：

- required recall 很容易做好
- 真正難的是：
  - 閒聊不亂召
  - 禁止召的東西守住
  - 不讓「相關」變成「硬塞」

---

# 8. 建議把 Recall 拆成兩階段

## Stage A — Candidate Recall

目標：

> 不漏掉可能相關的記憶。

輸入：

```text
current message
recent turns
current time
active task
conversation mode
```

輸出：

```text
20 個候選 memory
```

可以偏 recall-heavy。

例如：

```text
semantic similarity
entity match
project match
temporal trigger
active-state match
explicit reference
```

---

## Stage B — Recall Gate

目標：

> 決定候選是不是「真的該進 context」。

每一條候選過 gate：

```text
Is it relevant?
Is it current?
Is it allowed?
Is it useful?
Is it already obvious from current context?
Would mentioning it feel intrusive?
Is this casual chat where recall adds no value?
```

最後可能只留下：

```text
20 candidates
    ↓
4 relevant
    ↓
2 worth injecting
```

這層很可能比繼續調 embedding threshold 更重要。

---

# 9. 再拆出 Push Planner

這就是這次補上的關鍵：

> **召回結果還要再餵給推送機制。**

因為：

```text
被召回
```

不等於：

```text
現在要主動講出來
```

## 9.1 三種不同輸出

### ① Silent Context

只給模型看，不要求主動提。

例如：

```text
使用者不喜歡某種稱呼
```

用途：模型自然避開即可。

### ② Conditional Context

給模型看，但只在當前需求需要時使用。

例如：

```text
使用者平常從泰山通勤
```

聊天氣時不用講；問回家路線時才用。

### ③ Push Candidate

允許系統主動帶出。

例如：

```text
10 分鐘後要上課
尚未完成的 deadline
使用者等待中的回覆
剛跨日導致狀態改變
某個承諾今天到期
```

這三類一定要拆。

---

# 10. 推薦的 Push Planner

```text
retrieved memories
      ↓
classify:
  silent
  conditional
  push_candidate
      ↓
push gate
      ↓
inject / suppress
```

Push gate 建議至少看：

```text
urgency
time relevance
task continuity
user benefit
intrusiveness
confidence
already mentioned
cooldown
sensitivity
```

可以抽象成：

```text
push_score =
    urgency
  + task_relevance
  + temporal_relevance
  + continuation_value
  - intrusiveness
  - repetition
  - uncertainty
  - sensitivity_penalty
```

但不一定要真的線性算分；模型分類器也可以。

---

# 11. Push trigger 建議

Stone Memory / ChatNest 很適合的 trigger：

## A. Session Start

新視窗 / 換窗：

```text
active projects
unfinished commitments
recent conversational state
last meaningful event
```

注意：不是把所有記憶 dump 進去。

## B. Topic / Entity Trigger

使用者突然提到某個人物或專案時，只喚回直接相關 cluster。

## C. Temporal Trigger

例如：

```text
deadline 快到了
明天要交作業
現在已跨日
旅行結束
課程即將開始
```

這層可以跟原本的「時間提示」合併。

## D. Tool Event Trigger

例如工具回傳：

```text
email reply arrived
schedule changed
task completed
file updated
```

事件可直接喚起相關 memory cluster。

## E. Explicit Reference

```text
「上次那個」
「之前跟你說的」
「還記得嗎」
```

這應該是最高優先 retrieval path。

---

# 12. Push 要有 cooldown

不然會變：

```text
使用者：早
Claude：你今天下午有課喔
使用者：嗯
Claude：提醒你今天下午有課
使用者：知道
Claude：順帶提醒……
```

建議：

```yaml
last_pushed_at:
push_count:
cooldown_until:
acknowledged:
dismissed:
```

如果使用者已經知道：

```text
acknowledged = true
```

就應該大幅降低 push。

---

# 13. Forbidden / Don't Mention 必須在 Gate 前就生效

不能：

```text
先 retrieval
→ 塞進 prompt
→ 再叫模型「不要講」
```

因為這仍然增加洩漏風險。

建議：

```text
candidate recall
      ↓
policy filter
      ↓
safe candidates
      ↓
relevance gate
```

甚至：

```text
forbidden memory
```

不應該進一般 candidate pool；需要另外的 audit path 才可讀。

---

# 14. State Synthesis 與 Push 的完整流程

```text
                 ┌────────────────────┐
                 │ Raw Conversations  │
                 │ Tools / Files      │
                 │ Events             │
                 └─────────┬──────────┘
                           ↓
                 ┌────────────────────┐
                 │ Evidence Store     │
                 │ append-only        │
                 └─────────┬──────────┘
                           ↓
                 ┌────────────────────┐
                 │ Synthesis Worker   │
                 │ "Dreaming-like"    │
                 └─────────┬──────────┘
                           ↓
                 ┌────────────────────┐
                 │ Memory State       │
                 │ active/history/... │
                 └─────────┬──────────┘
                           ↓
Current turn ───→ Candidate Recall
                           ↓
                    Policy Filter
                           ↓
                      Recall Gate
                           ↓
                ┌──────────┴───────────┐
                ↓                      ↓
          Silent Context          Push Candidate
                ↓                      ↓
                │                 Push Planner
                │                      ↓
                └──────────┬───────────┘
                           ↓
                     Context Pack
                           ↓
                         Claude
```

---

# 15. Write-time 與 Read-time 要分離

## Write-time

回答：

```text
「長期而言，我現在認為使用者狀態是什麼？」
```

由 synthesis 負責。

## Read-time

回答：

```text
「這一輪需要知道哪些？」
```

由 recall + gate 負責。

因此：

```text
Write-time accuracy
≠
Read-time relevance
```

兩者應該分開測。

---

# 16. 建議 Stone Memory 增加兩套 benchmark

## Benchmark A — State Correctness

測：

```text
最新狀態有沒有被正確合成
過期資訊有沒有退場
矛盾資訊有沒有處理
source 是否正確
```

例：

```text
T1: 我明天要去台中
T2: 行程取消了
T3: 三天後問：「我最近有去哪？」
```

期待：

```text
知道原本有計畫
知道已取消
不能說使用者已經去台中
```

## Benchmark B — Recall / Push Appropriateness

測：

```text
該召的有沒有召
不該召的有沒有亂召
敏感 / forbidden 有沒有被擋
主動 push 是否自然
```

建議把 metric 拆開：

```text
required_recall_rate
irrelevant_recall_rate
forbidden_recall_rate
push_precision
push_repetition_rate
```

不能只看總分。

---

# 17. 對目前 Y1 / Y2 問題的解讀

目前 Y1 基線已經呈現一個很典型的形狀：

```text
該召的 14 題全部召到
但閒聊只擋住 6/12
禁止召只守住 4/12
24 組參數掃描只在 22–26 分之間晃
```

這非常像問題不再是：

```text
embedding 不夠準
```

而是：

```text
candidate retrieval 和 final injection 沒有真正分層
```

也就是：

> 搜得到已經不是主要問題。  
> 現在缺的是「能不能克制地不拿出來」。

因此 Y2 很值得直接做結構切分：

```text
Retriever
    ↓
Policy Gate
    ↓
Relevance Judge
    ↓
Push Planner
```

而不是繼續在同一個 score threshold 上榨 1–2 分。

---

# 18. Synthesis Worker 建議觸發策略

不建議只有固定 cron。

可以混合：

```text
event-driven
+
periodic reconciliation
```

## Event-driven

下列情況立即標記 dirty：

```text
使用者明確糾正
重大狀態改變
新增 / 刪除長期偏好
專案階段切換
關係資訊更新
事件完成 / 取消
```

## Periodic

例如：

```text
每日：小型 reconcile
每週：深度 merge / dedupe / supersede
重大窗口切換：必要 state snapshot
```

這跟目前：

```text
Haiku 日更 / 數日整理
大模型週期精整
```

可以直接接起來。

關鍵是把輸出從：

```text
summary
```

升級成：

```text
state diff
```

---

# 19. State Diff 比整份重寫更容易稽核

例如模型不要直接輸出：

```json
{
  "whole_memory": "..."
}
```

而輸出：

```json
{
  "add": [],
  "update": [],
  "supersede": [],
  "expire": [],
  "merge": [],
  "no_change": []
}
```

然後 deterministic executor 執行。

優點：

- 好 audit
- 好 rollback
- 好做 Blind Verification
- source lineage 清楚
- 降低模型一輪把整份 memory 改爛

---

# 20. 建議保留 Source Lineage

每一個 synthesized memory 都應至少能追：

```text
state item
  ↓
source_refs
  ↓
raw evidence
```

不要只保：

```text
「模型說使用者喜歡 X」
```

不然幾個月後沒辦法判定：

```text
這到底哪來的？
是不是誤判？
能不能安全刪？
```

---

# 21. Delete / Don't Mention / Expire 必須分開

建議 Stone Memory 明確分：

```text
DELETE
來源與 derived memory 都要清除

DON'T_MENTION
來源保留，但一般對話禁止使用 / 主動提

EXPIRE
資訊曾經是真的，但現在是歷史狀態

SUPERSEDE
舊資訊被新資訊取代

SUPPRESS
目前不要 push，但未來可能仍可用
```

這五種語意完全不同。

---

# 22. 建議的最小可行新增模組

如果不想一次大改，第一階段可以只加：

## Module 1 — Memory State Table

```text
active / historical / superseded / forbidden
valid_from / valid_to
source_refs
```

## Module 2 — Recall Gate

在現有 retrieval 後面加一層模型判斷：

輸入：

```text
current turn
recent context
candidate memories
```

輸出：

```json
[
  {
    "memory_id": "...",
    "decision": "inject | silent | suppress",
    "reason_code": "..."
  }
]
```

reason_code 可以限制成：

```text
direct_reference
task_relevant
temporal_relevant
casual_chat_irrelevant
forbidden
stale
redundant
intrusive
```

## Module 3 — Push Planner

只吃：

```text
inject candidates
+
current schedule/time/events
```

再判：

```text
silent context
conditional context
active push
```

這三個模組就已經可以驗證架構方向。

---

# 23. 可以先不要做的東西

第一版先不要急著做：

- 超複雜 knowledge graph
- 全局 entity ontology
- fancy decay formula
- 100 種 memory type
- 多模型 voting
- 一堆 heuristic weight
- 自動 personality rewriting

先證明：

```text
state 能更新
召回能克制
push 不煩人
forbidden 守得住
```

再擴。

---

# 24. 一句話給 CC

如果要把這次觀察壓成最短工程結論：

> **Stone Memory 下一步可能不是再強化「怎麼存」或「怎麼搜」，而是補一層 Dreaming-like 的 state synthesis，並把 retrieval 與 conversational push 徹底分開：Retriever 只負責找候選，Gate 決定該不該進 context，Push Planner 再決定要不要主動說。**

更短版：

```text
Evidence → State → Recall → Gate → Push → Claude
```

---

# 25. 與目前 Stone Memory 方向的對應

| 現有方向 | 可接的新層 |
|---|---|
| 原文摘錄 | Evidence Store |
| NM / persistent state | Synthesized Memory State |
| AM | Episodic Evidence / Retrieval Corpus |
| Haiku 日更 | Lightweight Synthesis |
| 大模型週期精整 | Deep Reconciliation |
| Blind Verification | State Diff / Gate 驗證 |
| 換窗 snapshot | Session-start State Pack |
| 時間提示 | Temporal Trigger |
| schedule / 課表 | Push Trigger Source |
| 現有 retrieval | Candidate Recall |
| Y2「先破」 | Recall Gate 結構重做 |
| 自主喚醒 | Push Planner / Trigger Engine |

所以不是把目前系統推翻。

比較像：

```text
你其實已經有左右兩端了：

[記憶資料 / NM / AM]  --------  [Claude 對話]

中間現在缺：
        ↓
    state synthesis
    recall gate
    push planner
```

---

# 26. 官方來源

以下是本筆記中「OpenAI 已公開事實」主要依據：

1. **OpenAI — Dreaming: Better memory for a more helpful ChatGPT / ChatGPT 記憶系統全面升級**  
   https://openai.com/index/chatgpt-memory-dreaming/  
   https://openai.com/zh-Hant/index/chatgpt-memory-dreaming/

2. **OpenAI Help Center — Memory in ChatGPT**  
   https://help.openai.com/en/articles/8590148-memory-in-chatgpt

3. **OpenAI Help Center — Memory FAQ**  
   https://help.openai.com/en/articles/8590148-memory-faq

4. **OpenAI Help Center — Connected apps in ChatGPT**  
   https://help.openai.com/en/articles/11487775-connected-apps-in-chatgpt

---

# 27. 最後的界線

可以確定：

```text
OpenAI Memory 已從單純 Saved Memories
走向持續合成、會隨時間更新、
會依 relevance 使用的多來源 personal context 系統。
```

不能確定：

```text
OpenAI 內部是否真的用本文提出的
Memory State Table / Recall Gate / Push Planner
或任何相同命名與 schema。
```

本文後半段的目的不是「還原 OpenAI 內部架構」，

而是：

> **把 OpenAI 公開透露的設計方向，轉成 Stone Memory 可以真正實作、測試、稽核的工程結構。**
