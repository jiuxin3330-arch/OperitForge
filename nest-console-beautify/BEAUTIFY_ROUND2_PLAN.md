# 檔案室整間美化 · 規劃書(給工作窗)

## Context

票券卡第一版(sw v148,撕線+打孔票根)糯糯驗收退回兩點:**按鈕不好看**(白描邊+黑實心,跟票面不搭)、**票根顏色髒**(`--nest-ticket #e4d9ac` 亮色下偏土)。糯糯給了三張參考圖並拍板:

- **配色方向:復古海報色卡(Jules Cheret)**——關鍵發現:Cheret 色卡的 #EBDBBE / #E7C44F / #E07947 就是日記日曆熱度格 `.memory-day[data-heat]` 在用的色(styles.css:14247-14249),檔案室走這組=跟日記半邊天生同源。
- **按鈕:新擬態軟按鈕**——憲法「新擬態只給按鈕」,現在按鈕反而是全房間唯一沒用新擬態的元素。
- **範圍:檔案室整間**(`.nest-archive` 房間內全部;**走廊兩扇門不動**)。

流程約定:這輪只規劃,實作交工作窗;打樣分步給糯糯驗收,她說好才算好。

## 現況(本 session 已親手驗證過的事實)

- 前端:VPS `/srv/chatnest-next/frontend`,樣式全在 `src/styles.css`(nest 檔案室區塊 ~14504 行起,tokens 在 2249-2330)。`src/nestConsole.tsx` 上輪證明**完全不用碰**(純 CSS 可達成,連 className 都不用加)。
- 新擬態 tokens 現成:`--nest-raise / --nest-raise-sm / --nest-press / --nest-groove`,**亮暗兩套都有定義**(暗色在 html[data-theme="dark"] 段,styles.css:2312-2319)。
- 撕線+打孔票根結構(v148 上的)糯糯沒有退,退的是**顏色**——結構保留。
- 上輪順手修的 `messageSegments.ts` table case 已上線,這輪不用管。
- 線上 sw = v148;備份 `.bak-ticket-1787597453` 三件 + `dist.prev-sw147-preticket/` 都在。

## 設計規格

### 1. 新 tokens(Cheret 檔案館色,加進 :root 的 nest token 區)

```css
/* Cheret 檔案館色(糯糯 8/25 選定,前三個=日曆熱度色同源) */
--nest-archive-cream:  #ebdbbe;  /* 票底奶油米 */
--nest-archive-gold:   #e7c44f;  /* = heat mid */
--nest-archive-orange: #e07947;  /* = heat high */
--nest-archive-peach:  #e1ab8c;  /* 蜜桃,輔助/hover */
--nest-archive-green:  #9cbe88;  /* Cheret 綠,owner 色條候補 */
```

暗色模式:抄日曆熱度的現成配方(styles.css:14358-14360)——大面積用 `color-mix(in srgb, 原色 N%, var(--nest-bg))`(票底約 20-25%,打樣定),小面積(色條、圓點、文字點綴)直接用原色。

### 2. 票券卡 `.nest-proposal`(修「髒」)

- `--nest-ticket` 改值:light `#ebdbbe`、`--nest-ticket-hi` 改 `#f3ead6`(奶油亮階,打樣可微調);dark `color-mix(in srgb, #ebdbbe 22%, var(--nest-bg))` / hi 維持白 8% 疊層。注意 `--nest-ticket-hi` 也被 `.nest-vol:hover` 引用——正好一起變新色,是想要的效果。
- 撕線、打孔、tag 細線、圓角 16、paper-card 陰影配方:**全部保留**。
- tag 前加 6px 圓點(`::before`,`--nest-archive-orange`)當「登記章」點綴。
- 引文左邊線:蝴蝶橘 `#DA724F` 換 `--nest-archive-orange`(兩色很近,統一進 Cheret 系)。

### 3. 按鈕族 → 新擬態(修「不好看」)

