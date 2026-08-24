# 檔案室改版 S1 · 抽屜打版(2026-08-25)

規劃書 v2【蓋章版】的第一步:檔案櫃抽屜結構+把手標籤牌+待審紅標籤。
對應蓋章條款 1/2/3/5(基本動效)/8/9。已 build 部署上線(sw v149),等糯糯點頭進 S2。

## 改了什麼

**nestConsole.tsx(純 UI 結構,api 零改動)** — 完整新檔在 `s1-drawer/nestConsole.tsx`

- 新增 `DrawerKey` 型別+`drawerOpen` state(三個 boolean,預設全關,不持久化)、`toggleDrawer`
- 三個區塊各包成 `<section class="nest-drawer">` = 把手 button(`nest-drawer-handle`,
  含標籤牌 `nest-drawer-plate` 名稱+計數、金屬凹槽 `nest-drawer-groove`、箭頭)+
  `nest-drawer-body > nest-drawer-inner`(內容原封不動搬進去,條款 8)
- 待審抽屜多一個 `nest-drawer-tab`(紅標籤):`proposals.length > 0` 時加 `is-out` 凸出,
  歸零時 class 拿掉滑回把手後面(元素常駐,CSS 資料態切換)
- 計數來源=現有 `states/eventsToShow/proposals` 的 `.length`,不新增請求(條款 2)
- 人格語言一字未動;`reload`/`useNestCounts`/批准駁回流程全部不動(條款 9)

**styles.css** — 新增區塊在 `s1-drawer/drawer-styles.css`(append 到檔尾),另外兩處 token 插入:

- 亮色 `:root`(`--nest-ticket-hi` 後):`--nest-archive-cream/gold/orange`(Cheret 三色)
- 暗色 `html[data-theme="dark"]`:同名 token 用熱度色 25%/38%/55% color-mix 配方
- 抽屜把手=新擬態浮起(`--nest-raise-sm` 現成 token);拉開時面板轉 `--nest-press`(內壓)
- 開合=grid-template-rows 0fr↔1fr transition;箭頭旋轉;`html[data-reduced-motion]` 全關動效
- 抽屜內不做巢狀滾動,展開直接撐高頁面(`.nest-archive` 仍是唯一滾動容器)
- 紅標籤=絕對定位在把手上緣、右側 22px,`border-radius: 7px 7px 0 0` 檔案夾索引 tab 形,
  `is-out` 時 `translateY(-72%)` 凸出;S1 先用 `--nest-danger` 磚紅,磚紅 vs 正紅兩版 S2 打版

**sw.js**:SHELL_CACHE v148 → v149。

## 打版裁量(給糯糯挑刺,都能改)

1. **搜尋自動拉開事件抽屜**:搜尋結果放在事件抽屜裡,抽屜關著會看不到,所以按下搜尋時
   自動把它拉開(純 UI)。不喜歡可改成別的呈現。
2. **拉開的把手變「按下」樣**(新擬態內壓),視覺語言=「這格是開的」。
3. **三個把手都有計數**(現況 15/事件 20/待審 N)。蓋章樣本只寫了「現況登記 15」,
   如果事件/待審不想放數字可以拿掉。
4. 紅標籤位置(右側)、凸出高度、標籤牌奶油底色深淺,都是可調參數。

## 驗證

- `tsc --noEmit` 零錯、`npm run build`(tsc -b + vite)通過
- 亮/暗 × 390 截圖:`screenshots/drawer-s1-{light,dark}.png`(mock 試衣間法,
  mock 檔在 `s1-drawer/mock-{light,dark}.html`,附錄流程可重用)
- 線上 `127.0.0.1:8790/sw.js` 已吐 v149
- 註:目前線上待審=0 筆,真機上紅標籤不會凸出(行為正確);mock 裡塞了 2 筆假資料展示

## 備份與回滾(VPS /srv/chatnest-next/frontend)

- `src/nestConsole.tsx.bak-drawer-1787601171`
- `src/styles.css.bak-drawer-1787601171`
- `public/sw.js.bak-drawer-1787601171`
- 整個舊 dist:`dist.prev-sw148-predrawer/`

回滾:三個 .bak 蓋回原位 → `npm run build`(node 在 /srv/chatnest-next/.nodeenv/bin)。
急救:`rm -rf dist && cp -a dist.prev-sw148-predrawer dist`(sw 回 v148)。

## 給下一步(S2)的話

- S2 =待審卡 A/B 兩版(撕線退役 vs 保留)+按鈕新擬態(primary 兩版)+兩個紅並排挑,sw→v150
- 截圖照規劃書附錄的 mock 試衣間法做:**工作窗環境本地就有 chromium
  (/opt/pw-browsers/chromium)和傳檔功能,不要試圖從 VPS 搬圖片回來**(二進位過不了,
  這輪在這裡卡了半天)。CSS 素材用 exec_vps 讀文字段落回來即可。
- mock html 生成邏輯可以直接改 `s1-drawer/mock-*.html`。
- 驗收官還是糯糯,她說好才算好。
