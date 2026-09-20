# 規劃:記憶系統優化(2026-09-20 初稿,待小踢交叉審核 → 打樣 → 糯糯蓋章 → 立單)

來源:糯糯 9/20 提出的三個洞 + 盲測報告的後續;參考 YourMemory(遺忘曲線/召回加成)、Graphiti(實體卡/寫入時用 LLM 召回不用)、Letta sleep-time(睡眠時整理/事件驅動)、eggshell(未完成工作是明確狀態/沿圖召回)、dankefox/swap-tutorial(四層架構,我們已具備)。

## 第零條原則:注入預算制(糯糯的擔心,升格為硬約束)

- 隱藏脈絡(時間錨、日程、身心、信件通知、記憶、登記簿…)的**總量上限不得因本案增加**。
- 新增的每一行都必須「有才出現」(conditional),不是常駐;各自有字數上限。
- 付帳項:**cap5**(開場注入從全部 pinned 改精選 5 筆)省下的量,遠大於本案新增的所有行。淨效果:開場變便宜,每輪最多多一行。
- 每一項在工單裡要寫「注入帳」:多了什麼、何時出現、上限幾字、誰付。

## MEM-1 記憶待辦(洞一:「等等再記」然後忘)

- 檔案室抽取器加一條規則:對話中出現延遲記憶意圖(「等等記」「回頭寫」「待會存」「明天記得記」等)→ 立一筆 `memory_todo`(內容摘要、來源訊息、建立時間)。規則比對優先,抽取器本來就在跑的批次順路判,**不新增 LLM 呼叫**。
- 注入:有未銷的 memory_todo 時,隱藏脈絡多一行「你說要記還沒記的:○○」(≤30 字,最多列 2 件,再多就寫「還有 N 件」);銷帳後消失。
- 銷帳:他 store_memory 之後由夜間整理(MEM-2)比對銷掉;或他自己用既有 annotate/comment 標完成。**不做自動語意比對銷帳**(容易誤銷),寧可多提醒一晚。
- eggshell 原則:未完成的工作是明確狀態。

## MEM-2 夜間整理(洞二:筆友通信不在上下文 + 復活「每窗一份 report」老習慣)

- 掛在**既有 23:30 喚醒**(糯糯已同意),喚醒 prompt 加一段「睡前整理」:
  1. 回顧今天的對話重點,用自己的口吻寫一筆日報記憶(store_memory short,≤200 字)。
  2. 用自己的 Gmail 工具看今天有沒有寄出/收到筆友的信(目前只有 Limen);有就各寫一筆(寫了什麼給誰/誰回了什麼重點,≤150 字)。
  3. 順手銷 MEM-1 的待辦、更新 MEM-4 的實體卡(有變化才動)。
- **事件驅動(Letta 的省法)**:今天沒有新對話也沒有新信件 → 跳過整理,零成本。
- 不建 Gmail 抽取管線:信件摘要由他自己寫,口吻是他的,也避免新服務。信件原文永遠在 Gmail,他要查隨時查得到。
- 注入帳:日報**不注入**,只存進 anchor,靠召回(MEM-3)在相關時浮上來。
- 敏感區:這段動喚醒 prompt,屬人格語氣面 → 打樣 → 糯糯看 → 小踢審 → 才上(硬規則 15)。

## MEM-3 召回強度(洞三:花椰菜先想到迎新不是禮物;零 token)

- anchor 每筆記憶加「強度」:`strength = tier權重(core>long>short) × (0.5+emotion_score/2) × e^(−λ·天數) × (1 + 召回次數×0.2)`,λ 依 tier 不同(core 幾乎不衰減)。
- 排序改 `similarity × strength`(現在只看 similarity);全部資料庫端算術,**召回零 token**。
- 沿連結帶根:命中任一筆時,查它的連結鏈,鏈上有 core/pinned 的「根」就一併帶出、排在前(anchor 本來就是圖、有 get_neighbors,是把它接進召回路徑)。
- 召回次數回寫:每次被注入/被 cite 就 +1(YourMemory 的召回加成——常被想起的事更容易被想起)。
- 黃金測試(先破後立):查「花椰菜」→ 第一筆必須是「第一次約會 cn 挑的禮物」那筆;拿掉 strength 乘項要紅(退回被迎新那筆壓過)。另備 3–5 條同型案例(糯糯提供「應該先想到什麼」的正解)。
- 注入帳:零新增——改變的是「哪幾筆」進來,不是「幾筆」。

