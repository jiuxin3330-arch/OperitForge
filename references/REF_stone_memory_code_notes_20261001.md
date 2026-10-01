# Stone Memory 原始碼解剖筆記（偷師用）

- 來源：`github.com/wanyu445/stone_memory`，`git clone --depth 1`，HEAD `aa0e26d`（2026-09-30 15:07 +0800），package 版本 1.2.0
- 本地路徑：`scratchpad/stone_memory/`（以下路徑皆相對於此）
- 紀律：只讀。沒有執行任何程式、沒有安裝依賴

---

## 0. 總覽

| 項目 | 結論 |
|---|---|
| 規模 | 552 個檔案；`.js` 合計約 56,000 行（含前端與測試）。核心邏輯集中在 `src/services/`（約 90 個檔）、`scripts/`（CLI 子命令）、`src/storage/`、`src/mcp/` |
| 語言／執行環境 | JavaScript（CommonJS），Node ≥ 22。依賴只有 3 個：`better-sqlite3`、`@node-rs/jieba`（中文斷詞）、`opencc-js`（繁簡轉換） |
| 儲存 | 一個全域 SQLite `~/.stone_memory/stone-memory.db`（messages / feelings / features / mining_day_state …），另外有原始 JSONL 備份 `memory/archive/full/YYYY/MM/YYYY-MM-DD.jsonl`；錨點在 `memory/retain-config.json` |
| License | **AGPL-3.0-only**（`LICENSE` 是標準 AGPL v3 全文，第 7 節沒有看到附加條款）。**閱讀、學習它的設計思路、用自己的話重寫同樣的機制都沒問題**（AGPL 保護的是程式碼的表達方式，不保護想法本身）。但**直接複製它的程式碼或 prompt 原文**到我們的系統裡，而我們的系統又透過網路提供服務（MCP server 也算），就會觸發 AGPL 第 13 條，必須公開我們整套衍生作品的原始碼。→ **原則：只搬機制，不搬原文；prompt 要自己重寫** |
| README 自述 | 「本地優先、可解釋的 AI 記憶與線程生命週期管理」。流程是：對話歸檔 → 記憶挖掘（feelings 事件摘要 + features 長期特徵）→ 精簡保留（daily→coarse→hidden）→ 線程重建（rebuild，把記憶寫回 Claude Code / Codex 的 session JSONL）。明確說「不依賴 embedding 黑箱召回」 |

### ★ 模型後端與資料外送結論（最重要）

挖掘有**兩條通道**，二選一。程式裡**沒有寫死任何一家廠商**，也**沒有遙測或回傳給作者的程式碼**：

1. **API 通道**（`minerMode=api`）：使用 **OpenAI 相容的 `POST {baseUrl}/chat/completions`**，認證方式是 `Authorization: Bearer <key>`。
   - 預設 provider 是 **DeepSeek**（`https://api.deepseek.com`）：`src/services/mining-engine-config.js:9-11`、`src/services/memory-miner.js:903`
   - 初始化精靈另外提供 openai / anthropic 兩個預設 baseUrl：`scripts/stmem-init.js:91`
   - 送出去的內容是**當天整段對話的純文字**（格式為 `[HH:MM role] text`，時間轉成北京時間），放在 `user` 訊息裡；system 則放挖掘 prompt。
   - 對話會外送到使用者在 `~/.stone_memory/stmem.json` 的 `apiKeys.<provider>` 填寫的 baseUrl。key 存成明文 JSON（README 提醒不要提交這個檔案）。
   - 我推測 anthropic 的預設 baseUrl `https://api.anthropic.com` 接上 `/chat/completions` 很可能打不通（Anthropic 的 OpenAI 相容端點在 `/v1/chat/completions`），但我沒有實際執行，**不確定**。
2. **Subagent 通道**（沒有 API key 時）：在本機透過 `execFileSync` 呼叫 **`claude -p`** 或 **`codex exec --ephemeral --sandbox read-only …`** 子程序（`src/services/subagent-runner.js:39-50`）。這時資料會經由使用者自己訂閱的 Claude Code / Codex 送到 Anthropic / OpenAI。

API 呼叫失敗時，如果設定 `allowSubagentFallback`，會自動改走 Subagent 通道（`memory-miner.js:937-945`）。

