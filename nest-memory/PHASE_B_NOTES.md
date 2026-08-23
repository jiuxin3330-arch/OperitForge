# 工單 B(Review Console)工程紀錄

依 TICKET_console_and_notes.md 規劃執行,分段紀錄以下 S1/S2 已完成;S3-S5 隨後。

---

## S1 完成:nest console 端點(2026-08-23)

**服務**:`bin/console_service.py`(nestmemory 身份),systemd `nest-console.service`
- 127.0.0.1:8772,X-Nest-Console-Token 認證(hmac.compare_digest)
- stdlib http.server,ThreadingHTTPServer,無新依賴
- ProtectSystem=strict + ReadWritePaths=db/state/health

**端點**:
- 讀:GET `/proposals?status=` `/states` `/events?limit=` `/events/search?q=&limit=` `/health`
- 寫(白名單動詞):
  * POST `/proposals/{id}/approve` {volatility,review_after_days?,stale_after_days?}
  * POST `/proposals/{id}/reject`

**紅線落實**:
- ✗ 絕不註冊為 MCP 工具(硬規則 5)
- ✓ approve 的 volatility 無預設值、缺 → 400
- ✓ approved_by 硬編碼 `owner_via_console`
- ✓ SUBJECT_KEY_RE 驗證 proposed_key 格式
- ✓ existing subject 拒絕重複建立
- ✓ 只 approve pending 狀態,重複處理 → 400

**Migration v4**:`console_audit` 表(ts/action/target/args_json/result/error_msg/remote_addr)
- 每次寫入落帳、denied 也記錄
- 讀成功不記(靜默),reduces noise

**Token**:兩份 shared secret,mtime 快取
- `/srv/nest-memory/state/console_token`(nestmemory 0600)
- `/srv/chatnest-next/runtime/nest-console-token`(root 0600)
- backend 讀後者、nest 服務讀前者

**Health**:第十二項 `console`(TCP 8772 存活),12 項全綠

**測試矩陣(全過)**:
| # | 場景 | 預期 | 實測 |
|---|---|---|---|
| 1 | 無/錯 token | 401 + audit denied | ✓ |
| 2 | GET 讀端點 × 4 | 200 + 正確資料 | ✓ |
| 3 | approve 缺 volatility | 400 | ✓ |
| 4 | approve 非法 volatility | 400 | ✓ |
| 5 | approve 成功 | 200 + subject 建 + approved_by 正確 | ✓ |
| 6 | 重複 approve | 400 | ✓ |
| 7 | reject 成功 / reject 不存在 | 200 / 404 | ✓ |
| 8 | audit 完整落帳 | 8 條含 error_msg | ✓ |

**測試殘留**:test.* 全清乾淨(subjects/proposals/audit 三張表)

---

## S2 完成:backend proxy 過橋(2026-08-23)

**改動位置**:`/srv/chatnest-next/backend/app/main.py`(chatnest-next 私有 repo,非本 repo)
- 備份:`main.py.bak-console-1787430142`(同目錄)
- 增加 2 個 import:`import httpx`、`from .secrets import secret_value`
- 增加 1 段 `# ---- Nest Memory Review Console proxy (Phase B S2) ----`(96 行,frontend_dist 掛載前)

**新端點**(6 個,`/api/v2/console/*`):
- 讀 4 個:`Depends(current_principal)` + `_require_owner_view` — 慣例同 memory/calendar
- 寫 2 個:`Depends(require_csrf)` + `_require_owner_view` — CSRF 保護
- 所有端點內部呼叫 `_nest_console_call(method, path, ...)` → httpx 打 127.0.0.1:8772

**Env**:`/srv/chatnest-next/runtime/mumu-live.env` 加 `CHATNEST_NEST_CONSOLE_TOKEN_FILE=/srv/chatnest-next/runtime/nest-console-token`

