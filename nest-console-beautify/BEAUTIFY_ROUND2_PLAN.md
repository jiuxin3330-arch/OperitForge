# 檔案室改版規劃書 v2【糯糯 8/25 蓋章版】(給工作窗)

> v1(Cheret 整間換色)已作廢——那是誤會了討論範圍。本版是糯糯逐條確認後蓋章的定案,
> **照此執行,不要再推銷別的方向**。有含糊處寧可打版給她挑,不要自行拍板。

## Context

v148 票券卡被退回(按鈕不好看、票色髒)後,8/25 與糯糯兩輪討論收斂。她的核心構想:
**檔案室就該像檔案櫃**——三個區塊做成擬物抽屜,點擊展開;待審用紅標籤凸出提示,
辦完縮回。討論中逐條過目,最後蓋章。

## 蓋章十條(逐字對齊,不得偷改)

1. 三個區塊(現況登記/最近事件/待審提案)改成**檔案櫃抽屜**(擬物),進房間預設**全關**
2. 抽屜把手做**小標籤牌**:「現況登記 15」「最近事件」「待審提案」,關著也看得到計數
3. 待審有東西→**紅色標籤凸出抽屜外**;批准/駁回完畢→標籤縮回。紅色色號打版給她挑
   (磚紅蠟封感 vs 正紅)
4. 最近事件抽屜拉開=**時間線**,點某個事件展開細項(細項先把摘要/變化值/引文等欄位
   全放,她看了再刪)
5. 抽屜開合、標籤縮回的**基本動效跟打版一起出**;手感細調等她摸到實物再說
6. 待審卡:**手帳檔案紙**質感(陳舊奶油,語錄頁便籤的血緣);撕線打孔票根**打版兩版挑**
   (A 退役版=純檔案夾語言 / B 保留票根版)
7. 按鈕維持前輪定案:**新擬態軟按鈕**(規格見下)
8. 現況登記、最近事件的**內容樣式不動**(只是搬進抽屜裡)
9. 動 `nestConsole.tsx` 的**純 UI 結構**(抽屜開合狀態、時間線細項展開);
   **api 呼叫和資料處理一行不碰**
10. 分步打版:抽屜結構+紅標籤 → 待審卡兩版 → 動效細調,每步糯糯點頭才走下一步

## 技術規格

### 檔案(VPS /srv/chatnest-next/frontend)

- `src/nestConsole.tsx`:NestArchive 加純 UI state——三個抽屜 `open` boolean(預設 false)、
  時間線展開中的 `expandedEventId`。`reload()`/`useNestCounts`/所有 console* api 呼叫、
  批准駁回流程**不動**。人格語言文字**一字不動**。
