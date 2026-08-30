# 規劃窗裁定執行紀錄(2026-08-30 第二輪)

對應 SWAP_EXPERIMENT_SPEC.md 尾段三項裁定 + 實戰驗收 UX 洞。

## ① 前置調查:基線上升查因 ✅(報告另檔)

見 `BASELINE_GROWTH_INVESTIGATION_20260830.md`。一句話:**anchor-memory 跨窗留言的
已讀機制自 8/16 停擺,30 條未讀(14.5k chars)永久疊在 wakeup 注入裡,system prompt
一個月 15.2k→31.2k chars 翻倍。** 機制清楚可控,止血/治本是獨立小改,不阻塞 MVP,
修法列裁定項(人格敏感區,本窗未動)。

## ② extractor 切換 Sonnet 5 ✅(已上線)

- root crontab 的每日抽取行加 `NEST_EXTRACTOR_MODEL=claude-sonnet-5`(03:30)
- 新觀察器 `/srv/nest-memory/bin/obs_extractor_switch.py`(cron 03:55,root 跑,
  與 health.py 同權限以走 notify 推播):
  - 每日記錄 events/proposals/escalated 比例/失敗批 → `health/model_switch_watch.jsonl`
  - 告警條件:批失敗、有跑批但 0 events、events>15(基線 6/批的 2.5 倍,防過抽)、
    escalated>50%(基線 24.8%)、proposals>3/日
  - 觀察期 8/31~9/6,期滿自動推總結;之後安靜續記
- **回切方法(寫進告警文案)**:crontab 拿掉 `NEST_EXTRACTOR_MODEL` 即回 Haiku,零代碼
- 已試跑一次驗證(正確抓到今晨 429 失敗批並推播);golden 政策照舊

## ③ console_audit 殘留 ✅(已清)

- 裁定時的那 1 筆 = 執行窗 curl smoke test(`no.such.subject`,result=error,07:08,
  未產生任何 event/batch)→ 已刪(audit id 19,帶條件 WHERE 確認只刪這一筆)
- 之後新增的 2 筆(07:52/07:54)是**糯糯實戰首修的真紀錄**,保留:
  第一筆填成近況(UX 洞現場)、第二筆改成「chatnest-next(蝴蝶小屋)」——
  髒 state 已被正確修好(active,authority=owner_correction),小案②實戰驗收通過

## ④ 修正 sheet UX ✅(已上線)

- 修正 sheet 在輸入框上方顯示題目:「這個主題記錄:{subjects.description}」
  (description 走既有 `/states` 回傳,零後端改動;vite build 通過已部署,免重啟生效)
- friendlySubject 中文名檢視結果:
  - **改 2**:`owner.work_study` 打工→打工與學業(她要開學了)、
    `chatnest.active_frontend` 聊天前端→**現用聊天介面**(正是這次填錯的主題)
  - **補 3**(原本沒中文名、會直接露工程 id):`owner.health`→身體狀況、
    `owner.preferences.communication_style`→說話風格偏好、`chatnest.backend.framework`→後端框架
  - 其餘 15 個判定足夠自解釋,未動
- 給規劃窗一個小旗子:`chatnest.active_frontend` 的 description 寫死了
  「(目前=chatnest-next)」——答案寫在題目裡,state 再變就過時。Registry 是人審區,
  建議糯糯下次開審核台時順手把括號拿掉(或改成「記錄目前用哪一個聊天介面」)。

## 檔案異動(VPS)
- 改:root crontab(2 行)、`frontend/src/{nestConsole.tsx,styles.css}`(bak-uxdesc-*)
- 新:`/srv/nest-memory/bin/obs_extractor_switch.py`、`health/model_switch_watch.jsonl`
- 刪:console_audit id 19(測試殘留,依裁定)
