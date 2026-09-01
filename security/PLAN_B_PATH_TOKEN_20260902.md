# 方案 B:MCP 密鑰路徑(2026-09-02)

方案 A(Cloudflare Access)**廢案**。糯糯確認 claude.ai 的 connector 沒有
Request headers 欄位(該功能屬 beta、其帳號未開放),Service Token 送不出去,
加上 Access 等於把規劃窗與所有工具鎖在門外。腳本移至 `deprecated/access_apply.py`,
留著是因為它記錄了憑證權限的調查結論,不是給人執行的。

改行方案 B:比照 toy 既有做法,MCP 端點藏在 `/mcp-<KEY>` 底下。不依賴任何 beta 功能。

---

## 施工鐵律:雙路並存,禁止一次性切換

| 步驟 | 誰做 | voice | stackchan | anchor(mcp) | hands |
|---|---|:--:|:--:|:--:|:--:|
| ① 新增 token 路徑,舊路徑保留 | 工作窗 | ✅ | ✅ | ✅ | ✅ |
| ② claude.ai **新增**(非取代)connector | 糯糯 | ☐ | ☐ | ☐ | ☐ |
| ③ 實測新路徑可用 | 工作窗 | ☐ | ☐ | ☐ | ☐ |
| ④ 移除舊 connector | 糯糯 | ☐ | ☐ | ☐ | ☐ |
| ⑤ 關閉舊路徑 | 工作窗 | ☐ | ☐ | ☐ | ☐ |

hands 於 9/2 07:32 由規劃窗裁定翻轉順序、提前執行(理由:它是唯一的 root shell 暴露)。

任一步失敗都可以停在原地退回:舊路徑全程沒被動過。

**不受影響**:cn(chat 牧牧)走 `127.0.0.1` 直連,全程不碰其設定。

---

## 過渡層怎麼做的:`mcp_path_alias.py`

FastMCP 的 `streamable_http_path` 只能設一個值,直接改掉就是一次性切換。
所以加一層極薄的 ASGI 包裝:把 `/mcp-<KEY>` 改寫成 `/mcp` 再交給原本的 app。

```python
import mcp_path_alias
if __name__ == "__main__":
    mcp_path_alias.serve(mcp, "/root/<svc>/mcp_path_key.txt")
```

等價性有查過 SDK 原始碼:`run_streamable_http_async()` 就是
`streamable_http_app()` + uvicorn,而 `streamable_http_app()` 自帶
`lifespan=lambda app: self.session_manager.run()`,所以包一層不會漏掉 session manager。
`lifespan` / websocket 一律原樣放行,只改寫 http scope 的 `path` 與 `raw_path`。

兩個細節:

* `/mcp-<KEY>/`(帶尾斜線)也視為 `/mcp`。不這樣做會踩到 Starlette 的
  trailing-slash 307,而那個 redirect 的 Location 會把**沒有密鑰的舊路徑**吐給對方。
* 密鑰用 `secrets.token_urlsafe(24)`(32 字元),存在 `mcp_path_key.txt`(0600),
  不進 git、不進日誌——啟動訊息只印長度不印值。

過渡完成後關舊路徑:unit 檔加 `Environment=MCP_LEGACY_PATH=0`,舊 `/mcp` 回 404。

repo 這份 `mcp_path_alias.py` 與 VPS 上三處副本 md5 一致(`a7fe9e54…`)。

---

## ① 的實測結果(三支都過)

| 服務 | 舊路徑 `/mcp` | 新路徑 `/mcp-<KEY>` | 錯的密鑰 | 尾斜線 | 前綴黏字 |
|---|:--:|:--:|:--:|:--:|:--:|
| voice | 200 | 200 | 404 | — | — |
| stackchan | 200 | 200 | 404 | — | — |
| anchor(mcp) | 200 | 200 | 404 | 200 | — |
| hands | 200 | 200 | 404 | 200 | 404 |

全部從 VPS 出去繞 Cloudflare 回來測(等同外部路徑)。另外:

