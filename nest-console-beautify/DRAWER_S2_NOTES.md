# 檔案室改版 S2 · 打樣定稿+上線(2026-08-26)

打樣 16 版收斂後糯糯說「直接上線」。已部署 **sw v150**。
最終打樣:`s2-final/s2-proofing-final.html`(手機可開,亮暗切換+可點開合)。

## 定稿內容(全部平面擬物:零漸層零立體零框線,新擬態只給按鈕)

- **抽屜**:平面色塊面板(`--nest-drawer-face` 亮 #f1eedb/暗 #313831,開=深一階)、
  兩行把手(標題貼+箭頭/內嵌拉手槽=淺槽+深縫兩層色塊)
- **標題貼三式**:現況=貼紙(奶油,微歪+右下斜切角)/事件=掛牌(深奶油 #dcc196,左端穿孔)/
  待審=紙膠帶(金 74% 半透明,兩端撕邊);待審=0 時膠帶淡化(26%)+字轉 muted
- **紅緞帶**(取代舊紅標籤):從抽屜內向上凸出,頂端單 V 燕尾(22%)朝上,只顯數字,
  疊進面板 12px;歸零=整條滑進抽屜消失(`retracted`,transform+opacity)。
  開關抽屜時緞帶不動(跳蛋動效已處決 www)
- **溢出紙堆裝飾**(`.nest-deco`,純視覺 aria-hidden):矮基底連綿層(露 4-9px,大量重疊)+
  高音符(夾板/筆記紙/帳單);精緻件:夾板=牛皮板+金屬夾、筆記紙=細線 1px 鋪滿不碰邊、
  帳單=底部鋸齒+兩條虛線;全暖色、以抽屜中心線為界向外歪斜;各抽屜構圖錯開
- **開合動效**:按壓縮小 scale(0.985) 回彈(原地零位移)+紙片同時向上向外散開
  (基底小動/高片大動),收回 .22s 快;曲線 cubic-bezier(0.32,0.72,0,1)
- **票券卡**:平面奶油底(`--nest-archive-cream`)+ink 字,撕線打孔保留(漸變刪除)
- **按鈕**:駁回=奶油底 ink 字/批准=橘底白字,都新擬態(raise-sm/:active press+scale .97)
- **走廊門卡膠囊**:案 A=奶油底磚紅字(黑膠囊退役)

## 改動檔案(VPS /srv/chatnest-next/frontend)

- `src/nestConsole.tsx`:S1 結構上加標題貼三式/緞帶(數字+retracted)/裝飾 span 組/
  兩行把手。api 與資料流零改動。完整檔=`s2-final/nestConsole.tsx`
- `src/styles.css`:①tokens 新增(tan/ink/drawer-face/pull/line-soft/clip-metal/紙色六種,
  亮暗各一套)②S1 抽屜區塊整段替換為 `s2-final/drawer-s2.css` ③.nest-proposal 平面化
  ④.nest-btn 家族重寫 ⑤.nest-dot-badge 案A ⑥reduced-motion 全關
- `public/sw.js`:v149 → v150

## 備份與回滾

- `src/*.bak-s2-1787782209`(三件)+ `dist.prev-sw149-pres2/`
- 回滾:.bak 蓋回 → `npm run build`;急救 `rm -rf dist && cp -a dist.prev-sw149-pres2 dist`

## 驗證

- tsc 零錯(build 內含 tsc -b)、vite build 過、8790 已吐 v150
- 新 class(nest-drawer-plate/nest-deco/nest-plate-tape/retracted 等)確認在 dist CSS
- 打樣頁四狀態(開關×亮暗)已逐版自檢;最終以糯糯真機為準

## 未做(刻意)

- `.nest-vol`/`.nest-back` 新擬態化(條款7後半):打樣沒過這塊,不擅動,留 S3/S4
- 時間線細項(S3)、動效手感細調+全房走查(S4):等糯糯開工令

## 血淚教訓(S2 十六版,接手者必讀)

1. 「擬物」=平面色塊擬物,不是立體;整個 app 是平面語言
2. 她說改 A 就只改 A;「順手優化」是罪
3. 字串替換必須 assert;silent fail 會賠掉一整輪信任(v8 動效事故)
4. `background:` 縮寫會殺 background-image(v12 筆記紙空白事故)→ 裝飾一律 background-color
5. 參考圖釘著逐項對照,別憑刻板印象(文件夾翻車)
6. 兩個形容詞(鋪滿+自然)是同時成立,不是二選一;聽不懂先複述再動手
7. QA 要放大看細節+四狀態全檢