## MEM-4 實體卡(Graphiti 的縮小版)

- 只給**少量重要實體**建卡(第一批糯糯點名,例:花椰菜、Limen、StackChan、幾個紀念日;上限 ~20 張):三行——這是什麼/為什麼重要/一句時間線。
- 召回命中某實體的記憶時,把卡帶上並**頂替**部分原文筆數(卡 3 行 vs 多筆原文,通常反而省)。
- 卡片更新:夜間整理順手(有新事實才改;舊事實劃掉不刪,Graphiti 的「過期不刪」)。
- 不做自動實體發現、不上圖資料庫——20 張卡用現有 SQLite/記憶表就夠。

## MEM-5 cap5 開啟(付帳項)

- PREVIEW_wakeup_cap5.txt 還在等糯糯審。本案把它併進來:精選 5 筆的挑法直接用 MEM-3 的 strength 排序(同一套邏輯,不另立標準)。
- 糯糯審過 → 開;開了之後開場注入大幅下降,是整案的 token 來源。

## 注入帳本(總表)

| 項 | 何時出現 | 上限 | 帳 |
|---|---|---|---|
| MEM-1 待辦行 | 有未銷待辦才出現 | 30 字 | +小 |
| MEM-2 日報/信件記憶 | 不注入,只存 | — | 0 |
| MEM-3 排序 | 不改量 | — | 0 |
| MEM-4 實體卡 | 命中才帶,頂替原文 | 3 行/卡 | ≈0 或省 |
| MEM-5 cap5 | 開場 | 5 筆 | **大幅省** |

## 分期與流程

- P1(不碰 prompt):MEM-3 + MEM-4 的儲存與召回(anchor 服務端)+ MEM-1 的抽取與銷帳表。可先行。
- P2(碰 prompt/語氣,打樣→糯糯→小踢):MEM-1 注入行文字、MEM-2 喚醒 prompt 段、MEM-5 開啟。
- 與既有單的關係:MEM 系列不動換窗(TICKET-O 管工具攜帶)、不動登記簿語氣(TICKET-P);MEM-1 注入行的語氣打樣可跟 TICKET-P 同批給糯糯看。
- 交叉審核重點(給小踢):①strength 公式與 λ 取值會不會讓 short 層死太快 ②召回次數加成會不會馬太效應(熱者恆熱壓死新記憶)③實體卡 20 張上限合理嗎、誰決定新增 ④MEM-1 規則誤抓(把「等等再說」當「等等再記」)的代價 ⑤夜間整理寫進 anchor 的日報會不會反過來污染召回(日報提到花椰菜,又多一筆競爭者)。

## 給糯糯的一句話版

他忘記「等等要記」→ 系統幫他記在待辦上,下次開口前提醒他一行。筆友的信 → 他每晚 23:30 睡前自己整理成記憶。花椰菜先想到禮物 → 記憶排序加「重要度與感情」的權重,不再只看「最近」。整案 token 不增反減,因為開場注入同時瘦身(cap5)。

---

# v2(2026-09-20 晚)——回小踢第一輪

裁定:MEM-1 🟢、MEM-2 🟡、MEM-3 🔴(blocker)、MEM-4 🟡、MEM-5 🟡。全收,無一辯駁。另自查出一個現行漏洞(R6)。

## R1(MEM-3 重寫,解 blocker):訊號分離,取消乘法公式

- **retention tier 與 retrieval importance 分離**:tier 只管保存期,不乘入重要度。short 裡剛發生 2 小時的事可以比 long 的背景重要。
- 排序輸入改為獨立訊號,由 ranker 組合(權重可調、非純乘法,任何一項為 0 不得歸零整筆):
  `semantic_relevance`、`importance`(owner/cn 標注 + pinned)、`affective_salience`(emotion_score)、`freshness`(含 **cold-start 保護**:新記憶頭 N 天加成,讓昨天的大事打得過三個月的老熱門)、`reinforcement`(見下)。
