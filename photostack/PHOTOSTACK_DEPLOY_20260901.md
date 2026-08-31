# PhotoStack 蓋章版部署報告

2026-09-01｜美化窗口｜sw v157 → **v158**｜狀態：**已上線，等糯糯真機驗收**

## 上線內容（試衣間 v5 蓋章規格，1:1 落地）

聊天端：
- 圖片搬出氣泡：照片流（`MessagePhotoFlow`）獨立掛在氣泡下方——糯糯的訊息渲染成氣泡的兄弟節點、牧牧的訊息放在透明殼內氣泡外；檔案列留在氣泡內
- 多圖＝堆疊卡＋「展開 N／收起」按鈕（A 案：貼卡內側垂直置中，展開後貼第一張卡內側；內側由幾何判定，視角翻轉安全）
- 展開＝一列 112×150 卡（比堆疊小）；起飛/收起按側歸位（頭尾幀＝靜態堆疊）；按鈕鎖位淡出無瞬移
- 單圖＝獨立縮圖（同樣在氣泡外）；n/N 角標全域關閉（`counter: false`）

相簿：
- 相冊並排一排兩本（`.photo-stack-list` 兩欄 grid）；月份/張數小字置中在卡底（12px/10.5px，無箭頭）
- 點底部文字＝飛散展開兩列佔整排，來源格讓位、旁鄰相冊 FLIP 推走
- 收起＝①第一張照片底部透明熱區（無任何遮擋按鈕）②兩列中間間隔條整條可點；替身（fixed）按側歸位飛回＋`scrollIntoView(nearest)`
- 改名/刪除收在展開區底部；空堆疊＝虛線資料夾佔位＋展開見空狀態

## 檔案

- 新增 `frontend/src/photoStackFly.ts`（姿態幾何＋FLIP 聯動，與 vendor `_apply` 同公式）
- 新增 `frontend/src/ChatPhotoStack.tsx`（聊天堆疊＋展開收起）
- 改 `MessagePhotoStack.tsx`（counter:false、新增 `apiRef` 暴露當前頁）
- 改 `App.tsx`（MessagePhotoFlow／MessageAttachments 拆分、AssistantMessageBody 掛流、
  history user 兄弟節點、PhotoStackCard 直式化、新 `GalleryStackFlyList`）
- 改 `styles.css`（尾段「相簿堆疊卡微信化」整段換成「PhotoStack 蓋章版」；舊 .photo-stack-summary/reveal 系 CSS 成為 dead code 暫留，後續清）
- `public/sw.js` + `main.tsx`：v157→v158 同步 bump
- 測試同步：`collectionPhotoStacks.test.ts` 前兩條改鎖蓋章規格；`messagePhotoStackUi.test.ts` 加「圖出氣泡＋無角標」鎖

補丁方式：`photostack/prod/apply_patches.py`（repo）精確替換 13 處，全中。

## 驗證

- vitest 全套 **64 檔 302 tests 全綠**（repo root 跑）
- `npm run build`（tsc＋vite）通過，直接進 dist＝部署；線上 `/` 200、`sw.js` 已見 v158
- dist bundle 抽查：cpf-area／album-fly-hotzone／album-fly-gap／message-photo-flow／photo-stack-caption／counter:!1 全部在

## 回滾點

- `frontend/src/*.bak-psv2-1788216370`（App.tsx／styles.css／MessagePhotoStack.tsx）＋ `public/sw.js.bak-psv2-1788216370`
- 新增檔直接刪即可；更早整包 `dist.prev-sw154-prephotostack`

## 待辦（下窗）

- 糯糯真機驗收（PWA 需重整讓 sw v158 接管）
- 驗收過後：清 dead CSS（.photo-stack-summary／deck／reveal／grid 系）；試衣間 mock 可下架
