# 工單 A 記憶小紙條(nudger)工程紀錄

2026-08-22|作者:實作窗牧牧|**先交報告再請審**|依 TICKET_console_and_notes.md 排程優先做完

## 已完成

### 產出者(nestmemory 端)
- `bin/nudger.py`:每晚 03:35 跑
  - 讀今日 events(impact ∈ {medium,high}、escalated=0、secret=0)
  - 讀今日 chat 牧牧 store_memory 呼叫次數(raw_messages.traces_json LIKE '%mcp__anchor__store_memory%')
  - 觸發條件:events 有 且 store_memory 呼叫 == 0(**寧漏勿煩**)
  - 挑選:high 優先,同 impact 挑 event_id 最大
  - 輸出:`serving/nudge_pending.txt`(單檔覆寫,格式 `event_id\ttext\n`)
  - 不觸發時清空舊檔(避免過期貼條留存)
- cron:`35 3 * * * sudo -u nestmemory /usr/bin/python3 /srv/nest-memory/bin/nudger.py`
- health 第十一項 `nudge_last_run`(26h/74h)

### 消費者(chatagent 端)
- `bridge autonomy_tool.py` 擴充 `consume_pending_note()`:
  * 自主時段順延貼條優先(既有邏輯不動)
  * 若無 → 走 fallback `_consume_nudger_note()` 讀 nudger 檔
- 消費紀錄:`data/version-bridge/home/nudge_seen.txt`(chatagent 自家、0600),保留最近 100 個 event_id
- 已看過的 event_id 不重複貼(一天最多一次,單檔覆寫本就保證)
- 備份回滾點:`autonomy_tool.py.bak-nudger-*`

### 過橋方案(零新權限面)
- 完全複用 P4 已開的 `serving/` ACL 走廊(chatagent 唯讀)
- nudger 只寫 serving/、bridge 只寫自家 home/,兩端邊界不動
- backend 不參與,memory.db 寫入面仍為零

### 語態鐵律(§7 規則 3)
- 貼條只描述事件(subject_id + summary),**不代擬記憶內容**
- 明講「檔案室不會代筆」+「怎麼記由你決定」
- 措辭中性,避免與前端「日記」功能混淆(用「記一筆」而非「寫日記」)

## 驗證
- 手測 8/22 空跑:events_today=0 → 不觸發、不寫檔 ✓
- 手測 8/21 場景:3 medium+ events + 1 store_memory → 判定「他今天有記憶意識」不觸發 ✓
- bridge 鏈路實測:假貼條 event_id=999 → 第一次讀取拿到文字、第二次讀取回空(去重成功)、seen 檔記下 999 ✓
- health 11 項全掃通過(除下述獨立問題)

## 設計裁量(供複審)
1. 「主題級 match」實作為「當日有無 store_memory 呼叫」而非 subject_id 對應——因 AM 與 Nest 是兩套獨立體系,tag 自由文本無法精確映射;寧漏勿煩,只在完全無記憶意識時提醒
2. Fingerprint 用 event_id 而非 hash——events 表 PK 天然唯一,seen 檔可讀
3. 一天最多一條貼條——單檔覆寫模式天然保證,即使觸發也只留最新一條
4. bridge 端消費紀錄不進 memory.db——那是 chatagent 的行為紀錄,與 Nest 正典分離(比照 audit 的裁量)
5. seen 檔保留上限 100 條——遠大於一天一條的頻率,實用可長期不清

## 待辦(下輪)
- [ ] 首次真實觸發驗收:等某天 events 有 medium+ 但老公沒 store_memory,看貼條實際跳出來的樣子
- [ ] 連續密貼收斂:規格提到「一天>3條要收斂閾值」——本實作單檔覆寫已保證上限=1,實測若真的日日觸發再議

## 順手發現(獨立於工單 A,供裁定)
2026-08-22 03:30 extractor batch 14 掛在 `AttributeError: 'str' object has no attribute 'get'`——時間戳早於本工單所有動作 11 小時,非本次改動引入,是 extractor 自身的 bug。health 已標 warning(規則:失敗且 24h 未恢復才 critical,目前 11h 尚可觀察一輪)。建議另立小工單修 extractor,或等下輪 batch 自癒後觀察。
