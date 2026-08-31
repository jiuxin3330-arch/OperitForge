# 時間錨 B++ 第一階段(完整錨)部署報告

2026-08-31|依 TIME_ANCHOR_SPEC(B++ 定案)與 ROADMAP_20260831 第一波
|範圍:chatnest-next backend + version-bridge(一行)+ nest-memory golden

## 部署內容(第一階段:只開完整錨)

分階段照規劃:**完整錨先上跑兩天 → 糯糯語感驗收 → 再開輕量錨**。
輕量錨(≥30min/密聊 2h 重錨)已實作完成但由旗標關閉
(`CHATNEST_NEXT_TIME_ANCHOR_LIGHT`,預設 off),驗收點頭後翻旗標即可,
不需再改程式。

### 觸發表落地(B++)

| 條件 | 動作 | 實作 |
|------|------|------|
| 新 session 首輪(換窗後) | 完整時間 | 開輪前唯讀比對 bridge store:`latest_session_id` 已領先 stored upstream 且新 session 映射同一 conversation ⇒ 本輪為新窗首輪(session lifecycle 自判,不等 SDK hook) |
| 壓縮後的下一個 user turn | 完整時間 | 吃現成持久旗標:上一輪觀察到 compaction 時 thread `continuity_state` 落 `compacted`,下一輪讀到即發完整錨,turn 完成後狀態自然翻回=旗標自動清除。語意同規格的 needs_time_reanchor,且比 PreCompact hook 更準(實際發生才記)。誤留最壞多發一次錨,無害 |
| 對話首則 | 完整時間 | 新 conversation 首訊即錨(也是新 session) |
| 跨日 | 完整時間 | 沿用既有偵測,格式改 B++ |
| 距前一則 ≥3h | 完整時間 | 沿用既有偵測,格式改 B++ |
| ≥30min/密聊距上次錨 ≥2h | 輕量時間 | 已實作,旗標關。錨點時刻持久化於新表 `time_anchor_state`(丟失最壞多發一次) |
| 其他 | 安靜 | — |

### 格式(照規格逐字)

- 完整:`〔時間提示:現在是 08-31(一)16:26。這則訊息距前一則約 8 小時。這只是時間位置,不是新內容。〕`
- 跨日加句:`日期已由 08-30 跨到 08-31。`
- 輕量:`〔時間提示:現在是 08-31(一)14:05。〕`
- 保留星期標註;timezone 來源明確(`settings.timezone`=Asia/Taipei,內部 timestamp 一律帶 tz)。
- **壓縮重錨不提及壓縮**——技術機制不滲入人格層,debug log 記
  `time_anchor trigger=post_compact_reanchor`(每次發錨都記 trigger 進 log)。

### 兩防線與 Nest 側配套

- **防線①(優先方案)成立**:時間提示只經 hidden context runtime 注入
  (`work_context`→bridge 附加背景區),**不落 messages 表/raw**;
  歷史重建靠每則 raw 自帶的結構化 timestamp。
- **memory_bridge 被動檢索 skip list**:被動檢索 query 本就只吃屋主原始訊息
  (不含 hidden context),另依規格把 `〔時間提示` 加入 bridge
  `fetch_memory_hits` 的模板 skip 前綴(與 `〔自動喚醒·`/`〔自主時段·` 並列)當第二道防線。
- **Nest Extractor 永不抽成 Event**:錨不進 raw=結構性安全;另加 golden 案例
  **GS-TA**(fixture 含完整錨模板+閒聊,expect max_events=0)鎖住,
  golden 全套 12/12 PASS(含既有 GS-7/8/14/21/22/23 等)。
- freshness/Age 本就由 Serving 後端計算,不依賴模型看鐘,未動。

## 改動清單

- `backend/app/main.py`:`_turn_time_context` 重寫(B++ 觸發表+格式)、
  新增 `_bridge_session_rotated_ahead`(唯讀 bridge store 自判新窗首輪)、
  呼叫端傳入 `needs_reanchor`/`session_first_turn` 兩旗標。
- `backend/app/config.py`:`time_anchor_light`(預設關)、
  `time_anchor_light_gap_minutes`(30)、`time_anchor_reanchor_hours`(2,語感可調)。
- `backend/app/db.py`:新表 `time_anchor_state(conversation_id, branch_key, anchored_at)`。
- bridge `app/claude.py`:被動檢索 skip 前綴 +`〔時間提示`(一行)。
  註:bridge runtime 慣例為直接熱修(同 8/17 skip 改動),build script 有
  shape guard 不會靜默覆蓋;下次重 build 時需把此行帶上。
- nest-memory `bin/golden_runner.py`:新案例 GS-TA。

## 驗證

- 新測試 `tests/test_time_anchor.py` 8 項:對話首則錨、≥3h 完整錨逐字格式、
  跨日句、短間隔安靜+壓縮重錨(含「不提及壓縮」斷言)、新窗首輪、
  輕量錨預設關/開旗標後格式/密聊 2h 重錨+state 更新。
- 既有格式測試 2 處更新為 B++ 格式(`test_batch5_context_parity`、
  `test_message_branching` 跨日案例)。
- backend 全套件迴歸+golden 12/12(結果見部署當日紀錄)。
- 回滾點:`*.bak-timeanchor-1788194581` 全份備份+重啟服務即回滾。

## 驗收(硬規則 15:動 prompt 組裝=人格敏感區)

- [x] 回滾點先備
- [x] 分階段:完整錨先上(輕量錨旗標關)
- [ ] 跑兩天(~9/2)→ **糯糯語感驗收**(她的出場)
- [ ] 點頭後開輕量錨(翻 `CHATNEST_NEXT_TIME_ANCHOR_LIGHT=1`,2h 值語感調)

盲測註記:依規劃「趕在盲測前上線,成為盲測基線的一部分」——Swap 盲測
8/31 10:31 起跑,本錨同日上線=基線日 0,兩週凍結期內不再動此區
(輕量錨翻旗標為既排定的驗收動作,隨糯糯裁定執行)。