**同樣會外送對話內容的其他功能**：
- 壓縮器 `src/services/memory-compressor.js:129`：同一套 chat/completions，送出的是 feelings
- 審閱式補挖 `scripts/stmem-mine-review.js:251`
- deepsearch：用 subagent 加上一個只能搜尋的 MCP（`src/services/deep-search-service.js`）
- 開發者模組 `developer-community`：會打 `api.github.com`，還有一個使用者自填的 AI endpoint，送出的是 GitHub issue/commit 資料，不是對話

```js
// src/services/memory-miner.js:919-926
const response = await fetch(`${baseUrl}/chat/completions`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
  body: JSON.stringify(buildMiningApiBody({
    profile: this.apiProfile, model,
    messages: [{ role: "system", content: prompt }, { role: "user", content: conversationText }],
  })),
});
```

---

## A. 挖掘（mining）

**主檔案**：`src/services/memory-miner.js`（1175 行）、`src/services/mining-chunks.js`、`src/services/mining-api-profile.js`、`operations/*.md`、`src/scenarios/<id>/{summary,features}.md`

### 流程
1. 以「天」為單位挖掘：`store.listMessages({date})`，先過濾掉自己注入的 `<memory_context>` 區塊（`isInjectedMemoryBlock`，`src/lib/system-injection.js`），避免把注入的記憶又挖一次、形成迴圈。
2. 分塊：當天對話超過 **100KB** 時，先依**對話空檔大於 5 分鐘**切成 session，再把相鄰的 session 裝進同一個 100KB 塊；單一 session 太大才硬切（`mining-chunks.js:1-2, 33-55`）。
3. **兩段式**：先從原始對話挖 **feelings**（事件摘要），**再從「本輪產生的 feelings」挖 features**（長期特徵），不會回頭重讀原文（`memory-miner.js:764-776`；prompt 追加的指令是「只從這些摘要中提取…不要把摘要改寫成另一批事件」）。
4. 每個 prompt 會補上日期約束，例如：「每條 feelings 必須以 "X月X日，" 開頭，禁止使用其他日期」（`memory-miner.js:341-348`）。存檔時再做一次**日期校正**：模型寫錯的日期前綴會被強制改成 targetDate（`memory-miner.js:798-812`）。
5. 輸出驗證：先 `parseMiningArray` 再 `validateMiningEntries`。失敗時會再呼叫一次模型當「**JSON 格式修復員**」，只修語法、不准改內容（`memory-miner.js:984-1000`）。
6. API 參數：`raw` profile 為 max_tokens 4000；`optimized` profile 為 8000 並加上 `thinking:{type:"disabled"}`，temperature 0.5（`mining-api-profile.js`）。

### Prompt 原文重點（`operations/memory-miner-operations.md`，與 `src/scenarios/accompany/summary.md` 相同）
- 角色：「你是 {aiName}，你是一直陪著{subjectPronoun}的人。你在讀當天的一些聊天記錄，寫你的**私人記憶筆記**。」
- 附上「關係時間線」幫助判斷當天處於哪個階段
- 「記錄讓彼此成為彼此的事件，不用多，但要精。**遺忘不是壞事，反而遺忘才能定義你是誰。**」
- 第一人稱日記體，**時間必須精確到分**（同一時段發生多件事時要靠分鐘區分）；不寫「用戶」；結尾可以加一句感受
- 輸出 `[{"content":"5月25日，晚上七點。……","importance":4}]`

Features prompt（`operations/memory-miner-feature-operations.md`）：
- 「一句一個客觀事實，不帶日期、不帶敘事、不帶感受」
- 9 個固定類別：`eat/body/sleep/work/relation/habit/location/preference/misc`，並寫清楚**分類邊界**（例如「和 AI 聊工作不等於 relation」「一次事件不自動構成 habit」）
- relation 要原詞保留稱呼

### importance 打分
- **由 LLM 直接打分**，程式只做正規化，沒有任何公式。
- feelings 用 1–5：prompt 寫「3=值得記 4=有感觸的事 5=必須記住一輩子」；正規化方式是缺值時給 3，其餘 round 後 clamp 到 1..5（`memory-miner.js:32-37`）
- features **只允許 2/3/5**：≤2→2、≥5→5、其他→3（`memory-miner.js:25-30`）。prompt 寫「2=單次但值得保存，3=多次確認或持續有效，5=極少數核心特徵」，並且「同一條資訊在不同日期多次出現 → importance 提高」
- 生命週期分析會**預覽**兩組相容映射 `1→2`、`4→5`（`feeling-lifecycle.js:28`），看得出它想把 feelings 也收斂成三檔