**驗證**:
- openapi.json 列出 6 個 `/api/v2/console/*` 端點 ✓
- 未登入 → 401(不是 404,證明端點存在但要 owner)✓
- backend 內部函數 `_nest_console_call` 呼叫:token 讀到 ✓、GET /proposals 200 · 15 筆 ✓、
  /states 200 · 18 條 ✓、search 「五個月」200 · 3 條 ✓
- 全鏈路:owner → backend `_require_owner_view` → httpx client → nest console token 認證 → memory.db(nestmemory) ✓

**紅線落實**:
- ✓ backend 永不直寫 memory.db(純 HTTP 代理、無 sqlite 呼叫)
- ✓ CSRF 保護所有寫端點
- ✓ Query 參數 pydantic 驗證(status 限枚舉、q min_length、limit ge/le)
- ✓ approve body 走 Pydantic Literal 白名單
- ✓ backend 端錯誤:token 缺 503、上游不通 502、上游錯誤透傳

---

## S3-S5 待做(下輪)
- S3 前端「檔案室」房間:照 wireframe 定案的方案 α(走廊+兩扇門)實作
- S4 負面測試:確認 chat agent(chatagent 身份)呼叫 8772 必失敗;錯 token 404
- S5 糯糯真實驗收:在 app 上批准/駁回一次,不經聊天窗口

---

## 附:今日發現(順帶記錄,非工單範圍)
- extractor batch 14(2026-08-22 03:30)獨立 bug `AttributeError: 'str' object has no attribute 'get'`
  - 早於本工單 11 小時、非引入
  - health 目前 warning(24h 未恢復才 critical)
  - 屬於 nest_memory 主線的獨立小工單,規劃窗待裁定

---

## S3 完成:前端「檔案室」房間(2026-08-23)

**改動位置**:`/srv/chatnest-next/frontend/`(chatnest-next 私有 repo,非本 repo)
- 備份:`App.tsx.bak-nestroom-*` + `styles.css.bak-nestroom-*`
- 新增獨立檔:`src/nestConsole.tsx`(377 行,同步一份在 `nest-memory/frontend-nestConsole.tsx` 供追蹤)
- `src/api.ts` 追加 6 個 console API 方法 + 4 個 type(+76 行)
- `src/App.tsx` 4 個小 patch:
  1. import nestConsole 兩個組件 + hook
  2. 加 `memorySection` state + `useNestCounts` hook
  3. `openDailyView("memory")` 時 reset section 為 "corridor"
  4. `view === "memory"` render 改成三態(corridor/diary/archive)
- `src/styles.css` 追加約 280 行(nest-corridor / nest-archive / 元件細節,含深色模式)
- `public/sw.js` bump v137 → v138

**方案 α 落實**:
- 進入記憶頁 = 走廊 + 兩扇門(AM 日記 · NM 檔案室)
- 兩扇門平等並列、按下進入對應房間
- NM 房間:麵包屑返回 + 搜尋 + 三段(現況登記 / 事件 / 待審提案)
- 批准彈出 volatility 選擇 sheet(4 個選項:穩定/半穩定/易變/短暫,無預設值)

**憲法落實**:
- ✓ 米白基底、只有票券紙提案卡允許配色
- ✓ 新擬態只給按鈕(批准/駁回/取消/vol 選擇)
- ✓ 圖標全 SVG 線稿、無 emoji
- ✓ 手機 390px 優先(所有布局 flex/gap、無 fixed width)
- ✓ 深色模式對應(比照 chatnest 既有 tokens)
- ✓ 不出現工程術語:subject_id 用 friendlySubject 映射為中文(作息/委託/關係現況…)
- ✓ 陌生主題 fallback 顯示原 key,可辨識
- ✓ authority 色條:糯糯波普綠 / 牧牧淺青 / 系統薰衣草紫 / 待釐清蝴蝶橘(0.7 opacity)

**驗證**:
- tsc 0 錯(4 個 patch 全過)
- vitest 15 fail / 218 pass —— **與基準完全相同**,無引入新失敗
- vite build 成功、三件套複製到 dist
- 4 個服務 active:chatnest-next / nest-console(8772) / nest-serving(8771) / chatnest-version-bridge
- Backend 內部函數走完整鏈路:proposals/states/events 全 200