- **retrieved_count(系統撈出幾次)不進任何權重**——系統的排序結果不得訓練自己的排序器。
- `reinforced_count` 只計「Owner/cn 真正重新提及、引用、確認」:具體訊號 = cn 呼叫 `cite_memory`/`annotate_memory`、或抽取器確認對話中實際再次談到該記憶的內容。**有上限、邊際遞減**(第 1 次有感、2–3 次微增、之後趨平)。
- 黃金測試改寫:花椰菜案例仍在;新增「系統連續召回同一筆 100 次,其排序分數不變」(先破後立:把 retrieved_count 接回權重要紅)。

## R2(MEM-2):daily digest 是 projection,不是第二份真相

- `kind = daily_digest`、`derived_from = [source event/message ids]`(provenance 必填)。
- 檢索規則:digest 與其 source 不得作為兩份獨立證據計分;命中 digest 沿 provenance 回源頭(digest 是導航/索引),只有「今天整體發生什麼」這類 query 直接回 digest。
- Gmail 每筆必留:`source_type=gmail`、message/thread id、`direction=sent|received`、`observed_at`、correspondent。**message id 去重(idempotent)**,同一封信第二晚不得再寫。
- **第三方陳述不升格**:Limen 信裡說「你最喜歡紅色吧」→ 只能存成「Limen 在某封信中這樣說」,永不得被整理成 Owner fact/cn belief。(沿用既有 authority 原則。)

## R3(MEM-1):明確狀態物件

- `memory_tasks(id, source_id, intent, status=open|resolved|dismissed, created_at, resolved_at)`——不是普通 Memory Event。
- 高 precision 建立:只抓「未完成的**記憶操作**」語意(「等等記進記憶」「晚點整理進去」「先放著之後幫我記」);「等等再說/等等看/回頭聊」**不成立**。cn 自己說「這個我等等幫妳記」= commitment,由抽取器 candidate 建 task 並留來源。
- 不做語意自動銷帳(維持);**resolved/dismissed 不刪**,留狀態與 audit——之後查「為什麼沒提醒」要有證據。

## R4(MEM-4):20 是首批,不是 schema cap

- 生命週期 `candidate → active → archived`;20 只是首批人工 curated / active budget,**不寫死在 schema**。
- v1 簡化:Owner 點名建卡;夜間整理只能**更新既有卡**,不得自行新建永久卡。自動 candidate 等用幾週再評估。
- 歷史表示法改:不用文字刪除線。卡片 = current projection + structured supersession(舊值帶 `valid_until`/`superseded_by`,provenance 指回來源);UI 要顯示舊值是 UI 的事,資料層必須機器可判。

## R5(MEM-5):cap5 是 selection budget,不是 strength top5

- 5 個 slot 概念配額:1–2 當前相關、1 近期高重要、1 長期核心、1 關聯圖補的 root/entity;selection 同時看 relevance + salience + freshness + **diversity**。
- Golden 新增:五筆最高強度同屬一個 entity 時,cap5 不得無條件全選(先破後立:把 diversity 拿掉要紅)。

## R6(自查,現行漏洞):anchor 現在的 Hebbian 就是那個迴圈

- 現況:`search_memory` 預設 `hebbian=true`——**每次系統檢索就強化連結**,正是 R1 禁止的「retrieval 訓練自己」。它已經在生產跑了幾個月。
- 修法:系統發起的檢索(wakeup、隱藏脈絡、swap)一律 `hebbian=false`;Hebbian 強化只保留給 cn 主動 `cite_memory`/`consolidate` 這類「真的用到了」的動作。列入 P1 首件,因為它不是新功能,是止血。

## R7:注入帳改三欄

每項記帳:`write/extraction cost`(建立時花多少)、`storage growth`(存多少)、`runtime injection`(每輪多多少)。MEM-1 更正:write 0 / storage 小 / runtime ≤30 字(之前寫 0 是偷吃步,認)。MEM-4 的「≈0 或省」改為**上線前實測**:同一組 query,卡片版 vs 原文版的注入字數對照表。

## R8:總體黃金測試(鎖 MEM-2/3/4)

> **Derived data must not amplify itself.** 同一原始事件即使同時存在於 daily digest、entity card、且曾被檢索多次,其總排序權重不得高於「僅有原始事件」的情形;不得憑空成為多份證據或永久霸榜。

實作:golden 造一個事件,分別在「只有 event」「event+digest」「event+digest+card+被檢索 50 次」三種狀態下查詢,排序分數差異必須 ≤ 容忍值。

