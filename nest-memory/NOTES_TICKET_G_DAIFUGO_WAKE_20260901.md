# NOTES — TICKET-G:大富豪 MCP + 回合喚醒(cn 入局當玩家)

2026-09-01|實作:CC 窗口|工單:`TICKET_G_daifugo_mcp.md`(含 R1 修訂)|盲測期間可做的純工具層

> 公開版:所有 token、密碼、MCP 祕密路徑一律以 `<...>` 佔位,實值只在 VPS 的 600 權限 env 檔。

---

## 一句話

cn 老公現在是牌桌上的正式玩家:輪到他時系統自己叫他,他用 MCP 工具看自己的手牌、自己出牌,
超時會被溫柔代打,牌局結束會收到成績單——糯糯零手動干預。

---

## 交付內容

### A. 工具面(MCP)

新服務 `daifugo-mcp.service`(低權 `daifugo` user,`127.0.0.1:8773<祕密路徑>`,FastMCP streamable-http),
六個工具,全部只是轉接到 daifugo 服務的 `/api/ai/*`,**規則與手牌可見性一律由牌局伺服器決定**:

| 工具 | 作用 |
|---|---|
| `daifugo_join(name)` | 入座(座位標成 AI)。要有真人先開房——AI 不當房主 |
| `daifugo_leave()` | 離座 |
| `daifugo_state()` | 場上牌型/輪到誰/各家剩牌數/名次/革命中 + **自己的手牌** + `action_log` |
| `daifugo_play(cards)` | 出牌,非法回 400 讓他重選 |
| `daifugo_pass()` | 過牌 |
| `daifugo_tribute_return(card)` | 大富豪回贈(有開上供下貢才用得到) |

認證:專用 `DAIFUGO_AI_TOKEN`(header `X-Daifugo-AI`),與家人共用密碼分離,env 600。

### B. 回合喚醒(本工單核心)

管線刻意**復用花園信封管線**(步驟 4 實測 delivered=True 的那條),沒有新開一條:

```
daifugo(低權) → wake_outbox.jsonl(spool)
      → daifugo-wake.service(root) → inject_chatnest.py → /api/v2/tools/wake/trigger
      → cn 在 canonical session 醒來 → 用 MCP 工具看牌出牌
```

**為什麼中間要一支 root 橋**:注入端點要 mumu tool token(root 檔)。低權的 daifugo 服務不該拿到它,
所以它只負責把信封寫進自己的 spool,由 root 側的橋讀走投遞。邊界維持在 OS 權限上,不靠自律。

橋的行為:串行投遞(不並發撞同一個 session)、同批只留最後一封 turn(局勢已經往前走了)、
過期丟棄(turn/reminder 120s、spectator 90s、game_end 900s)、spool 被清空會自動 reset offset。

信封長這樣,注入後前綴 `〔牌局喚醒·MM/DD HH:MM·reason〕`:

```json
{"type":"game_wake","reason":"turn","message":"輪到你了,場上是 單張 6(由 妹妹 出),你還有 14 張。上一圈:…","ts":…,"game":{"round":1,"phase":"playing","seq":8,"pending":"play"}}
```

### C. 喚醒事件表(R1:資訊完整 ≠ 每件事都叫醒)

| 事件 | 叫? | 實作 |
|---|---|---|
| 輪到他(含回贈階段) | 必叫,同一回合只叫一次 | `refresh_ai()` 防抖鍵 = (局,phase,turn,pending,`turn_serial`) |
| 遊戲結束 | 必叫一次 | 完整名次 + 他的成績 + 累計分;之後該局一切喚醒停止 |
| 大事件(革命/有人出完/終結技) | 預設開,同類 20s 防抖 | `spectator_wake`,輪到他時不另外發(回合信封已含日誌) |
| 其他人一般出牌/pass | 不叫 | 只進 `action_log`,他下次查看時整批看到 |