- `.nest-btn`(駁回):`border: 0; background: var(--nest-bg); box-shadow: var(--nest-raise-sm);` hover 維持浮起,`:active` 換 `var(--nest-press)`。在奶油票面上,`--nest-bg` 底的按鈕會像「浮在票上的圓鈕」。
- `.nest-btn-primary`(批准):同新擬態浮起,但底色 `--nest-archive-orange`、文字 `#fff8ed`;陰影配方照抄 raise-sm(暗階自動來自 `--nest-shadow`)。**打樣兩版**給糯糯挑:A) 橘底實色新擬態 B) 奶油底+橘字橘描邊。
- `.nest-vol`(批准選頻率 modal 的四個選項):描邊卡 → 新擬態浮起卡(`--nest-surface-strong` 底 + raise-sm,active press)。
- `.nest-back`(返回圓鈕):描邊 → 新擬態浮起(它是按鈕,憲法適用)。
- `.nest-btn:disabled` 維持 opacity 降低,不給 press。

### 4. 現況登記列 `.nest-state-row`(調和)

- 白卡底 `#fffef9` + paper 陰影:**不動**(跟日記 paper-card 同款,是對的)。
- 左側 authority 色條換 Cheret 系:owner `#9cbe88`(Cheret 綠,保留糯糯=綠的身分語言)、assistant 維持 `#71C2CB`(牧牧=青藍,身分色不搬家)、system 維持紫、衝突/暫定 `#DA724F` → `--nest-archive-orange`。
- `.nest-state-warn` 文字色同步換 `--nest-archive-orange`。

### 5. 事件時間軸 `.nest-events`(調和,順便更有語意)

- impact 圓點改對齊日曆熱度語言:high `--nest-archive-orange`、medium `--nest-archive-gold`、low 維持 muted 灰。(現在 high=綠 medium=青,和「熱度」語意不通;改完跟日曆一個語言:越熱越橘。)

### 6. 搜尋欄與其他(小修)

- `.nest-search` 內凹新擬態已達標:不動結構;focus-within 時放大鏡 icon 色亮到 `--nest-archive-gold`(小點綴,可選,打樣不順眼就砍)。
- `.nest-section-head` / 麵包屑 / 空狀態:不動。
- 人格語言(「兩者不互相冒充、互相補充」「備你查,不是你的記憶」等)**一字不動**。

## 執行順序(分步驗收,防爆炸)

每步:改 → tsc+build → 亮/暗/390 截圖 → 糯糯點頭 → 才走下一步。

1. **第一步:tokens + 票券卡換色 + 按鈕族新擬態**(她最在意的兩點,含 primary 兩版打樣)
2. **第二步:登記列色條 + 時間軸圓點 + warn 色統一**
3. **第三步:搜尋欄 focus 點綴(可選)+ 全房間走查**

每步收尾:`sw.js` SHELL_CACHE +1(第一步 v148→v149,之後每次部署再 +1)。

## 工作窗守則(上輪驗證過的)

- 動工先備份:`cp -p src/styles.css src/styles.css.bak-<美化名>-$(date +%s)`(sw.js 同)。build 前 `cp -a dist dist.prev-sw<N>`。
- 只動 `styles.css` + `sw.js`;nestConsole.tsx 不碰。
- build:`export PATH=/srv/chatnest-next/.nodeenv/bin:$PATH && npm run build`(tsc 零錯 + vite);build 後 `chown -R root:chatagent dist && chmod -R g+r dist`;dist 是靜態檔,免重啟,`curl 127.0.0.1:8790/sw.js` 驗版本號。
- **驗 390px 的坑**:headless Chromium 視口有 500px 下限,`--window-size=390` 是假的;要用 500+ 視口裡放 `body{width:390px;margin:0 auto}` 容器模擬(或真機)。驗證 mock 放 scratchpad。
- 完工把 diff/NOTES/截圖推 OperitForge repo `claude/file-room-ui-beautify-dv83xu` 分支(已有 `nest-console-beautify/` 目錄,上輪 commit 5fa87da)。

## 驗收清單(每步都要)

- [ ] tsc 零錯、build 成功
- [ ] 亮色 / 暗色 / 390px 三件套截圖
- [ ] sw 版本號 +1、線上 8790 吐新資產
- [ ] 人格語言零改動
- [ ] 最終:糯糯真機說好
