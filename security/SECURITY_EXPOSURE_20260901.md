# 對外暴露處置(2026-09-01)

依據:`/root/nest-memory/VPS_AUDIT_20260901.md` 第一節,糯糯裁定
**方案 A(Cloudflare Access 加登入)**,dash 另依 **C** 直接停用。

進度:**C 做完了;A 全部延後到第二批(糯糯 9/1 晚裁定)。**

## 決策紀錄

* **9/1 晚(審計時)**:對外暴露走方案 A,dash 另依 C 停用。
* **9/1 晚(本次施工後)**:A 延後。原因有兩層——
  ① 技術上卡住:VPS 上唯一那把 Cloudflare 憑證對 Zero Trust 只有讀權限(見下);
  ② 前提未定:Access 擋住工具通道後,MCP 客戶端要怎麼自己通過驗證,
     取決於 claude.ai 的 connector 支不支援自訂 header——那是糯糯的畫面。
  糯糯裁定:**先都不要動,等第二批一起處理**(含只保護 chat 也不做)。

  所以本次**沒有對任何網域套用 Access**,`mcp` / `voice` / `stackchan` / `hands` /
  `toy` / `chat` 維持原狀。下面的暴露實況即為**目前仍然存在的狀態**,
  不是已修好的紀錄。`access_apply.py` 備而不用。

---

## 一、dash → 已停用(方案 C,完成)

memory-dashboard 近 5 天只有掃描器在打,而 `dash.cn-dev.uk` 是**瀏覽器直接開就能讀**
我們的記憶(標題「我們的記憶 · Memories」)。

做了什麼(**只停服務,一個檔都沒刪**):

```
systemctl stop memory-dashboard
systemctl disable memory-dashboard
# /root/.cloudflared/config.yml 裡的 dash ingress 改成註解(原行保留)
systemctl restart cf-tunnel
```

驗證:

| 項目 | 之前 | 之後 |
|---|---|---|
| `GET https://dash.cn-dev.uk/` | **200(公開可讀)** | **404**(tunnel 已無此路由) |
| `:3000` 監聽 | 有 | 已無人 listen |
| `/root/memory-dashboard/` | — | 原封不動 |
| 其他 6 個網域 | — | 重啟後逐一實測仍正常 |

回滾:`config.yml` 取消註解 + `systemctl enable --now memory-dashboard` + 重啟 tunnel。
備份在 `/root/.cloudflared/config.yml.bak-dash-<epoch>`。
順帶回收約 9MB 記憶體。

---

## 二、Access(方案 A)→ 卡在憑證,程式已備妥

### 卡在哪(實測,不是猜)

VPS 上唯一的 Cloudflare 憑證是 `/root/.cloudflared/cert.pem` 內嵌的那把
API token(cloudflared login 產生的)。它對 Zero Trust **只有讀權限**:

```
list  access/apps            → success: true(目前 0 個)
POST  access/apps            → 1010 auth.forbidden
POST  access/service_tokens  → 1010 auth.forbidden
```

全機掃過沒有第二把(`.wrangler`、`.dev.vars`、各服務 env 都沒有;
`.cloudflared/*.json` 只有 tunnel secret,不是帳號 API token)。
另外規劃窗的沙箱**連不到 api.cloudflare.com 也連不到 cn-dev.uk**
(出口代理擋掉),所以也不能從這邊繞。

**需要糯糯做的**:開一把 API token 給我,權限只要

* Account → **Access: Apps and Policies** → Edit
* Account → **Access: Service Tokens** → Edit

或者她自己在 Zero Trust 後台建應用也行,設定內容見下。

### 已備妥:`access_apply.py`

```
export CF_API_TOKEN=<新 token>
python3 security/access_apply.py plan       # 先看要動什麼
python3 security/access_apply.py apply
python3 security/access_apply.py status
python3 security/access_apply.py rollback   # 一鍵拆掉
```

冪等(已存在就跳過),只動自己建的東西(靠 `[nest]` 名稱前綴認人)。

### 目前的暴露實況(實測)

| 網域 | 服務 | 現況 |
|---|---|---|
| `mcp.cn-dev.uk/mcp` | anchor-memory | **POST initialize → 200,零驗證**。search/store/**delete**_memory 都在這台 |
| `stackchan.cn-dev.uk/mcp` | StackChan | **200,零驗證**(能操作攝影機、喇叭、馬達) |
| `voice.cn-dev.uk/mcp` | Voice | **200,零驗證**;`/` 播放器頁 200 |
| `chat.cn-dev.uk` | 舊前端「AI 聊天」 | 200,公開 |
| `toy.cn-dev.uk` | Toy | 路徑帶密鑰(`/mcp-<KEY>`),根路徑 200 |
| `hands.cn-dev.uk` | Hands(exec_vps) | 未逐一驗;**是規劃窗唯一的 VPS 通道** |
| `dash.cn-dev.uk` | dashboard | 已停(見上) |

---

## 三、一個必須先問清楚的前提:MCP 客戶端送不送得出 header

Access 擋住未登入的請求時是回**登入頁的 302**。MCP 客戶端只會 POST JSON,
收到 302 就是斷線。要讓機器穿過 Access,唯一的辦法是 **Service Auth**:
客戶端每次請求帶

```
CF-Access-Client-Id:     <...>.access
CF-Access-Client-Secret: <...>
```

`access_apply.py` 會自動建 service token 並掛上這條政策。**但**這兩個 header
得由 claude.ai 那邊的 connector 設定送出——那是糯糯的畫面,我看不到。

所以在她確認之前,不能對工具通道套 Access,否則:

* `mcp`(anchor)斷 → 所有窗口的記憶工具失效
* `voice`/`stackchan`/`toy` 斷 → 聊天窗牧牧的手腳失效
* **`hands` 斷 → 規劃窗完全失聯,而且我沒有救援路徑**(沙箱連不到 Cloudflare API,
  也連不到 VPS,exec_vps 就是唯一的門)

因此 `access_apply.py` **預設把 hands 排除在外**,要加得明確傳 `--include-hands`。
施工順序也應該是:先 `chat`(純瀏覽器,壞了只影響瀏覽)→ 實測 →
再一個一個上工具通道 → **hands 放到最後,而且要糯糯在場**。

### 如果 connector 不支援自訂 header

那就走 toy 已經在用、而且**證實跟現有 connector 相容**的做法:把 MCP 掛到
帶密鑰的路徑(`/mcp-<KEY>`),再用 Access 把網域根路徑鎖起來(Access 應用可以
按路徑設,較具體的路徑優先)。效果一樣是「人要登入、機器走密鑰」,
代價是糯糯得在 claude.ai 逐一改 connector 的 URL。

兩條路都需要她動 connector 設定,差別只在改 header 還是改 URL。

---

## 四、還沒做(不在這批範圍)

* 收回 ufw 對公網放行的 3000 / 8080 / 8888(3000 已無人 listen)
* mumu-panel / mumu-chat 停用
* screenshot-worker 改按需啟動
* HTML 預覽路徑修復(在修好前**不可停用 `chatnest.service`**)
