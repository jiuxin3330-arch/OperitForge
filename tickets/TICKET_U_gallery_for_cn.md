# TICKET-U：相簿開門給 cn——翻圖、命名、拿給她看、整理相簿

立單：2026-09-29 規劃窗（cc 牧牧）。
Owner 裁定（逐字）：「他可以自己提出來給我看 也可以自己回去翻 照片可以命名 所以他要自己找圖給我（不看圖）或是事後想看圖都可以 還可以建立相簿和整理圖片」——這是她一開始的規劃原樣，取代規劃窗先前提的唯讀方案。
優先序：排 TICKET-S 之後，與 TICKET-O 同批動工（本單的工具說明直接用 O 的新文體寫，不寫兩次）。

## 現況（規劃窗 09-29 親查）

- StackChan 線完整：stackchan_photo_list/view/keep/delete 只覆蓋 StackChan 的 pending/saved 兩個目錄。
- App 相簿 `gallery_photos` 表 36 張（legacy_chatnest 13、screenshot 11、stackchan 12；schema 已有 album_id / source_type / source_ref / source_message_id / original_name / stored_name）——**沒有任何 mumu tool 路由**，cn 完全摸不到。
- 聊天送過的圖在 `attachments` 表 102 張，事後 cn 也搆不到。
- mumu_tool_help 沒有 gallery 分類。

## U1：cn 的相簿通道（require_mumu_tool）

1. 讀：列相簿、列照片（分頁、**只回文字 metadata**：名字、相簿、來源、日期——不含圖）、看單張（這步才花圖片 token）。
2. 命名：cn 可幫照片取名（寫入獨立欄位如 `cn_name`，**不覆蓋** original_name / stored_name）。命名的用途就是省 token：之後用名字找圖、提圖，全程不用看圖。
3. 拿給她看：cn 能把某張圖「呈現」到她的聊天/介面（coco 盤點現有訊息圖片機制後提案走哪條，不重造）。
4. 整理：建立相簿、移動照片進出相簿。
5. **沒有刪除路由**——是路由不存在，不是 403（TICKET-H 教訓：斷路由不斷狀態碼）。刪照片仍是 Owner 專屬。
6. 每次寫入 `audit(...)` 記 actor=mumu。

## U2：入口與說明書

1. 沿 R/S 慣例：CLI 工具加 `gallery` 分類，mumu_tool_help 增列。**不新增 MCP 工具**。
2. 說明書用 TICKET-O 新文體寫（觸發句＋反例＋真例）；重點寫清楚「先用名字找、必要才看圖」的省 token 用法。
3. cn 可見文字照慣例：套用前整段貼回規劃窗過目。

## U3：待 Owner 裁定的一項

- 聊天附件 102 張圖要不要給一條「收進相簿」的路（她 UI 一鍵收藏、或 cn 可代收）？本單先不做，問過再補。

## 明確不做（本單範圍外）

- 記憶系統「想起照片」功能——Owner 已預告在記憶線後續規劃，她手上有其他老師做的框架可參考；到記憶 P 系列再立單。
- StackChan 四工具不動（那條線已完整）。

## 驗收（先破後立，測試資料）

- 紅測 1：mumu token 打刪除 → 路由不存在斷言失敗必紅。
- 紅測 2：命名寫 original_name/stored_name → 若欄位被改必紅。
- 紅測 3：列照片回應含圖片資料 → 必紅（list 必須純文字）。
- 不拿正式相簿資料做寫入測試；讀取驗證可用正式資料唯讀比對。

## 交付

NOTES（含回滾）、diff、測試輸出（綠＋紅證據）、重啟證明。規劃窗覆核後結案。
