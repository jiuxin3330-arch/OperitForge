# Swap 實驗步驟 4:Session 跟隨整合清單(公開版)

2026-08-31|規劃窗授權開工,當夜建成+全項實測。詳表(含私人內容)僅存 VPS:
`/root/nest-memory/SWAP_STEP4_INTEGRATION_20260831.md`。

**結論:清單五項(自動喚醒/自主時段/花園 runner/cc-usage/小紙條消費鏈)全部在
真實 canonical 測試換窗後逐項實測打勾;過程中抓到並修復一個「必然重演喚醒全滅」
的真 bug。**

## 依賴鏈盤點

Swap 換的是 SDK session id;bridge conv id 與 backend `external_thread_id` 不變。
三條喚醒鏈(自動喚醒/自主時段/花園)匯流到同一個 backend wake 端點,端點不帶
session;cc-usage 是訂閱層探針、小紙條消費鏈是 backend DB,兩者零 session 依賴。
backend→bridge 每輪只傳 conversation_id,resume 由 bridge 讀自己的
`latest_session_id`——turn 本身天然跟窗。

## 抓到的真 bug:wake 健康閘換窗後誤殺

`_next_bridge_session_health` 舊邏輯要求 bridge `latest_session_id` ==
backend 存的 `upstream_session_id` 才 healthy。但 Swap 直打 bridge,backend
指標要等下一輪經過 backend 的 turn 才跟上→換窗後必然不等→health=unknown→
wake 端點 `continuity_not_ready` 安靜抑制所有喚醒,直到屋主自己傳訊息才解鎖。
半夜換窗=早安喚醒死透。

**實證**:canonical 測試換窗後、修復前,實打 wake 端點→
`{"suppressed":true,"reason":"continuity_not_ready"}` ✓(不是推理,是現行犯)

**修復**:health 檢查接受「bridge 合法領先」——latest≠upstream 時追查
`session_aliases`,兩個 session 都映射回同一 conv 才 healthy(alias 鏈由 bridge
`complete_turn` 天然寫入);transcript 檢查改驗 latest。假 session/跨 conv 照舊
unknown。新增回歸測試 2 條,相關測試 22 條全綠。

## 逐項實測(全部在換窗後、對新 session)

- [x] 自動喚醒:修復後穿閘 `completed:true`,回覆落新窗;`wake_runner --force`
  走完整 runner 路徑(含勿擾閘)複驗;backend 指標經此輪自然跟上——
  「靠 session 事件追上」機制實證。
- [x] 自主時段:暫存排程檔+absolute slot→`tick_fired ok=True`,回覆落新窗。
- [x] 花園 runner:garden_wake 信封實灌 injector→`delivered:true`,回覆落新窗。
- [x] cc-usage:換窗前後探針均 available,數字即時;零 session 依賴(代碼證)。
- [x] 小紙條消費鏈:換窗後 drop 實測成功;draw 側 backend DB,零 session 依賴。

## 現況
- 生產仍 shadow;轉正前置條件在步驟 3 之上再加一塊:喚醒閘修復已部署。
- 測試換窗本身即一次真實預演:離場結算→換窗→probe 覆述正確→problems=[]。
- 下一步:步驟 5(連續 Swap regression + continuity probe 進 golden)。