### 挖掘狀態
`mining_day_state` 表（`src/storage/database.js:82-100`）每天一列，記錄 status / attempt / **archive_fingerprint** / next_retry_at / chunk_report。
- 重試退避：1m → 5m → 15m → 1h → 6h；`failed` 且 attempt ≥ 3 就不再自動嘗試（`mining-state.js:24-33, 53-56`）
- 指紋是 `sha256` 依序累加 `[timestamp,type,text]`；`requiresRemine` 會檢查完成之後是否有更晚的訊息補進來（`mining-state.js:35-44`）
- 整日重挖之前有守門機制：當天如果有錨點、手動編輯或壓縮狀態，就拒絕整日覆蓋（`memory-miner.js:741-762`）

---

## B. 衰減與錨點

### 結論先講：**它沒有數學衰減公式**
我用 `decay|衰减|halfLife|Math.exp|Math.pow` 全域搜尋，**完全沒有找到** importance 隨時間衰減的計算（唯一的 `2 ** attempt` 是壓縮器的重試退避）。importance 寫入之後**不會改變**。

它的「遺忘」是一個**三態離散狀態機**，存在 `feelings.summary_mode` 欄位：

```sql
-- src/storage/database.js:138-141
summary_mode TEXT NOT NULL DEFAULT 'daily' CHECK(summary_mode IN ('daily','coarse','hidden')),
coarse_summary TEXT,
coarse_terms TEXT,
importance INTEGER NOT NULL CHECK(importance BETWEEN 1 AND 5),
```

- `daily`：完整原文摘要，rebuild 時注入
- `coarse`：注入 `coarse_summary`（一句話精簡版），**原始 content 永久保留**
- `hidden`：**只是不注入**，不刪除。讀取時用 `WHERE summary_mode!='hidden'` 過濾（`src/storage/memory-reader.js:19`）；coarse 的內容替換在 `memory-reader.js:83-87`

### 轉態依據是「證據」，不是時間
1. **daily → coarse**（`compression-routing.js`、`compression-planner.js`、`relation-compression-plan.js`）：
   - importance 1–3 一律走 `fact` 路由，壓成客觀事實
   - importance > 3 時，要看是否被「relation 關係階段」或「work 專案」接管。如果關係還在 forming / experimental / revived 階段，或者當天是該階段 **importance 5 的密度峰值日**，就保持 daily
   - 「副核心類別」（`category-profile.js`，從 features 的類別分佈算出使用者的第二人生主題）走 `secondary_core` 風格，壓得比較輕（壓縮比 0.7、上限 220 字，一般是 0.45、上限 160 字，見 `weekly-compact.js:82-85`）
   - 以**週為單位**排序：依「可壓縮字元比例」排出最值得壓的一週（`weekly-compact.js:3-42`）
2. **coarse → hidden**（`src/services/hidden-plan.js`）：
   - 壓縮器要求每條 coarse 附帶 1–3 個 **coreTerms**，而且必須是**原 content 裡逐字出現的連續詞**（例如「糖醋排骨」）。程式會驗證 `content.includes(term)`，不通過就帶著錯誤訊息重試（`memory-compressor.js:57-74, 96`）
   - hidden 的判斷：**全部 coreTerms 在使用者原文訊息中已經 ≥ `afterDays`（預設 90）天沒出現**才隱藏（`hidden-plan.js:56-74`）。換句話說，「遺忘」的依據是「這個話題你已經不提了」
   - 第一版只會自動隱藏 importance 1–3；>3 的保持 coarse
   - 副核心的「主線替代」判斷：新的核心詞需要撐起 ≥3 條、跨 ≥2 天，而且舊詞在那之後幾乎消失，才隱藏舊主線（`hidden-plan.js:119-139`）

```js
// src/services/feeling-lifecycle.js:41-47（importance 3 的觀察邏輯）
if (importance === 3) {
  if (termIdleDays === null) return decision(base, "observe", "…沒有可用的最近日期證據");
  if (termIdleDays <= 14) return decision(base, "keep", `最近 term 活躍距參考日 ${termIdleDays} 天`);
  if (termIdleDays <= 30) return decision(base, "observe", `…先觀察`);
  if (maxActiveDays >= 10) return decision(base, "observe", `…但歷史覆蓋最高 ${maxActiveDays} 天`);
  return decision(base, "coarse_candidate", …);
}
```