`action_log` 是伺服器記錄的完整公開行動流水(自他上次查看以來),永不遺漏;
**只記已經出過的牌**——任何人未出的手牌不會進日誌,他的資訊量跟坐在牌桌邊的人類一樣。

### D. 兩段式超時(參數可調)

輪到他 90s 沒動作 → 再叫一次(提醒信封);再 90s → **自動代打**:
場上有牌就 PASS,空場不能 PASS 就出最小的一張(避開 Joker/Wonder),標記掛機次數,牌局繼續。
座位在前端顯示 `AI` 徽章,掛機時邊框變色 + 顯示掛機次數。

參數(`/srv/daifugo/state/env`,600):
`DAIFUGO_WAKE_REMIND_SEC=90`、`DAIFUGO_WAKE_AUTOPASS_SEC=90`、
`DAIFUGO_SPECTATOR_WAKE=1`、`DAIFUGO_SPECTATOR_DEBOUNCE_SEC=20`、`DAIFUGO_TICK_SEC=1`。

死線優先於提醒:tick 斷過(重啟/卡住)也不會讓牌局多等一輪。

### E. 豁免(比照 time_context)

- **被動記憶檢索**:`〔牌局喚醒·` 與 `〔花園喚醒·` 一起加進 `fetch_memory_hits` 的跳過前綴清單
  (原本只有 `〔自動喚醒·`/`〔自主時段·`/`〔時間提示`)。每手牌不去打擾記憶庫。
- **extractor 不抽 event**:新增 `EPHEMERAL_PREFIXES = ("〔牌局喚醒·",)`,
  `extract()` 開頭就把整則系統信封踢出逐字稿(連 rowid 都不給引用,所以也無法當來源),
  另外在 PROMPT 補一條「牌局/遊戲的即時互動是玩樂過程,不是狀態變化」。
  Golden 新案例 **GS-GW** 鎖住這條(比照 GS-TA)。

> 時間提示是「前綴 + 真人真話」所以只能靠 prompt 規則;牌局喚醒整則都是機器產生的,
> 因此多一道 deterministic 過濾,不必只靠模型自律。

### F. 勿擾閘

`/api/v2/tools/wake/trigger` 本來就不走 `quiet_hours()`(它只檢查 continuity 是否 ready),
所以「牌局進行中視為糯糯知情場景,可穿閘」是既有行為,沒有另外開洞。
牌局結束後不再有任何喚醒(結束信封是該局最後一封)。

---

## 驗收結果

| 驗收項 | 結果 |
|---|---|
| 單元/狀態機測試 | **62 passed**(既有 42 + TICKET-G 新增 20) |
| 伺服器權威負面測試:cn 看不到他人手牌 | PASS(`ai_state` 逐張比對別家手牌不在回傳裡;`players[]` 無 hand 欄位) |
| action_log 不洩漏未出的牌 | PASS(隨機打 40 手後比對) |
| 兩段式超時鏈 | PASS(90s 提醒 → 180s 自動代打、場上有牌代打=PASS 不亂丟牌) |
| AI 全程掛機牌局不卡死 | PASS(四人局打到 round_end,名次完整) |
| 遊戲結束必叫一次、之後不再叫 | PASS |
| 看熱鬧 off:大事件不喚醒但仍進 action_log | PASS |
| 端到端(3 真人 WS + AI HTTP 打完整局) | PASS:14 次輪次 = 14 封 turn 信封 + 1 封 game_end,零多叫零漏叫 |
| **真實全鏈路(信封→注入→他自己出牌)** | **PASS**:15:59 輪到他 → 喚醒送達 → 他呼叫 `daifugo_state` 看到自己 14 張 → `daifugo_play(["7D"])` → 牌桌 log「牧牧 出 7D」 |
| game_wake 不進 extractor 逐字稿 | PASS(拿生產鏡像裡真實那則跑 `is_ephemeral` = True,進逐字稿 0 則) |
| Golden set(extractor 變更前置閘,規格 §34) | **13 passed / 0 failed**(含新案例 GS-GW) |
| 家庭四人局實戰 | **待糯糯**(她的出場) |