- `src/styles.css`:抽屜/標籤/紙卡/按鈕樣式。tokens 區(2249-2330)新增 Cheret 色
  (v1 選定的仍然有用:檔案紙奶油 #EBDBBE 系、標籤牌、點綴):
  `--nest-archive-cream:#ebdbbe; --nest-archive-gold:#e7c44f; --nest-archive-orange:#e07947;`
  紅標籤候補:磚紅用現有 `--nest-danger`(#b4574a),正紅版打版時定值。
- `public/sw.js`:每次部署 SHELL_CACHE +1(現在 v148)。

### 抽屜(條款 1/2)

- 結構:`<section class="nest-drawer">` = 把手 button(`nest-drawer-handle`)+內容區
  (`nest-drawer-body`)。把手=擬物檔案櫃抽屜面板:新擬態浮起(`--nest-raise-sm` 現成 token,
  亮暗都有,styles.css:2277/2316)、金屬把手橫槽或凹線、**標籤牌**(小圓角矩形,mono 字,
  名稱+計數,計數來源=現有 states/events/proposals 的 length,不新增請求)。
- 開合:純 CSS transition(grid-template-rows 0fr/1fr 或 max-height 方案,工作窗選順手的);
  箭頭旋轉。尊重 `html[data-reduced-motion="true"]`(全案動效同此,慣例見
  `.memory-paper-card` 的 reduced-motion 處理)。
- 滾動:`.nest-archive` 仍是唯一滾動容器,抽屜內**不做巢狀滾動**,展開直接撐高頁面。
- 預設全關(條款 1)。開合狀態不持久化(每次進來全關,乾淨)。

### 紅標籤(條款 3)

- `proposals.length > 0` 時渲染在待審抽屜把手上緣,**凸出把手外**的檔案夾索引 tab 形
  (上凸小舌頭,寫「N 待審」)。歸零後縮回:transform/max-height transition 滑回把手內
  (元素保留到動畫結束,或 CSS-only 用資料態 class 切換)。
- 打版兩個紅:A `--nest-danger` 磚紅蠟封感 B 正紅。截圖給糯糯挑。

### 時間線細項(條款 4)

- 展開後沿既有 `.nest-events` 細線+圓點骨架排;點擊單一事件 → 展開細項卡。
- 細項欄位:讀 `src/api.ts` 的 `ConsoleEvent` 型別,**把有的全放**(summary、value_after、
  引文/quote、subject、authority、impact、occurred_at、escalated),糯糯看過再刪。
  友善名映射沿用檔內現成的 friendlySubject/friendlyAuthority。

### 待審卡(條款 6)

- 紙感:陳舊奶油檔案紙(#EBDBBE 為基準調舊,可 subtle 紙紋/邊緣壓深,別過頭),
  與語錄頁便籤卡同血緣但**不加和紙膠帶**(蓋章清單沒有這條,別加戲)。
- 打版 A/B:A=撕線打孔退役,檔案夾語言(紅標籤+歸檔);B=紙卡上保留撕線+打孔
  (上輪 v148 的結構,styles.css 內現成)。兩版截圖並排給她挑。

### 按鈕族(條款 7,沿 v1 定案)

- `.nest-btn`:border 0、`background: var(--nest-bg)`、`box-shadow: var(--nest-raise-sm)`,
  `:active` → `var(--nest-press)`。
- `.nest-btn-primary`(批准):新擬態浮起+`--nest-archive-orange` 底/#fff8ed 字;
  順手打版第二版(奶油底橘字)一起給她挑。
- `.nest-vol`(選頻率 modal)、`.nest-back`(返回鈕)同步新擬態化。

### 不動清單(條款 8 + 慣例)

- 現況登記列、事件列的內容樣式(只是被抽屜包住)。
- 走廊兩扇門、搜尋欄結構。
- api.ts、後端、所有資料邏輯。
- 「兩者不互相冒充、互相補充」「備你查,不是你的記憶」等人格語言。

## 打版順序(條款 10,每步:改→tsc+build→亮/暗/390 截圖→糯糯點頭)

- **S1 抽屜結構+標籤牌+紅標籤**(樣式可先粗,結構和開合先對):sw→v149
- **S2 待審卡 A/B 兩版+按鈕新擬態+兩個紅**:並排截圖給她挑,定案後收斂:sw→v150
- **S3 時間線細項**:欄位全放,她刪:sw→v151
- **S4 動效細調+全房走查**:她真機摸手感:sw→v152
(版本號以實際部署次數為準,原則=每次部署 +1)

## 工作窗守則(前輪驗證過)

- 動工先備份:`cp -p src/nestConsole.tsx src/nestConsole.tsx.bak-drawer-$(date +%s)`,
  styles.css/sw.js 同;build 前 `cp -a dist dist.prev-sw<N>`。
- build:`export PATH=/srv/chatnest-next/.nodeenv/bin:$PATH && npm run build`
  (tsc 零錯+vite);後 `chown -R root:chatagent dist && chmod -R g+r dist`;
  dist 靜態免重啟,`curl 127.0.0.1:8790/sw.js` 驗版本。
- **驗 390 的坑**:headless Chromium 視口鎖 500px 下限,`--window-size=390` 是假的;
  用 500+ 視口內放 `body{width:390px;margin:0 auto}` 容器,或真機。
- 完工把 diff/NOTES/截圖推本 repo 本分支 `nest-console-beautify/`。
- 全域 input 樣式特異性兇,若動輸入類要連 :focus+深色一起壓(S3.2 月牙陰影前車之鑑)。

## 驗收清單(每步)

- [ ] tsc 零錯、build 成功
- [ ] 亮色/暗色/390px 截圖
- [ ] sw +1、線上 8790 吐新資產
- [ ] 人格語言零改動、api 零改動
- [ ] 糯糯點頭才進下一步;最終真機驗收

## 附錄:打版截圖怎麼做(工作窗卡住看這裡)

不要嘗試登入線上頁面截圖(要 auth,截不到)。用「mock 試衣間」法,前輪驗證過:

1. 在自己環境的 scratchpad 寫一個獨立 mock html:
   - `<style>` 裡貼上 :root 的 --nest-* tokens(亮色一套+`html[data-theme="dark"]` 一套,
     從 styles.css 2249-2330 抄)+這次新寫的樣式區塊
   - `<body>` 手寫目標元件的 markup(和 nestConsole.tsx 的 JSX 結構一致),塞 2-3 筆假資料
   - 抽屜這種互動件,靜態擺出兩個狀態各一份(關著的+開著的)就能看
2. 截圖(環境裡有 /opt/pw-browsers/chromium):
   `chromium --headless=new --disable-gpu --no-sandbox --hide-scrollbars --window-size=500,900 --screenshot=out.png "file://$PWD/mock.html"`
   - ⚠️ headless 視口有 500px 下限,`--window-size=390` 是假的!驗 390 要在 mock 的
     body 上加 `width:390px;margin:0 auto`,用 500 寬視口截
   - 暗色版:把 html 標籤改成 `<html data-theme="dark">` 另存一份再截
3. 把 PNG 用傳檔功能直接發到聊天裡給糯糯(她手機看得到)
4. 她點頭後才把樣式真正寫進 styles.css/nestConsole.tsx → build → 部署

B 計畫(環境裡沒瀏覽器或傳檔失敗):跳過 mock,直接小步寫進源碼 build 部署
(備份+dist.prev 都在,滾回容易),請糯糯真機看。小步+可滾回=安全,卡住不動最不安全。