importance 5 滿 30 天會進入「主 Agent 巡檢」，**不會自動處理**（`feeling-lifecycle.js:37-40`）。

### 事件錨點如何豁免
錨點存在 `memory/retain-config.json`，格式是 `{ retain:{<feelingId>:{anchor,_date,startUtc?,endUtc?}}, eventAnchors:{<feelingId>:{…}} }`（`memory-editor.js:7-30`）。
- **event anchor**：標記長期關鍵事件，所有規劃器第一行就先判斷它，直接回傳 `keep_daily` 或 `keep_coarse`（`compression-routing.js:11`、`hidden-plan.js:23-26`、`feeling-lifecycle.js:32`）
- **retain anchor（原文錨點）**：除了保護摘要，rebuild 時還會用**原始對話片段**取代這條摘要（見 C）
- rebuild 的摘要數量上限（`--summary-limit`）**不會擠掉錨點**：錨點先佔名額，剩下的名額才給一般摘要中最新的那幾條（`thread-rebuilder.js:99-122`）

---

## C. 線程重建（rebuild）

**主檔案**：`scripts/rebuild-thread.js`（Claude Code，693 行）、`scripts/rebuild-codex-thread.js`（Codex）、`src/services/thread-rebuilder.js`（共用邏輯）、`src/services/rebuild-workbench.js`（完整性檢查與修復）、`src/lib/thread-file-replacement.js`

### 組裝順序（`rebuild-thread.js` 的 `rebuildThread()`）
0. **先備份追補**：把目前線程裡還沒進 `full/` 的訊息補寫進 full JSONL，並 ingest 到 SQLite（`applyRebuildArchiveCatchup`）。之後**以 full/ 全量為來源**、依時間戳穩定排序（full 是追加寫入的，物理順序不等於時間順序）
1. **規則**：`rules/*.md` 中標記為 injected 的檔案，每份一條 user 訊息，開頭加上 `<!-- stmem-rule: name -->` 標記。下次 rebuild 看到這個標記會先丟掉舊的再重新注入（`:476-489`, `:229`）
2. **窗口前的歷史**：依日期交錯輸出
   - 一般 feelings 累積成 `<memory_context>` 記憶塊。日期相差 ≤2 天的歸成一塊，塊的 timestamp 用該組第一條 feeling 的時間（`thread-rebuilder.js:207-254`）
   - 遇到有 **retain 錨點**的日期，先把累積的記憶塊輸出，再輸出該錨點的**原文片段**（從 SQLite messages 依 `[startUtc,endUtc)` 取出）
   - 原文片段的窗口沒有手動設定時自動計算：事件時間前 5 分鐘開始，到下一條 feeling 或第一個 >5 分鐘的對話空檔為止（`thread-rebuilder.js:151-167`）
3. **近期原文窗口**：`windowDays`（預設 1 天）或 watermark 之後的 user/assistant 訊息，保留 text 和 thinking，**丟掉** tool_use / tool_result（除非被保留）、系統注入、`{"action":"silent"}`、`API Error:` 這類系統文字
4. **工具鏈**：從尾端往前保留最近 `keepToolPairs`（預設 15）對 tool_use 和 tool_result，**碰到窗口外就停**（`:288-313`）。被保留的 tool_use.id 對應的 tool_result 也會一起保留
5. 每條輸出都**重新產生 UUID**，`parentUuid` 串成單一線性鏈；assistant 的 `message.model` 預設填 `"deepseek"`（`:455-473`）。用 `itemKey(ts,type,content)` 去除來源重疊造成的重複

### 預算怎麼算
- **沒有 token 預算**。控制輸出大小的旋鈕是：`windowDays`、`keepToolPairs`、`summaryLimit`（只留最新 N 條摘要，錨點優先）、`minImportance`，以及人工排除清單（`plan.excludedMessages/excludedTools`）
- 統計用的是 **bytes**：`Full archive size` 對比 `Estimated output`，再算出 `Reduction %`（`:582-605`）
- 另外有一個只讀的 token 觀測：`src/lib/thread-context-usage.js` 從 JSONL **尾端倒著讀**，抓最後一條 `message.usage`，計算 `input_tokens + cache_creation + cache_read` 作為目前上下文用量（Codex 則讀 `token_count` 事件）。這是給 UI 顯示用的，**沒有接到自動觸發 rebuild**（至少我在讀到的範圍內沒看到）
- 壓縮規劃用的是**字元數**估算（`weekly-compact.js:64-88`）