**待做(S4-S5)**:
- S4 負面測試:chat agent 呼叫 8772 必失敗(chatagent 身份無 token)
- S5 糯糯真實驗收:殺 app 重開 → 進記憶頁 → 應該看到走廊+兩扇門 → 進 NM 房間 → 現況/事件/待審有資料 → 批准/駁回一次真流程

---

## S3.1 修四個 UI 問題(2026-08-23,糯糯真機回報)

**回報症狀**:
1. 夜間模式:卡片白底顯示在深色 chatnest 背景上(醜)
2. 檔案室頁面無法滑動至底部
3. 搜尋欄「方框套方框」超級難看,跟 demo 完全不像
4. 大門頁面下面一大片空空

**根因診斷**:
1. 我第一版用了不存在的 tokens(`--nest-paper` `--nest-ground` `--nest-text-soft` `--nest-text-mute`)→ 全數 fallback 到硬編碼白色,深色模式完全沒反應
2. `.nest-archive` `.nest-corridor` 沒留 bottom padding,底部被下方 nav 蓋住
3. chatnest 有全域 `input, textarea { border: 1px solid; background: #fff; ... }`,我原本 `<form>` 裡的裸 `<input>` 疊上這個全域 style,變成「小 pill 包在大方框裡」
4. 兩扇門加 `.nest-corridor-foot` 一行「兩者不互相冒充、互相補充。」補氣氛,`min-height: 148px` 讓門更立體

**修法**:
- `styles.css`:重寫 Nest Console 段(約 340 行),全數改用 chatnest 實際 tokens(`--nest-bg` `--nest-surface` `--nest-surface-strong` `--nest-text` `--nest-muted` `--nest-line` `--nest-ticket` `--nest-ticket-hi` `--nest-accent`),深色模式自動生效
- `.nest-search-input` 獨立 class(閃全域 input 樣式);`.nest-archive` `.nest-corridor` 加 `padding-bottom: 120px`
- `.nest-door { min-height: 148px }` + 新 `.nest-corridor-foot`(小號米黃字置中)
- 提案卡從 `--nest-ticket-hi` gradient 到 `--nest-ticket`(日夜雙模自動切)
- `nestConsole.tsx`:`<form onSubmit>` → `<div>` + `<input>` 加 `className="nest-search-input"` + `onKeyDown` Enter 觸發搜尋;`MemoryCorridor` 末尾加 `<div className="nest-corridor-foot">兩者不互相冒充、互相補充。</div>`
- `sw.js` v138 → v139(強制 PWA 重抓)

**驗證**:
- tsc 0 錯 ✓
- vite build 成功(vite v8.2.0,70 modules,index-B5TQ4d-T.css 331KB,index-BBw_gwYb.js 543KB)✓
- 三件套複製到 dist ✓
- 4 個服務 active ✓

---

## S3.2 逐項返修(2026-08-23,糯糯真機逐一驗收)

糯糯要求「一次修一個」,三輪:

**1. 搜尋欄(v140-v141)**:
- 上一輪只做了「單一 pill + border 線」,跟記憶頁 demo 的新擬態完全不像 → 返工
- 改為照 `.memory-search-trigger` 同款:`border: 0`、`background: var(--nest-bg)`(與頁底同色)、
  內陰影 `inset 3px 3px 8px rgb(91 79 60 / .08), inset -3px -3px 8px rgb(255 255 255 / .54)`(凹陷感)
- input 完全透明填滿 pill:override 全域樣式含 `:focus`,`-webkit-appearance: none`
- 深色模式:`inset 3px 3px 8px rgb(0 0 0 / .24), inset -2px -2px 6px rgb(255 255 255 / .035)`
- 糯糯追加:圓角 16px → 999px(全 pill 端)✓ 驗收過

