# 步驟 3 交付:離場結算(補刀 B)——「先結帳再搬家」

2026-08-31 02:00|規劃窗授權開工,當夜建成+實測通過。**SWAP_ENABLED=1 的前置條件已齊。**

## 機制(全現成,零新輪子)

`swap_runner.do_swap` 在打包/換窗**之前**插入 `exit_settlement()`:

1. **mirror catch-up**:跑一次 `mirror.py`(失敗不擋——最近 5 分鐘的訊息本來就在
   tail bootstrap 裡,不會丟)
2. **extractor 水位線迴圈**:重複跑 `extractor.py`(每批 60 條,上限 5 批)直到
   `no_new_messages`——未抽取的 raw 全部結帳入庫。extractor 冪等
   (input_hash/fingerprint),多跑無害;模型取自 root crontab 的
   `NEST_EXTRACTOR_MODEL`(單一事實來源,現=claude-sonnet-5)
3. **結不了帳→不搬家**:任一批失敗或跑滿上限仍未見底 → 本輪換窗中止
   (`swap_aborted_settlement`,推播),舊窗續用、下輪 cron 再試;
   真逼近硬上限時 CLI auto-compact 逃生門仍在
4. 結算全紀錄入 swap manifest(`settlement` 欄:批次/events/proposals/水位)

這就把補刀 B 指出的唯一真實退步(compact 會摘要而 Swap 硬丟中期段落)關掉了:
**預算外的中期段落在被切之前,值得記的先進 events 正典。**

## 配套修正
- `extractor.py`:`no_new_messages`/`duplicate_batch` 早退路徑補印 stdout JSON
  (呼叫方靠 stdout 判定;首測抓到的缺口)
- `swap_runner.py` 加 `--settle-only`(手動結帳/測試,不換窗)

## 實測(2026-08-31 01:58~02:00)

1. `--settle-only`:mirror ok → **batch 28 committed,4 events——Sonnet 5 生產首抽**
   (歸櫃正確:penpals/花園/作息/學業,authority 分明)→ 第二輪 `no_new_messages` 收口 ✓
2. 拋棄式 conv 完整換窗(錨點「深夜鯛魚燒車隊的路線圖」):
   結算(batch 29)→ 換窗 `4004588a→0ea5be22` → probe 覆述話題正確 → problems=[] ✓
   (測試 conv 已刪)

## 現況與下一步

- 生產仍 **shadow**;轉正=cron 加 `SWAP_ENABLED=1`(前置條件已齊,等規劃窗指令)
- 實驗順序:步驟 4(Session 跟隨整合清單——自動喚醒/自主時段/花園 runner/
  cc-usage/小紙條消費鏈逐項驗證)→ 步驟 5(連續 Swap regression+continuity probe
  進 golden)→ 步驟 6(糯糯盲測 2 週)
- 觀察器今晚 03:30/03:55 照常盯 Sonnet(結算已提前抽掉今天的量,cron 屆時應
  no_new_messages——這是正常現象不是故障)

## 檔案
- 改:`/root/chatnest-next/scripts/swap_runner.py`(exit_settlement,bak-step3-*)、
  `/srv/nest-memory/bin/extractor.py`(早退印 stdout)
- manifest 樣本:`/root/chatnest-next/data/swap_manifests/swap_20260831_020006.json`