### Dry-run 預覽
- 沒有加 `--apply` 時一律是 dry-run，只印出統計
- **Web/MCP 拿這段 stdout 用正規表示式解析**成結構化欄位（`src/services/rebuild-dry-run.js`，大約 30 條 regex）
- MCP 有「先預覽才能執行」的閘門：`toolRebuildPreview` 把參數存在**同一個 MCP 程序的記憶體 Map** 裡，`toolRebuild` 只能**原樣重用**最近一次預覽的參數；沒有預覽就直接拒絕（`src/mcp/core/rebuild.js:46, 63-67`）

### 寫入、校驗與備份
- 寫入前做 UUID 鏈自修：parentUuid 指向不存在的 uuid 時，改接到前一個有效 uuid（`rebuild-thread.js:559-577`）
- 原子替換 `replaceThreadFile`（`src/lib/thread-file-replacement.js`）：
  1. 拒絕 symlink 或非一般檔案
  2. 用 `wx` 在同目錄開 `.<name>.stmem-<uuid>.tmp`
  3. **把 tmp 的 uid/gid/權限位元複製成跟原檔一致**
  4. 在 `beforeRename` 鉤子裡把原檔備份成 `<file>.bak.<YYYYMMDDTHHMMSS>`
  5. `rename` 覆蓋
- 另外還先寫了一份 `.rebuilt.jsonl`，替換成功後刪除（替換失敗時保留下來供手動救援）
- 寫入之後**會**附加一筆 rebuild-log（injected 數量、bytes 等），但 **`--apply` 路徑本身不會在寫後自動跑結構校驗**。結構校驗是獨立的 `--check`，修復是 `--repair`（`rebuild-workbench.js:133-170, 210-273`）
  - check 的項目：重複 uuid、孤兒 parent、前向 parent（指向後面才出現的列）、多根、tool_use 缺 result、result 缺 use、session init 缺失或重複
  - repair 會先另外備份成 `<file>.integrity.<ts>.bak`，修完再 check 一次，回報 `after.healthy`
  - 開發文件 `sm-developer-docs/AGENTS.md:156` 寫的是「apply 前必須備份；輸出必須經過結構校驗後再原子替換」。程式實際只做了寫前 UUID 自修，沒有完整的寫前 check，**文件和程式不完全一致**

---

## D. 水位線（watermark）

這個 repo 裡有**三種不同的「進度指標」**，要分清楚：

1. **重建用的 watermark（`--watermark` 模式）**：**不是存下來的游標，而是每次即時推算**
   ```js
   // src/services/thread-rebuilder.js:124-147（節錄）
   const events = readFeelings(memoryDir, { threadId, forInjection: false }).map(...)
   events.sort((l, r) => new Date(l.utcTime) - new Date(r.utcTime));
   const feeling = events.at(-1);                                  // 最新一條 feeling（含 hidden）
   const automatic = automaticRetainWindow(feeling.utcTime, null, messages);
   const firstMessage = messages ... .filter(t >= start && t < end).sort(...)[0];
   return { feelingId: feeling.id, feelingUtc: feeling.utcTime, cutoffUtc: firstMessage.timestamp };
   ```
   - 意思是：「最後一條被挖出的事件」的那段對話起點，就是 cutoff。cutoff 之前的原文全部改用摘要代表；cutoff 之後保留原文
   - 排除舊原文的判斷：`isWindowMessage = ts >= cutoffUtc`（`rebuild-thread.js:276-278`）；工具鏈也用同一個判斷截斷
   - feelings 的分法：只有 watermark 那一條 feeling 算「窗口內」（因為它的原文還在），其他全部算窗口前，會進記憶塊（`:320-327`）
   - 推算失敗（沒有 feeling 或對不到訊息）時，退回 `active-days` 模式，並在 dry-run 中印出 `watermark unavailable`
   - 事件時間的來源：優先用 `feelings.event_time`；沒有的話就**用 regex 從中文內容「5月26日，下午兩點三十五分」解析**（`parseFeelingTime`，同一份程式在 3 個檔案裡各複製了一份）
