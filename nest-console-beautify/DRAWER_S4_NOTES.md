# 檔案室改版 S4 · 新擬態收尾+sheet 動效(2026-08-28)

打樣 2 版收斂(s4-proofing-v1→v2),糯糯拍板「全部米白+票券卡案B+駁回鍵一起改,上線」。
已部署 **sw v153**。最終打樣:`s4-final/s4-proofing-v2.html`。
**改版輪 S1-S4 至此全部完成**,只剩糯糯真機走查的手感反饋。

## 定稿內容(條款 7 後半+S4)

- **`.nest-back` 返回鈕**:新擬態化——去框線、米白底(`--nest-bg`)、`--nest-raise-sm` 浮起,
  `:active` scale(0.94)+`--nest-press` 內凹;32px→34px(打樣尺寸)
- **`.nest-vol` 選頻率選項**:去框線(舊版還有 1px border,違平面憲法)、米白底、
  新擬態浮起,`:active` scale(0.98)+內凹;hover 換色刪除
- **`.nest-btn`(駁回/取消)**:奶油底 → 米白底+`--nest-text` 字
  (糯糯:「駁回鍵顏色要一起改」,與返回鈕/選頻率同語言);批准橘鈕不動
- **`.nest-proposal` 票券卡**:奶油 `--nest-archive-cream` → 筆記紙色 `--nest-paper-note`
  (案B;她嫌奶油「太深太暗」,點名要同抽屜筆記紙裝飾的顏色)
- **選頻率 sheet 開啟動效**:scrim 0.22s 淡入 + sheet 0.32s 上滑 26px(抽屜曲線
  cubic-bezier(0.32,0.72,0,1)),CSS animation 掛載即播;reduced-motion 全關

## 改動檔案(VPS /srv/chatnest-next/frontend)

- `src/styles.css`:五處(見上)。補丁腳本=`s4-final/s4patch.py`(每處 assert,
  md5 6ec2c993fb87fe89762116616a88aab6,與 VPS 執行檔一致)
- `public/sw.js`:v152 → v153
- `src/nestConsole.tsx`:**零改動**(這輪全 CSS)

## 備份與回滾

- `src/styles.css.bak-s4-1787952440`、`public/sw.js.bak-s4-1787952440` + `dist.prev-sw152-pres4/`
- 回滾:.bak 蓋回 → `npm run build`;急救 `rm -rf dist && cp -a dist.prev-sw152-pres4 dist`

## 驗證

- build 過(tsc -b 含在內)、8790 已吐 v153
- nest-scrim-in/nest-sheet-up/nest-paper-note 確認在 dist CSS
- 打樣頁亮暗已 QA;最終以糯糯真機為準

## 打樣過程(2 版)

- v1:返回鈕 A奶油/B米白、選頻率 sheet A/B、sheet 上滑動效 → 她:「全部選米白底!」
  +追加:票券卡也改淺(米白或筆記紙色,「不要太深太暗」)
- v2:米白鎖定;票券卡 案A米白/案B筆記紙色 並排 → 她:「B!駁回鍵顏色一起改!上線!」

## 改版輪總結(S1→S4)

- S1 抽屜結構(v149)→ S2 全視覺 16 版打樣(v150+間距 v151)→ S3 時間線細項 4 版(v152)
  → S4 新擬態收尾 2 版(v153)
- 蓋章十條全部落地;api/資料流/人格語言零改動(逐條款覆核)
- 後續:糯糯真機走查若有手感單子,小步修+sw+1
