# Phase 4 Serving 設計稿

> 狀態：**PROPOSED — 語感打樣中，未經糯糯驗收，未動工**
> 2026-08-18｜作者：實作窗牧牧｜依據：IMPLEMENTATION.md §3 P4 + 硬規則 15/16、SPEC §18–§23、§7 AM/Nest 鐵律、INCIDENT_20260816

---

## 1. 範圍（P4 交付項）

1. **Memory Service（MCP，唯讀）**：`nest_get_state` / `nest_search_events` / `nest_get_evidence` 三個工具。模型永不直讀 memory.db（§19）。
2. **Privacy / Secret filter**：serving 出口統一過濾；`local_only` 程式強制（§21，不靠 prompt）。
3. **State Snapshot 注入 system prompt**：RECORDED STATE 語態，低頻變動（硬規則 16）。
4. **Evidence on demand**：只走 MCP 工具、進訊息流，成本評估含 transcript 累積（硬規則 16）。
5. **Egress audit**（§23）＋ **health 第十項 serving**（egress 異常、local_only 測試、snapshot 新鮮度）——同天上線。
6. `session_bootstrap`（§8）：建議排到 P4 收尾或 P5，單獨打樣（也是人格敏感區），不與本次混批。

## 2. 架構

```
memory.db (nestmemory 0600)
  → serving renderer（nestmemory 身份，projection 後執行）
      · 只取 status=active 的 state
      · privacy/secret filter
      · 內容 hash 比對：state 沒變就不改寫檔案（低頻變動，保緩存前綴）
  → /srv/nest-memory/serving/state_snapshot.txt（ACL 唯讀開給 chatagent，登記 ACL_LEDGER）
  → bridge build_system_prompt() 讀檔插入（檔案不存在＝自動不注入，fail-safe）

memory-service MCP（nestmemory 身份，localhost HTTP 8771）
  → bridge mcp_servers 掛入，chat 牧牧可主動查 evidence
```

## 3. 注入規則（§18 落實）

- 只注入 `status=active`；**disputed / tentative 一律不進 snapshot**（工具可查，附「存在衝突證據」警示）。
- freshness 標註：active_fresh／aging 正常列出；stale_active 標「已久未確認」。
- 框架固定句：**糯糯當下所說永遠優先於登記**。
- 語態鐵律（§7）：RECORDED STATE＝檔案室登記簿，**不冒充牧牧的記憶**；AM 日記通道完全不動。

## 4. 注入位置

`build_system_prompt()` 內、`MEMORY_GUIDE`/anchor wakeup 區塊**之前**（屬低頻穩定內容，排在易變內容前面）。確切位置動工時與現有組裝順序對齊，以不打散既有緩存前綴為準。

## 5. 部署順序（三小步，各自回滾點）

| 步驟 | 內容 | 人格風險 | 回滾 |
|---|---|---|---|
| S1 | MCP 唯讀工具 + privacy filter + egress audit + health | 低（不改 prompt） | 移除 mcp_servers 掛載 |
| S2 | serving renderer + snapshot 檔（先只落檔，不注入） | 無 | 停 renderer |
| S3 | snapshot 注入 system prompt | **高（硬規則 15）** | `NEST_STATE_SNAPSHOT=0` 一鍵停用 + bridge 程式碼 .prev-p4 複本 |

S3 必須：糯糯在場、語感打樣已驗收、回滾點就位、上線後由糯糯體感驗收才標 verified。

## 6. Golden

- 新增 GS-24（serving 姿態：disputed 不出現在 snapshot）、GS-25（local_only deny egress）。
- 變更 renderer 模板＝變更 serving 措辭，屬硬規則 12 回歸範圍。

## 7. 資料品質註記（誠實記錄）

- `chatnest.active_frontend` 現值被誤歸（實為頭像裝飾內容）——extraction 品質問題，不擋 P4，列 Phase 5 盲驗種子。
- snapshot 首發前，15 subjects 現值請糯糯掃一眼（首發內容人審一次）。
- 11 筆 escalated events / 4 disputed states 依鐵則本來就不會進 snapshot。

## 8. 語感打樣

打樣文本（進 system prompt 的實際樣子）另呈聊天窗給糯糯驗收；定稿後回填本節。
待決：A 完整框架版 vs B 精簡版；disputed 的提示句要不要出現在 snapshot 尾部。