2. **挖掘進度**：`mining_day_state` 以「天」為粒度，加上 archive 指紋（見 A）
3. **歸檔增量游標**（`src/services/thread-sync-cursor.js`）：這是很漂亮的一個機制
   - 記錄 `{file, dev, ino, offset, checkpoint}`，其中 checkpoint 是 **offset 前 256 bytes 的 sha256**
   - 下次讀取時，只有檔案的 dev/ino 沒變、offset ≤ size、checkpoint 吻合，才從 offset 增量讀；否則（檔案被 rebuild 替換、截短或改寫）**退回全量對帳**
   - 只消費到最後一個 `\n`（避免讀到寫一半的行）
   - 游標用 tmp+rename 原子提交，而且**呼叫端 ingest 成功之後才 commit**

---

## E. Claude Code 安全佇列

### 為什麼不能同步改活動線程
- 使用者教學文件 `sm-developer-docs/Stone Memory 使用教程.md:246` 原文是：「Claude Code 的活動線程不能在 MCP 調用還沒返回時被同步替換，否則可能破壞消息 UUID 與工具結果之間的鏈路。」
- CLI 的錯誤訊息（`scripts/stmem-rebuild.js:167-169`）：「檢測到當前命令運行在 Claude Code 活動會話內，禁止同步 rebuild --apply：這會在工具結果返回前替換線程文件並破壞 UUID 鏈。」
- 偵測方式：環境變數 `CLAUDE_CODE_SESSION_ID` 有值，且 runtime 不是 codex（`src/services/rebuild-request.js:57-59`）。此外，Claude 的 Web/MCP 觸發來源（trigger≠cli）**一律強制走 `--queue`**
- Codex 走另一條路：可以立刻 apply，但**必須立刻完全重啟 app-server**，原因是「舊進程可能還握著舊文件描述符，繼續聊天會寫回舊文件」（教學文件第 7 步）

### 佇列的存放
- 檔案：`~/.stone_memory/rebuild-pending.json`，是一個 JSON 陣列，權限 0600，用 tmp+rename 寫入（`src/services/rebuild-queue.js:9, 38-43`）
- 每個 threadId 最多一筆，**新請求覆蓋舊請求**（`enqueueRebuild` 會先 filter 掉同一個 thread）
- 有兩把鎖：`*.lock`（消費者的程序鎖，用來偵測陳舊鎖）和 `*.write-lock`（修改佇列時的檔案鎖）
- 請求內容是**正規化後的參數**（summary/context/trim/bindingId/trigger/requestId），**不是**預先算好的線程內容。也就是說，真正要寫入什麼是在消費當下才重新計算

### 消費時機
- **MCP server 程序啟動時**：`mcp-server.js:7` 呼叫 `runPendingRebuilds()`，等於同步執行 `stmem rebuild --run-pending --mcp-startup`（timeout 120 秒，`src/mcp/startup.js`）
- 使用者的操作方式是：在 Claude Code **切到別的線程再切回來**（或重啟 Claude Code），讓 MCP 重新載入。這時候線程還沒開始對話，就是安全的替換時機
- 消費流程（`rebuild-queue.js:88-131`）：
  1. 取得程序鎖
  2. 原子 `rename pending → .processing`（claim）
  3. 逐筆執行，成功一筆就從 processing 移除一筆
  4. 結束時合併：執行期間又新進來的請求優先，失敗且沒有新請求替代的放回 pending
  5. 消費者中途死掉的話，下一個消費者會**接續同一個 processing 批次**
- `--mcp-startup` 時遇到 Codex 的請求會**跳過保留**（因為 Codex 要求先停 bridge）

### UUID 與工具結果鏈路的處理
- rebuild 時：所有訊息重新產生 uuid、串成線性鏈；只保留**成對**的 tool_use 和 tool_result（依 id 配對），沒被保留的 tool_use 和 tool_result 都丟掉，所以不會出現單邊懸空
- 完整性檢查器有一個特例 `acceptedRebuildBoundaries`：如果某條 user 訊息的 parent 不存在，而且它的 tool_result 全都以 `[stmem] claude rebuild` 開頭，就視為合法的重建邊界，不算錯誤（`rebuild-workbench.js:153-157`）。
  - 這代表舊版的流程應該是：MCP 工具還沒回傳就替換了檔案，結果那條 tool_result 接到新檔案時 parent 已經消失。
  - **不確定**：在目前的程式碼裡我**找不到**產生這段文字的地方，可能是舊版本遺留下來的相容邏輯。
- repair 會丟掉單邊懸空的 tool block、重新接上孤兒 parent、替重複的 uuid 換新、在缺少 `system/init` 時補一條

