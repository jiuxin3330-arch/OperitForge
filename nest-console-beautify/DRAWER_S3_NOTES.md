# 檔案室改版 S3 · 時間線細項(2026-08-28)

打樣 4 版收斂(s3-proofing-v1→v4),糯糯說「上線」。已部署 **sw v152**。
最終打樣:`s3-final/s3-proofing-v4.html`(手機可開,亮暗切換+可點開合+點事件展開)。

## 定稿內容

- **串珠時間線**:線 1.5px(`--nest-line-soft`)從珠後穿過(z-index 0/1),
  珠 7px 加外圍 3px 背景色圈(`box-shadow: 0 0 0 3px var(--nest-bg)`)——
  視覺上「線不碰珠」(糯糯定案:碰到與不碰到兩版比過,選不碰)。
  珠色不變(high 綠/medium 藍綠/其他 muted);展開時珠 scale(1.4)。
- **點事件展開細項卡**(蓋章條款 4):橫線筆記紙樣式——
  `--nest-paper-note` 底 + 20px 行距 1px 橫線(background-image,分開寫)+
  左側兩顆活頁打孔(背景色圓)。
- **細項欄位**(糯糯逐項刪過重複的,只留事件行沒有的):
  1. 變化值 `value_after`(主體,墨綠灰 #515a4e,暗色轉 `--nest-ink-on-cream`)
  2. 引文槽=`escalation_reason`(只有待釐清事件有;斜體灰綠 #78806f,
     左緣蝴蝶橘 55% 細線)——真實資料沒有獨立引文欄位,打樣的引文槽
     對應到待釐清原因
  3. footer:完整時間 `M/D HH:MM` + 狀態(已歸檔 / 橘字待釐清)
  - 已刪(與事件行重複):摘要、主題、權威、影響
- **展開機制**:`expandedEventId` 純 UI state,一次一條,點同條收回;
  grid-template-rows 0fr↔1fr,.28s 抽屜曲線;事件行展開時解除兩行截斷;
  reduced-motion 全關。

## 改動檔案(VPS /srv/chatnest-next/frontend)

- `src/nestConsole.tsx`:+`fullTime()`、+`expandedEventId`/`toggleEventDetail`、
  事件列表項加 role=button/tabIndex/aria-expanded/onClick/onKeyDown+細項卡結構。
  api 與資料流零改動。完整檔=`s3-final/nestConsole.tsx`(md5 3a70a0c857d1216b03849786f4537093)
- `src/styles.css`:①時間線區塊整段替換(舊 6px 珠+1px 線 → 串珠版)
  ②檔尾 append S3 細項卡區塊。兩段合併記錄=`s3-final/s3-detail.css`
  (= 補丁腳本 `s3-final/s3patch.py` 的 NEW_TL+S3_BLOCK,腳本每個替換有 assert)
- `public/sw.js`:v151 → v152

## 備份與回滾

- `src/*.bak-s3-1787947618`(三件)+ `dist.prev-sw151-pres3/`
- 回滾:.bak 蓋回 → `npm run build`;急救 `rm -rf dist && cp -a dist.prev-sw151-pres3 dist`

## 驗證

- tsc 零錯(build 內含 tsc -b)、vite build 過、8790 已吐 v152
- 新 class(nest-event-detail-wrap/nest-ed-value/is-expanded)確認在 dist CSS,
  nest-ed-quote 在 dist JS
- 打樣頁亮暗×展開已 QA(`screenshots/qa-v4-{light,dark}.png`);最終以糯糯真機為準
- 本地記錄檔與 VPS 上線檔 md5 一致(同一份補丁腳本兩邊跑,結果比對)

## 打樣過程(4 版)

- v1:時間線改串珠(她給圖:•—•—「像被線串起來」,珠圖層在線上)+細項卡初版
- v2:細項欄位去重(她逐項刪:摘要/主題/權威/影響 = 與事件行重複)
- v3:線珠相碰版效果比較;細項卡改橫線筆記紙+打孔
- v4:定案=線不碰珠(背景色圈)+字色改淺墨綠灰(她指定「類似夜間模式那種的墨綠或灰綠」)

## 未做(刻意)

- `.nest-vol`/`.nest-back` 新擬態化:仍留給 S4
- S4:動效手感細調+全房走查(糯糯真機驗收)
