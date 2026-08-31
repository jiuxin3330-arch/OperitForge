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