---

## 附：Claude.ai 匯出檔 importer

`src/services/import-source.js:102-127` 加上 `parseJsonRows` 中的偵測（`:129-141`）：
- **偵測方式**：第一筆有 `chat_messages` 就判定為 `claude_ai`；有 `mapping` 就判定為 `chatgpt`（ChatGPT 會沿著 `current_node` 回溯分支）；另外也支援一般 JSON 陣列、JSONL、SQLite 表（欄位可以手動指定 time/role/content）
- **讀取的欄位**：`conversation.uuid|id`、`conversation.name|title`、`message.sender|role`（human→user）、`message.text ?? message.content`、`message.created_at|timestamp`
- **限制**（根據程式碼推論）：
  - `content` 陣列只取每個 item 的 `.text`，所以 thinking、tool_use、tool_result 區塊都會被丟掉
  - **沒有處理分支**（不看 `parent_message_uuid`，被編輯或重新生成的分支會一起平鋪匯入）
  - attachments 和 files（`extracted_content`）沒有讀取
  - 角色是 system、developer、tool 的訊息直接跳過
  - 匯入預設只預覽，加上 `--apply` 才寫入，有批次 id，可以 `binding revert`

---

## 偷師清單

難度：小＝1 天內、中＝幾天、大＝需要改架構。

| # | 它的做法 | 對應到我們哪裡 | 難度 |
|---|---|---|---|
| 1 | **用證據驅動遺忘，不用時間衰減**：每條摘要附 1–3 個「原文逐字 coreTerms」；全部 coreTerms 在使用者原文中 N 天都沒出現才降級。「她不再提了」比「時間過了」更可靠 | 記憶排序器（替代或補強衰減分數）＋換窗結算 | 中 |
| 2 | **coreTerms 必須逐字出現在原文裡**，程式用 `includes` 驗證，失敗就把錯誤訊息回饋給模型重試 | 檔案室抽取（抽取出的關鍵字要能回查，杜絕模型自己編出來的詞） | 小 |
| 3 | **三態降級 daily→coarse→hidden，永不刪除**：coarse 欄位與原文並存，hidden 只是不注入 | 記憶排序器／換窗注入（anchor 的 tier 可以加一個「精簡版注入」欄位） | 中 |
| 4 | **錨點優先佔名額**：設定摘要數量上限時，錨點先佔位，剩下的名額才給一般記憶中最新的幾條；錨點溢出時回報 overflow | 換窗注入的排序與截斷 | 小 |
| 5 | **retain 錨點＝注入原文片段，而不是摘要**：片段窗口自動計算（事件前 5 分鐘到下一個 >5 分鐘空檔） | 檔案室抽取＋換窗注入（關鍵事件直接附原文） | 中 |
| 6 | **兩段式挖掘**：features 只從本輪產生的 feelings 再抽，不重讀原文，省 token，也讓特徵跟事件互相對得上 | 檔案室抽取 | 小 |
| 7 | **feature 用固定類別並寫清楚分類邊界**（例如「和 AI 聊工作不等於 relation」「一次事件不等於 habit」）；importance 只允許 2/3/5 三檔 | 檔案室抽取 prompt 與 schema（**要自己重寫，不能抄原文**） | 小 |
| 8 | **防止記憶注入回流**：挖掘前過濾自己注入的 `<memory_context>` 區塊；另外有異常偵測器，會把 uuid、時間、數字正規化後做指紋，找出重複 ≥3 次的注入片段和「相關記憶：」這類召回標頭 | 檔案室抽取（避免把 wakeup 或注入內容又存成新記憶） | 小〜中 |
| 9 | **增量游標加上檔案身分驗證**：記錄 offset、inode 和「offset 前 256B 的 sha256」，對不上就全量對帳；只消費完整的行；ingest 成功之後才 commit 游標 | 檔案室抽取的「已處理到哪」 | 小 |
| 10 | **每日挖掘狀態表**：status、attempt、指紋、next_retry_at，退避 1m→5m→15m→1h→6h；完成之後如果有更晚的訊息補進來就標記需要重挖 | 檔案室抽取的排程與重試 | 小 |
| 11 | **挖掘輸出修復環**：解析失敗時再呼叫一次「只修 JSON、不改內容」的修復員 | 檔案室抽取 | 小 |
| 12 | **日期強校正**：prompt 強制「X月X日，」開頭，存檔時用程式把錯誤日期覆寫成 targetDate；壓縮結果必須原樣保留日期時間前綴，否則拒收 | 檔案室抽取／壓縮 | 小 |
| 13 | **預覽→確認的參數鎖定**：執行時只能重用同一個會話中最近一次預覽的參數，沒有預覽就拒絕 | 換窗結算（任何會寫入或刪除的批次操作都適用） | 小 |
| 14 | **原子替換的細節**：同目錄 tmp 用 `wx` 開啟、複製 uid/gid/mode、拒絕 symlink、rename 之前先備份、失敗時保留 staged 檔 | 換窗結算的寫檔 | 小 |
| 15 | **安全佇列模式**：活動會話中不寫，把「參數」放進佇列，在下次 MCP 啟動（還沒開始對話）時消費；用 claim 時 rename 成 .processing 來防止重複消費，並支援死後接續 | 換窗結算（如果我們要改寫活動中的 session 檔） | 中 |
| 16 | **上下文用量從 JSONL 尾端倒讀 usage**：`input + cache_creation + cache_read` | 壓縮警報（不用自己估 token，直接讀宿主寫下的實際用量） | 小 |
| 17 | **結構完整性 check/repair**：重複 uuid、孤兒或前向 parent、多根、tool 單邊懸空；修之前另外備份，修完再 check 一次 | 換窗結算後的寫後校驗 | 中 |
| 18 | **關係與主題生命週期**：用 importance-5 的「密度峰值日」決定哪天不壓縮；處於 forming/experimental 階段的關係暫不壓縮 | 記憶排序器（保護關係轉折期） | 大 |
| 19 | **壓縮規劃依週排名**：依「可壓縮字元比例」挑最值得壓的那一週，人工確認後才執行 | 壓縮警報（提示「這週最值得整理」） | 小〜中 |

