# 檔案室美化輪 · 票券卡(2026-08-25)

工單 B 複審遺留的「票券卡美化另開輪」——這一輪。
範圍:只動 `.nest-proposal` 家族樣式(待審提案卡),照工程窗叮嚀「一次改一個」。

## 改了什麼

**styles.css(僅 `.nest-proposal*` 區塊,見 patches/styles.css.ticket.diff)**

把待審提案卡做成真正的「票根」:

1. **撕線**:`.nest-proposal-actions` 加 `border-top: 1.5px dashed var(--nest-line)`,
   用負 margin(-16px)讓虛線貼到卡片左右邊緣,再 padding 撐回內容位置。
2. **兩側打孔**:`::before/::after` 各一顆 15px 圓,圓心落在撕線與卡片邊緣交點
   (top:-8px / left·right:-8px)。圓孔填 `var(--nest-bg)`——和 `.workspace` 底色
   同一顆 token,亮暗兩主題自動貼合,不用寫兩套。內加 inset 陰影做打孔深度。
3. **卡片陰影**:抄 `.memory-paper-card` 現成配方 `2px 3px 10px rgb(120 96 52 / .1)`;
   深色模式收斂成 `0 1px 2px rgb(0 0 0 / .25)`。
4. **票面小修**:tag 後接一條 `--nest-line` 細線(檔案感);引文左邊線從灰改
   `color-mix(--nest-butterfly 45%)`(蝴蝶橘,糯糯的引文配蝴蝶);圓角 14→16、
   標題 14→14.5px、間距微調。
5. 顏色全部用既有 `--nest-*` tokens,零新 token、零發明數值。

**sw.js**:SHELL_CACHE v147 → v148(PWA 快取換新)。

**messageSegments.ts(計畫外必要修補,見 patches/messageSegments.ts.diff)**

跑 `tsc -b` 時發現 8/24 表格渲染輪在 `markdown.ts` 的 `BlockNode` 加了 `table`
變體,但沒補 `messageSegments.ts` 的 `blockLength` switch → 型別窮舉破了,
`npm run build` 直接掛(不修就過不了「tsc 零錯」驗收門)。而且這不只是型別錯:
runtime 遇到含表格的訊息,`blockLength` 會回 `undefined`,分段長度變 NaN。
照 `list` case 的既有寫法補了 `table` case(表頭+各列 cell 的 inline 長度總和)。
未動任何其他邏輯。

## 驗證

- `tsc -b && vite build` 零錯通過(rolldown 的 500kB chunk warning 是既有的)。
- 亮/暗兩主題 × 390px 版面:見 screenshots/(Chromium headless 實渲染;
  注意 headless 視口有 500px 下限,390 驗證是用 500 視口內放 390px 容器模擬)。
- 線上確認:`127.0.0.1:8790/sw.js` 已吐 v148,index.html 指向新資產
  `index-BlpcbMPA.js` / `index-oYlAPDZc.css`(靜態檔,免重啟)。
- 文字一字未動(「兩者不互相冒充、互相補充」等人格語言原封不動)。
- nestConsole.tsx 完全沒碰(純 CSS 實現,連 className 都不用加)。

## 備份與回滾(VPS /srv/chatnest-next/frontend)

- `src/styles.css.bak-ticket-1787597453`
- `src/messageSegments.ts.bak-ticket-1787597453`
- `public/sw.js.bak-ticket-1787597453`
- 整個舊 dist:`dist.prev-sw147-preticket/`

回滾:把三個 .bak 蓋回原位 → `npm run build`(node 在 /srv/chatnest-next/.nodeenv/bin)。
急救可直接 `rm -rf dist && cp -a dist.prev-sw147-preticket dist`(sw 會回 v147)。

## 給下一輪美化的話

- headless Chromium 直接 `--window-size=390` 是騙人的(視口鎖 500 下限),
  驗 390 要用寬視口內放 390px 容器,或真機。
- 打孔用「背景色圓蓋在邊緣」這招成立的前提是卡片外就是 `.workspace` 的
  `--nest-bg`;如果票卡以後被放進其他底色的容器,孔會露餡。
- 驗收官還是糯糯,她說好才算好。