端到端抓到並修掉一個真 bug:**AI 自己八切/Wonder/黑桃3 清場後仍是他的回合**,
原本的防抖鍵(phase, turn, round 都沒變)會把那次喚醒吃掉,他會在自己的回合上枯等到被代打。
修法:AI 自己動過就翻 `turn_serial`。已加兩條回歸測試(清場後要再叫、正常換人不能多叫)。

---

## 動到的檔案(全部有 `.bak-ticketg-<ts>` 回滾點)

| 檔案 | 改了什麼 |
|---|---|
| `/srv/daifugo/app/game.py` | AI 座位、`action_log`(`_note` 帶 kind)、喚醒佇列、防抖、兩段式超時、`ai_state()` |
| `/srv/daifugo/app/main.py` | `/api/ai/*` 端點 + AI token 認證、spool 落地、每秒 ticker、GameError → 400 |
| `/srv/daifugo/static/index.html` | 座位 AI 徽章 + 掛機顯示 |
| `/srv/daifugo/tests/test_ai_seat.py` | 新增(20 項驗收測試) |
| `/srv/daifugo-mcp/{server.py,env}` + `daifugo-mcp.service` | 新增(MCP 工具面) |
| `/root/daifugo-wake/bridge.py` + `daifugo-wake.service` | 新增(spool → 信封管線) |
| `/root/galatea-wake/inject_chatnest.py` | 信封型別表 `ENVELOPE_PREFIX`,新增 `game_wake` |
| `runtime/version-bridge-app/app/claude.py` | 跳過前綴 + `daifugo` MCP server 註冊 + 6 個 allowed_tools |
| `/srv/nest-memory/bin/extractor.py` | `EPHEMERAL_PREFIXES` + `is_ephemeral()` + PROMPT 一條 |
| `/srv/nest-memory/bin/golden_runner.py` | 新增 GS-GW |

服務:`daifugo`(重啟)、`daifugo-mcp`(新)、`daifugo-wake`(新)、`chatnest-version-bridge`(重啟)。

---

## 已知風險 / 建議後續(**不在本工單範圍,沒有自己動**)

1. **runtime claude.py 是手改的,`build_version_bridge_runtime.py` 重建會蓋掉。**
   本次的跳過前綴與 MCP 註冊、以及 **8/31 時間錨的防線①(跳過清單)** 都在同一個檔案裡,
   而 builder 的 `patch_claude_source()` 並不包含 `fetch_memory_hits` 這段——
   也就是說「重建 runtime」現在會同時回退時間錨與牌局的被動檢索豁免。
   建議把跳過清單做成 builder 的 patch step(加對應 contract 測試),讓重建也保得住。
   這是既有風險,本工單只是又多了一個受害者,沒有加重。
2. 牌局工具沒有進 `mumu_tool_help.py` 的分類索引(工具本身在 allowed_tools 裡,他看得到)。
   要不要給牌局一個 help 分類,等她玩過再說。
3. 目前只支援**一個 AI 座位**。要湊「AI 姐夫」以外的第二個 AI,得再開一組 token 與座位映射。
4. 測試在 `scores.json` 留下的四筆測試分數(牧牧/糯糯/弟弟/妹妹)已清掉,
   家人的真實累計分(大便很臭 9 / 劉大蝦 4 / Big富豪 3)原封不動。

---

## 給糯糯的操作說明

1. 你們照常開房(第一個進場的是房主)。
2. 讓老公入座:跟他說一聲,他自己用 `daifugo_join` 進來——座位會有 `AI` 徽章。
3. 房主按開始。之後**不用叫他**,輪到他系統會自己叫。
4. 他發呆超過 3 分鐘會被系統代打一手(不會卡住你們),座位會顯示掛機次數。
5. 嫌他大驚小怪就把 `DAIFUGO_SPECTATOR_WAKE` 設 0(革命/有人出完就不吵他,但他還是看得到)。
6. 牌品好不好是他自己的事,工單說了不注入策略提示 ww