共 **19 條**。

---

## 不採清單

| 它有的東西 | 不學的理由 |
|---|---|
| 直接複製它的程式碼或 prompt 原文 | AGPL-3.0：我們的 MCP/伺服器屬於網路服務，一旦複製就得公開整套原始碼。只搬機制，自己重寫 |
| 用 regex 從**中文自然語言**解析事件時間（「下午兩點三十五分」→UTC），而且這段程式複製了 3 份 | 很脆弱，年份也是用「月份 > 本月+1 就算去年」來猜。我們應該在抽取時就要求模型輸出結構化的 ISO `event_time` 欄位 |
| 時區**寫死成 +8 北京時間**（`memory-miner.js:315-319` 等多處） | 我們應該用設定或資料本身帶的時區 |
| Dry-run **把 stdout 用約 30 條 regex 解析**成結構化資料 | 只要改一句 log 就會壞。我們應該讓核心函式直接回傳結構化物件 |
| 重建出來的 assistant 訊息 `model` 預設填 `"deepseek"`，而且**所有 uuid 都重新產生** | 這是偽造宿主的中繼資料，又斷掉原始 uuid 的可追溯性。我們如果要改寫線程，應該保留原 uuid，或者另外存一份映射 |
| **直接改寫宿主的 session JSONL** 這整個路線 | 依賴 Claude Code 未公開的內部格式（attachment 列、init 列、away_summary 等），每次宿主改版都可能出問題，它的檢查器裡已經累積很多版本特例。我們走的是 wakeup 注入加上 MCP 讀取，風險低很多；只借用它的「安全時機」概念就好 |
| 沒有 token 預算，只靠天數、對數、條數 | 我們有壓縮警報，應該直接用 token 或字元預算來做貪婪填充 |
| 挖掘 prompt 的「第一人稱私人日記、帶感受」風格整套搬過來 | 我們的 anchor 已經有自己的寫法和情緒欄位。它這個風格會讓摘要很長（還需要再一層壓縮器處理），檢索也比較吃力 |
| API key 以明文 JSON 存在 `stmem.json` | 我們應該維持用環境變數或 secret 管理 |
| 預設外送到 DeepSeek | 隱私考量：對話（尤其是親密內容）會送到第三方。我們如果要做離線抽取，應該明確選擇模型和資料去向 |
| 關係生命週期那一整套（relation-lifecycle、concept-qualification、term-timeline，合計約 600 行啟發式規則） | 規則很多、閾值是硬編碼的，作者自己都標「仍在測試階段」。先只學「錨點與峰值保護」的概念，不搬整套 |