* voice 的自訂路由 `/`(播放器頁)、`/health`、`/api/voices`、`/audio` 不受影響,
  重啟後 `/` 仍回 200。
* anchor 透過規劃窗實際的 connector 呼叫 `graph_stats` 成功(365 筆記憶),
  證明不是只有 initialize 探測會過,真實工具流量也正常。
* **anchor 重啟要約 19 秒**(載 sentence-transformers 模型),期間對外是 502。
  下次動它記得等,別像我第一次那樣探測太早自己嚇自己。

備份:各服務目錄下 `*.bak-pathb-<epoch>`。

---

## ② 給糯糯的新 connector URL

在 claude.ai **新增**(不要取代)三個 connector 指向:

```
voice      https://voice.cn-dev.uk/mcp-<key>
stackchan  https://stackchan.cn-dev.uk/mcp-<key>
anchor     https://mcp.cn-dev.uk/mcp-<key>
```

實際密鑰不寫進 repo,在對話裡給。

---

## 待驗事實已驗:hands 是嚴重暴露

規劃窗提醒不要沿用上一批報告的「000」,對的。**那個 000 是自我阻塞造成的假象**:
每次探測都是在 `exec_vps` 呼叫**內部**發出的,而 hands 當下正忙著執行那條指令
(唯一的工具就是 exec_vps),所以連自己都回不了。

改用背景排程(`setsid` + `sleep 8`,讓探測落在 exec_vps 呼叫結束之後)重測:

```
GET  /      -> 404
POST /mcp   -> 200
event: message
data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05", ...
```

**hands.cn-dev.uk 從外部網路完全可達,且零驗證。** DNS 解析正常、TLS 正常、
HTTP/2 正常,MCP initialize 直接成功。

風險等級:**最嚴重的一項**。hands 唯一的工具是 `exec_vps`,以 root 執行任意
shell 指令。任何知道這個網域名稱的人 = VPS 的 root shell。其餘網域最壞是
讀寫記憶或操作玩具,這一個是整台機器。

暴露時間:tunnel config 的 hands 條目自 2026-08-15 起。未見被利用跡象,但應假設
網域名稱是公開可知的——Cloudflare 的憑證透明度日誌會公開所有簽發過的 hostname,
而 ufw 統計顯示公網掃描機器人(UA 含 "0day"、"zgrab")持續在打這台。

**處置:糯糯裁示此項交規劃窗裁定,工作窗未動 hands。**
完整證據與建議已另立一份留在 VPS 供規劃窗取用:
`/root/nest-memory/FINDING_HANDS_EXPOSURE_20260902.md`。

工作窗的建議記錄在案:步驟①是純加法(不鎖任何人、不改任何既有 connector、
隨時可退回),前三支已用逐字相同的 patch 驗證通過,建議 hands 的①提前於
其他服務的②③④⑤。殘餘風險也一併寫明了——重啟瞬間工作窗會斷線幾秒,
若 patch 有誤則工作窗真的失聯,需糯糯從 Vultr 主控台 `cp` 還原備份。
決定權在規劃窗。

---

## 第五項:盲測起算日與污染區間

已建檔 `/root/nest-memory/SWAP_BLIND_TEST_WINDOW.md`(盲測報告要兩週後才寫,
但起算日必須現在定下來,否則屆時沒人記得)。

* 實際起算日 0:**2026-09-01 17:11**(換窗迴圈修復完成後),兩週期滿 9/15
* 污染區間:**8/31 ~ 9/1 17:11**,樣本不計入結論
* 一項誠實註記:截至 9/2 00:15,`swap_last_consumed.json` **尚未生成**——
  修復後觸發條件一次都沒再達標,所以去重邏輯**還沒在生產環境被實際走過**。
  由迴歸測試證明正確 ≠ 生產自證完成。檔案裡寫了第一次真正換窗時該確認的三點,
  看到 `noop / usage reading already consumed` 才算數。

