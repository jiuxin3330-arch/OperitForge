# NOTES:跨窗口留言 read_by_ai 最終語意(裁定① 2026-08-31 定稿)

規劃窗裁定+糯糯執行細節補充(「標記掛系統注入時機,非依賴 cn 行為;想清楚多讀者
共用一個旗子的語意」)。本檔為正典;實作在
`version-bridge-app/app/memory_bridge.py`(`mark_injected_comments`)。

## 正典語意(一句話)

**`read_by_ai = 1` 表示「這條留言已注入過聊天窗口(牧牧本體)的 system prompt」。**
不是「某個 AI 讀過」,不是「模型自己說讀過」。

## 三個決定與理由

1. **掛誰的注入時機:只掛 version-bridge(聊天窗)的 wakeup 注入。**
   留言的功能是跨窗口交接給「下一個活著的牧牧」;聊天窗是常駐本體,是留言的
   正典收件人。標記由系統在注入完成後自動打(`build_system_prompt` 注入
   anchor_ctx 後 fire-and-forget `mark_injected_comments()`),完全不依賴模型
   行為——8/16 停擺的教訓就是依賴模型行為的標記必然漂移。

2. **CC/MCP 側(工作窗、規劃窗的 wakeup 呼叫):不標。**
   CC 是短命執行體,CC 看過≠本體看過;若 CC 標掉,聊天窗永遠看不到那條留言。
   多讀者共用一個 `read_by_ai` 旗子的語意由此收斂:旗子只描述「聊天窗收件」
   這一件事,其他讀者(CC/規劃窗/dashboard)都是旁觀者,讀不動旗子。
   MEMORY_GUIDE 同步改寫:「收到的留言只讀、絕不手動標已讀(注入送達時系統自動標)」。

3. **標記時機=注入後,不是 fetch 後。**
   `_call_wakeup` 把本輪注入的 comment_ids 存進 cache(`pending_ids`);
   `build_system_prompt` 真的把 anchor_ctx 放進 prompt 之後才觸發標記。
   fetch 進快取但沒被任何 turn 用到,不算送達。

## 失敗與冪等

- 標記失敗(anchor 掛了/超時):自吞、記 warning,留言保持未讀,下次注入再標。
  寧可多注入一輪,不可標了沒送達。
- 重複標記無害(UPDATE set 1,冪等)。
- `read_by_human` 完全不受本機制影響(人的已讀仍由 dashboard/人工管理)。

## 與裁定②③的銜接

- 裁定②(已執行 2026-08-31):8/23 前的 21 條未讀一次性批量標已讀
  (直接 UPDATE,與 anchor `mark_comments_read` 同語句)。剩餘 8/23 後的未讀
  將在下一個真實聊天 turn 的注入後被自動標掉。
- 裁定③(打樣中,**預設關閉**):`NEST_WAKEUP_COMMENT_CAP` 環境變數(0=關),
  開啟後每輪只注入最新 N 條、其餘折疊並提示條數;被折疊的舊留言不標已讀,
  隨已注入者被標掉而輪替上場(每輪消化 N 條,積壓會排隊排空,不會永久沉底)。
  樣張:`/root/nest-memory/PREVIEW_wakeup_cap5.txt`(cap=5:6,991 chars vs
  無 cap 9,242 chars)。**糯糯過目核可後**在 version-bridge.env 設
  `NEST_WAKEUP_COMMENT_CAP=5` 並重啟 bridge。

## 驗證紀錄(2026-08-31 00:0x)

- 管線測試:測試留言 `comment_d83e1496ecd0` 出現在注入清單 → `_call_mark` →
  復查消失 ✓(該測試留言已標,內容註明可忽略)
- bridge 重啟後 active;自動標記將於下一個真實 turn 首次實戰觸發,
  屆時 `journalctl -u chatnest-version-bridge | grep "auto-marked"` 可查證
