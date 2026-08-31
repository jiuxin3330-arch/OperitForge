# 聊天照片瀏覽替換:Wren036/PhotoStack(sw v155)

2026-08-31|需求:糯糯(「完全替換聊天室傳送的照片瀏覽」)|純前端工具層,零盲測影響

## 行為變化
- 舊:聊天圖片=內嵌 `<img>`,點了開新分頁看原始檔(無 in-app 檢視)。
- 新:
  - 多圖訊息 → 微信式堆疊照片卡(PhotoStack:三張守恆探邊/跟手翻頁/快甩,右下 n/N 角標)
  - 單圖訊息 → 維持內嵌大縮圖
  - 點任何圖 → 新的聊天內檢視器(黑底、左右滑或方向鍵切換、Esc/點背景/輕點關閉、
    保留「原檔」出口開新分頁)。不循環翻頁,到邊即停(照微信行為)。
- 非圖片附件(PDF/檔案)行為不變。

## 實作
- vendor:`src/vendor/photostack/`(photo-stack.js/css 零改動;VENDOR.md 記來源與授權
  PolyForm Noncommercial 1.0.0——個人非商業使用,合規)
- `src/MessagePhotoStack.tsx`:React 掛載殼(生命週期+onTap 接檢視器)。
  註:App.tsx 內已有收藏盒的同名 PhotoStackCard(相簿堆疊),故取名 MessagePhotoStack。
- `src/chatPhotoViewer.ts`(+test):模組級 viewer store(open/step clamp/close/swipe 判定)
- `src/ChatPhotoViewer.tsx`:overlay(掛在 main.tsx root)
- App.tsx `MessageAttachments` 重寫(圖片/檔案分流);styles.css 附錄段;sw v155
- 契約修正:main.tsx `register("/sw.js?v=155")` 與 SHELL_CACHE 同步(pwa.test 契約,
  原本 v136/v154 不同步為既有漂移);visualPolish.test 日曆貼紙斷言更新為
  8/15 calendar-head-clip-fix 的現行貼底設計(測試陳舊,CSS 未動)。

## 驗證/回滾
- vitest 63 檔 297/297 全綠(新增 6 項 viewer store 測試);tsc+vite build 乾淨。
- 回滾:`src/*.bak-photostack-1788196493` + `dist.prev-sw154-prephotostack` 整份。
- 待糯糯真機走查:堆疊卡手感(峰形軌跡/快甩)、檢視器滑動、長圖表現;
  有手感單子就小步修(sw+1)。

## 追記:v156 修復 + v157 相簿微信化(同日深夜)

### sw v155 空白卡事故(糯糯真機回報:圖片完全沒顯示)
- 根因:vendor photo-stack.js 尾部含 `module.exports` 判斷,bundler(rolldown)
  將其包成 CJS 模組 → `module` 存在 → 走 `t.exports=r` 分支,
  `window.PhotoStack` 從未被設上 → React 殼拿不到建構子,靜默渲染空 div。
  (她那則訊息實傳多張圖,命中堆疊卡路徑。)
- 修復(sw v156):改吃 default export(CJS interop)+ `window.PhotoStack` 後備;
  建構子拿不到時 fallback 成普通縮圖列,**永不空白**。
  bundle 驗證:`.default ?? window.PhotoStack` 已入 dist;
  生產實拍(AI 視角截圖)確認堆疊卡渲染(1/4 角標可見)。
- 新合約測試 `messagePhotoStackUi.test.ts`:鎖 default import、fallback、
  聊天附件走 MessagePhotoStack+in-app 檢視器。
- 順帶對齊 pwa.test 契約:main.tsx `register("/sw.js?v=N")` 與 SHELL_CACHE 同步
  (原 v136/v154 為既有漂移)。

### v157 相簿堆疊微信化(糯糯裁定:換微信卡+展開固定兩列)
- 相簿(收藏>照片)堆疊卡本體換成 MessagePhotoStack(118×158,卡上最多疊 9 張,
  跟手翻頁,點單張直接進 collection-lightbox);標題列+chevron 獨立為展開按鈕。
- 展開網格 `.photo-stack-grid` 固定兩列(桌面也兩列);
  deal-in 動畫/展開結構/空堆疊資料夾佔位不動。coco 版三張扇形 covers 退役
  (CSS 保留供空狀態與 reduced-motion 契約)。
- 合約測試補充於 collectionPhotoStacks.test.ts;vitest 64 檔 301/301 全綠;
  回滾:`*.bak-photostack-1788196493`、`*.bak-gallerystack-1788198476`、
  `dist.prev-sw154-prephotostack`。
- 相簿手感待糯糯真機走查(截圖 worker 只能拍到聊天預設頁)。
