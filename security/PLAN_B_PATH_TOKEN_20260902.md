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
| ① 新增 token 路徑,舊路徑保留 | 工作窗 | ✅ | ✅ | ✅ | ⛔ 待指令 |
| ② claude.ai **新增**(非取代)connector | 糯糯 | ☐ | ☐ | ☐ | — |
| ③ 實測新路徑可用 | 工作窗 | ☐ | ☐ | ☐ | — |
| ④ 移除舊 connector | 糯糯 | ☐ | ☐ | ☐ | — |
| ⑤ 關閉舊路徑 | 工作窗 | ☐ | ☐ | ☐ | — |

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

| 服務 | 舊路徑 `/mcp` | 新路徑 `/mcp-<KEY>` | 錯的密鑰 | 尾斜線 |
|---|:--:|:--:|:--:|:--:|
| voice | 200 | 200 | 404 | — |
| stackchan | 200 | 200 | 404 | — |
| anchor(mcp) | 200 | 200 | 404 | 200 |

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

處置:`hands` 依鐵律仍保持「動它須明確指令」。**但風險等級應從『未知』上修為
『最高、且應優先於其他服務處理』**——建議在 voice/stackchan/anchor 走完 ②③④⑤
之前,先單獨把 hands 的步驟①(加新路徑、舊路徑保留)做掉,因為①是純加法、
不會鎖住任何人,而它換來的是把 root shell 從公開網際網路上藏起來。
