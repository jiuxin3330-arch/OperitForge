# 交接單:照片瀏覽(PhotoStack)→ 美化窗口

2026-09-01 凌晨|CC 工作窗交接|狀態:功能上線但糯糯真機驗收「都不對」,
視覺/手感需求未對齊——**請先跟她對規格再動手**(打樣紀律:mock 試衣間+A/B 並排,只改她點名的)。

## 需求原意(糯糯)
用 Wren036/PhotoStack(微信式堆疊照片卡)「完全替換」照片瀏覽:
①聊天室訊息裡的圖片 ②相簿(收藏>照片)堆疊(coco 版她不喜歡)。
她提過「大展開從一列變成兩列」——我理解成展開網格欄數,可能理解錯,請重新確認她指的畫面。

## 現況(sw v157,全部已上線)
- 聊天:多圖訊息=PhotoStack 堆疊卡(預設 142×190,n/N 角標開);單圖=內嵌縮圖;
  點圖進新的 in-app 檢視器 ChatPhotoViewer(黑底/左右滑/Esc/「原檔」出口),不再開新分頁。
  堆疊卡渲染已生產實拍確認 OK。
- 相簿:堆疊卡本體換 MessagePhotoStack(118×158,最多疊9張,點單張進 collection-lightbox),
  標題+chevron 獨立成展開按鈕;展開網格固定兩列。**這部分她說不對,最可能是重做對象。**

## 檔案地圖(frontend/src/)
- vendor/photostack/(photo-stack.js/css 零改動;VENDOR.md 有授權說明,非商業個人用 OK)
- MessagePhotoStack.tsx(React 掛載殼,含尺寸參數與 fallback)
- chatPhotoViewer.ts(+test)/ ChatPhotoViewer.tsx(檢視器 store+overlay,掛在 main.tsx)
- App.tsx:MessageAttachments(聊天,~line 1265)、PhotoStackCard(相簿,~line 7030)
- styles.css 檔尾兩段:「PhotoStack 聊天照片瀏覽」「相簿堆疊卡微信化」

## 地雷(踩過的坑,別再踩)
1. **vendor CJS 陷阱**:photo-stack.js 尾部有 module.exports 判斷,vite/rolldown 會包成 CJS,
   `window.PhotoStack` 不會被設上——必須用 default import(現行寫法),別改回 global 取法。
   合約測試 messagePhotoStackUi.test.ts 鎖著。
2. sw 慣例:public/sw.js 的 SHELL_CACHE 與 main.tsx register("/sw.js?v=N") 必須同步 bump
   (pwa.test 會抓)。現為 v157。
3. 測試從 repo root 跑:`frontend/node_modules/.bin/vitest run --config frontend/vite.config.ts --dir frontend/src`
   (node 用 /srv/chatnest-next/.nodeenv);build:`cd frontend && npm run build`(tsc+vite,直接進 dist=部署)。
4. 相簿合約:collectionPhotoStacks.test.ts(coco 立的+我補的),改結構記得同步測試。

## 回滾點
- 聊天輪:src/*.bak-photostack-1788196493
- 相簿輪:src/App.tsx/styles.css .bak-gallerystack-1788198476
- 整包 dist:dist.prev-sw154-prephotostack(PhotoStack 之前的最後狀態)

## 建議起手式
先請糯糯指著畫面說哪裡不對(卡片大小?位置?角標?展開方式?檢視器樣式?),
拿 mock 出 A/B 讓她點名,再進 code。功能骨架(堆疊翻頁/檢視器/兩列網格)都在,
美化窗口大概率只需動 CSS 與參數(尺寸/peek/角標/佈局),邏輯不必重寫。