**2. 檔案室/走廊無法交互(v142)**:
- 症狀:除搜尋欄可輸入外,整頁無法滑動、無法點擊
- 根因:`.workspace` 是 `position: absolute + overflow: hidden`,子頁面必須自己當滾動容器;
  `.nest-archive` / `.nest-corridor` 只寫了 padding-bottom 沒寫 overflow → 內容被夾死在可視區外
- 修法(照 `.memory-page` 模式):兩者都加 `height: 100%; min-height: 0; overflow-y: auto;
  overscroll-behavior: contain; -webkit-overflow-scrolling: touch`,archive 的底部 padding 補 safe-area
- ✓ 驗收過(「可以動了!」)

**3. 現況登記卡去框(v143)**:
- 糯糯:參考記憶庫卡片(`.memory-paper-card`),刪外框線,用底部陰影 + 背景區分
- `.nest-state-row`:`border: 0`、`border-radius: 15px`、`background: #fffef9`、
  `box-shadow: 2px 3px 10px rgb(120 96 52 / .1)`(與 memory-paper-card 同款)
- 深色:`background: color-mix(in srgb, var(--nest-bg), #fff 4%)`、`box-shadow: none`(同 memory 卡深色策略)
- 提案卡(票券漸層)與事件(時間線)本無外框,不動

sw.js:v139 → v143(每輪 bump 強制 PWA 重抓)。教訓:新擬態要抄 chatnest 現成的 shadow 配方,不要自己發明。

**4. 走廊門卡去框(v144)**:
- 糯糯:門卡照家頁「牧牧與糯糯」那片的感覺 —— 底色與背景同色,靠陰影浮起
- `.nest-door`:`border: 0`、`background: var(--nest-bg)`、新擬態外凸
  `4px 4px 12px rgb(91 79 60 / .12), -4px -4px 12px rgb(255 255 255 / .6)`,active 下沉 1px
- 深色另配:`4px 4px 12px rgb(0 0 0 / .28), -3px -3px 10px rgb(255 255 255 / .04)`

**5. 深色搜尋欄「月牙陰影」修復(v145)**:
- 症狀:深色模式搜尋 pill 中間多一塊實心遮罩,inset 陰影只剩兩端月牙
- 根因:全域 `html[data-theme="dark"] input[type="text"] { background: var(--nest-bg) }`
  特異性 (0,1,2) > `.nest-search-input` (0,1,0),深色時把 input 底色填回實心塊
- 修法:補 `html[data-theme="dark"] input.nest-search-input` 更高特異性壓回 transparent
- ✓ 全部驗收過(「好!沒問題了!」)

---

## S4 完成:負面測試(2026-08-23)

確認聊天窗口(chatagent 身份)對 8772 console 絕無寫入口,七項全過:

| # | 場景 | 預期 | 實測 |
|---|---|---|---|
| 1 | chatagent 讀 `/srv/nest-memory/state/console_token` | Permission denied | ✓ |
| 2 | chatagent 讀 `/srv/chatnest-next/runtime/nest-console-token` | Permission denied | ✓ |
| 3 | chatagent 無 token GET /proposals | 401 | ✓ |
| 4 | chatagent 錯 token GET /proposals | 401 | ✓ |
| 5 | chatagent 錯 token POST approve | 401 | ✓ |
| 6 | 以上 denied 全落 console_audit(`bad or missing token`)| 有 | ✓ |
| 7 | chatagent 直開 memory.db 寫入 | unable to open database | ✓ |

另確認:`console_service.py` 零 `mcp` import(grep = 0)—— 硬規則 5(絕不註冊為 MCP 工具)成立;
chat agent 的工具面只有 anchor-memory(AM),沒有任何 nest console 動詞。

**S5 待做(最後一關)**:糯糯真實驗收 —— 在 app 檔案室對一筆真提案批准(volatility 自己選)或駁回,
全程不經聊天窗口,事後 audit 應出現 `owner_via_console` 落帳。