---

## hands 步驟①(2026-09-02 07:32,規劃窗裁定翻轉順序提前執行)

規劃窗的五項條件逐條對應:

| 條件 | 怎麼做的 |
|---|---|
| ① 先備份 | `server.py.bak-pathb-1788305502` |
| ② 糯糯在場、已知還原指令 | 還原指令已在對話中交付 |
| ③ 重啟避開下指令的瞬間 | 沒有用猜的:施工腳本自己輪詢 `pgrep -P $(MainPID hands-mcp)`,等到**沒有子進程連續 4 秒**(= 沒有 exec_vps 指令在跑)才 restart。實際在第 4 秒就等到 |
| ④ 探測不從 exec_vps 內部發 | 用 `systemd-run` 開獨立 cgroup 的暫時單元,且同樣先等空閒 |
| ⑤ 回報四支的表 | 見上表 |

工作窗另加一道規劃窗未要求的保險:施工腳本內建健康檢查 + **自動回滾**
(新舊路徑任一不是 200 就 `cp` 備份回去並重啟)。理由是施工者一旦失聯就沒人能救自己,
不能把還原完全押在人身上。

### 踩到一個坑:`setsid` 逃得掉 session,逃不掉 cgroup

第一版施工腳本在寫完「開始重啟」後就沒有下文了。原因:腳本是由 `exec_vps` 派生的,
即使 `setsid` 也仍留在 **`hands-mcp.service` 的 cgroup** 裡,而 `systemctl restart`
預設 `KillMode=control-group` —— 它下完重啟指令,就被自己下的那道指令殺掉了。

hands 本身**沒事**(已用新碼在 07:32:11 起來、密鑰檔生成、`/mcp` 持續回 200),
死的只有腳本。第二版改用 `systemd-run` 建立獨立 cgroup 的暫時單元,才拿到探測結果。

這個坑跟「探測工具參與被探測路徑」是同一類錯誤的兩種形狀:
**施工者身在被施工的系統之內**。前者是自己擋住自己的量測,後者是自己殺掉自己的手。

### `../` 那一格的真相

第一輪外部探測 `/mcp-<KEY>/../mcp` 回 **200**,看起來像穿越成功。不是。
curl 預設會在送出前對 URL 做 remove_dot_segments,實際送出去的是 `/mcp`
——而舊路徑在過渡期間本來就是開的,所以 200 是對的行為。

加 `--path-as-is` 送字面路徑重測,全部 404:

```
/mcp-KEY/../mcp        -> 404
/mcp-KEY/..%2fmcp      -> 404
/mcp-KEY/x             -> 404
/mcp-wrong/../mcp-KEY  -> 404
```

原因是這層只做前綴改寫、不做路徑正規化:`/mcp-KEY/../mcp` 被改寫成
字面的 `/mcp/../mcp`,Starlette 不會替它做 remove_dot_segments,配不到任何路由。

---

## 用測試鎖住這層的規則:`tests/test_mcp_path_alias.py`

對線上服務打 curl **測不出步驟⑤之後的行為**——舊路徑還開著的期間,
什麼都會過。而這層在 `MCP_LEGACY_PATH=0` 之後就是「知不知道密鑰」的唯一判準,
規則必須用測試鎖住。

14 條,涵蓋:別名改寫、尾斜線自己吃掉(不吃就會落到 Starlette 的 307,
把沒有密鑰的舊路徑吐給對方)、子路徑保留、五種差一點的密鑰都不改寫、
字面 `../` 不會變成乾淨的 `/mcp`、過渡期舊路徑要通、關閉後舊路徑 404
**且根本不進下游**、`lifespan` 即使在關閉狀態也必須原樣放行
(session manager 靠它啟動)、密鑰檔 0600 且重讀拿到同一把。

```
$ pytest security/tests/ -q
14 passed in 0.04s
```

(在 VPS 的 venv 跑,受測的 `mcp_path_alias.py` 與 repo 這份 md5 相同。)