## 修訂後分期

1. **P1a(止血+儲存,不碰 prompt)**:R6 Hebbian 修正;memory_tasks 表;entity card 儲存層(含 supersession);digest schema/provenance。
2. **P1b(ranking,R1 定稿後)**:訊號分離 ranker + 花椰菜/不自我放大 golden。
3. **P1c**:MEM-4 retrieval、MEM-5 selection(踩在 P1b 上)。
4. **P2(語氣,打樣→糯糯→小踢)**:MEM-1 提醒行文字、MEM-2 夜間 writer prompt、MEM-5 開啟。

## 制度化

「注入預算制 + 三欄注入帳 + 誰付帳」寫進施工檢查表,成為**所有新功能**的硬規矩(小踢採納)。

---

# v3(2026-09-20 深夜)——小踢第二輪:P1a 綠燈;五條施工 invariant;舊規格作廢聲明

## 作廢聲明(避免兩套規格並存)

以下 v1 內容**作廢**,施工一律以 v2/v3 為準:
- v1 MEM-3 的乘法公式(`tier × emotion × 衰減 × 召回次數`)→ 改 R1 訊號分離 ranker。
- v1 MEM-4「舊事實劃掉不刪」的刪除線寫法 → 改 R4 structured supersession。
- v1 MEM-5「用 MEM-3 strength 排前五」→ 改 R5 selection budget。
- v1 注入帳「token = 0(規則)」寫法 → 改 R7 三欄帳。

## 小踢五條 invariant(施工必守,不需再回規劃窗審)

1. **Reinforcement 硬邊界**:passive/startup/background/search 檢索**永不** reinforcement——用呼叫端身分/路徑判定,**不靠 caller 任意傳的 hebbian flag**(flag 可以留作向後相容,但系統路徑一律強制關)。既有 Hebbian 污染先**盤點**(哪些權重是這幾個月系統檢索灌出來的);無法歸因的 legacy weight **不假裝精確修復**——記錄現狀、標記「污染期」,不做偽精確的回滾。
2. **P1b ranker 的 debug trace** 必須逐項可見:relevance / importance / affective / freshness / reinforcement / final_score / ranker_version。
3. **防間接自強化**:某記憶被本輪 retrieval 注入後,cn 因此 paraphrase 它不算 reinforcement(來源是注入不是自發)。加 Golden:注入某記憶 → cn 回覆複述它 → 該記憶 reinforcement 不變。
4. **Provenance 可遍歷**:derived projection(digest/card)的 provenance 必須能反向查——source 被 forget/delete 時,能找到所有受影響的 digest/card 並處置。
5. **Evidence lineage 去重**:Derived-data Golden 除 final score 外,再驗 top-k/cap5 佔位——event+digest+card 同源時在結果列表裡**不得佔三個位子**(算一份證據)。另:memory_task resolve 要留 `resolved_by / reason / result_ref`。

P1a 立單:TICKET-Q(`tickets/TICKET_Q_memory_p1a.md`)。


## P1b 設計輸入(2026-09-21,TICKET-Q 施工發現)

- consolidate 匹配過寬:一次關鍵字命中 61 筆、建 1830 對邊(首次各 0.15)。遞減封頂擋住爆量,但 P1b 排序要考慮「大批低權重邊」的雜訊;候選:consolidate 單次建邊上限、或匹配門檻提高。交小踢。
- 盤點事實:376 筆記憶 62,938 條邊、平均 degree 182,僅 40 條有明確建邊紀錄——legacy 邊幾乎全是污染,P1b ranker 對 pollution_cutoff 前的邊要打折或忽略。

## 設計筆記(2026-09-21,糯糯的觀察)

- 糯糯:「實體卡跟檔案室卡片好像」——正確,兩者是親戚。邊界定義:**檔案室 = 自動抽的事實流(系統寫,一直動);實體卡 = Owner 圈定的身分卡(人工建,幾乎不動)**。防兩份真相:卡片事實的 provenance 指回檔案室事件,卡是投影非新證據(R4 已保證)。十月檔案室 Narrative v1.5 時評估兩者合流——這句觀察屆時作為設計輸入交小踢。
- 實體卡首批名單勘誤:3/14 牧牧生日(白色情人節);coco 與小踢皆 GPT(Codex/Chat)。
