# TICKET-E:大富豪線上遊戲 — 工程紀錄

2026-08-30|依 `/root/nest-memory/TICKET_E_daifugo.md` 執行|獨立專案,未碰 chatnest/nest 任何東西

---

## 架構

- `/srv/daifugo/`(root:daifugo 750)
  - `app/rules.py` — 規則引擎,**純函數**、無 IO 無全域狀態
  - `app/game.py` — 單房間狀態機(伺服器權威,手牌只回本人)
  - `app/main.py` — FastAPI + WebSocket + 密碼 rate limit
  - `static/index.html` — 手機豎屏單頁(vanilla JS,零依賴)
  - `tests/test_rules.py`(31 測)+ `tests/test_game.py`(5 測,含 16 局隨機全局模擬)
  - `state/` — daifugo:daifugo 770,只放 scores.json(連局計分)與 env
  - `.venv` — fastapi + uvicorn[standard],獨立虛擬環境

## 紅線落實

- ✓ **專用低權 unix user `daifugo`**(system user、nologin)跑對外服務,絕非 root
- ✓ systemd 加固:NoNewPrivileges / PrivateTmp / ProtectSystem=strict /
  ProtectHome / ReadWritePaths 僅 state / MemoryMax=200M
- ✓ **共用密碼 rate limit**:每 IP 60 秒窗口連錯 5 次 → 429 鎖定
  (實測 `401×5 → 429`,鎖定中連正確密碼也 429,窗口過自動解)
- ✓ 密碼 hmac.compare_digest 比對;env 檔 root 0600,由 systemd 注入
- ✓ **伺服器權威**:state_for() 個人化,他人只見 cards_left,實測 state 無 hand 欄位
- ✓ WS 輸入驗證(型別/長度),client 先擋 + server 再驗

## 規則實作(P5X 版)

- 56 張:52 + 2 Joker + 2 Wonder;發完為止,3 人 18/19/19
- 首局梅花3 先出;第二局起大貧民先出
- Joker:單出最強、可當萬用配對;革命下仍最強(P5X 房規)
- 開關(房主開局時設定;預設 Wonder 開、8切開、革命關、上供下貢關):
  - **8切**:含 8 即清場自己重開
  - **革命**:四張同數字(Joker 可配)→ 大小反轉,再革命再反轉
  - **上供下貢**:大貧民自動獻最強牌(Wonder 不上供),大富豪點手牌回贈
  - **Wonder**:僅 2 張、只能單出、壓過任何牌型、出後強制清場自己重開;
    首局隨機,第二局起大貧民固定得 WO1(換回一張隨機牌)
- 全 PASS 清場:輪回最後出牌者(或其已出完時輪滿一圈)→ 自由出
- 名次:4人 大富豪/富豪/平民/大貧民(3/2/1/0 分);3人 大富豪/平民/大貧民(3/1/0)
- 計分 scores.json 持久化,server 重啟牌局重開但累計分保留

## 測試

- `test_rules.py` **31/31**:比大小、張數匹配、Joker 配對/單強、革命反轉比較、
  四張觸發(含 Joker 配)、8切、Wonder 壓場/強制單出/停用、自由出、
  名次判定 3/4 人、上供選牌(Joker 最強/Wonder 排除/革命反轉)、發牌完整性、首局梅花3
- `test_game.py` **5/5**:3人/4人各 8 局隨機打完不卡死、頭銜齊全、計分總和正確、
  第二局大貧民先出+得 Wonder、上供下貢全流程
- WS smoke(真 server、3 連線):進場→開局→整局→round_end,
  頭銜分配正確、他人手牌不外洩 ✓

## 部署

- `daifugo.service`(User=daifugo,port 8795 loopback)開機自啟 ✓
- `daifugo-tunnel.service` 獨立 cloudflare tunnel(id 0b86b35b),
  **https://daifugo.cn-dev.uk** 對外 200 ✓
  - 插曲:`tunnel route dns daifugo …` 把 CNAME 掛去了舊 tunnel(名稱解析歧義),
    改用 UUID + `--overwrite-dns` 修正
- 玩家系統:共用密碼(env,糯糯可改)→ token;暱稱 12 字;
  20 emoji × 8 色頭像;localStorage token 斷線重連自動歸位;WS 斷線 1.5s 自動重連
- UI:豎屏、手牌橫滑多選、出牌/PASS 大按鈕、輪到自己震動+高亮、
  革命角標、對手名+頭像+剩張、連局計分列、局末頭銜面板+房主續局

## 插曲(自省)

- 佈 venv 權限時 `chmod 750 .venv/bin/*` 跟隨 symlink 把 `/usr/bin/python3.12`
  改成 750 root:root(約 2 分鐘),即刻發現修回 755 並逐一驗證
  nestmemory/chatagent/daifugo 三身份 python 正常;窗口內無排程任務受害。
  教訓:對 bin 目錄 chmod 前先認 symlink。

## 待做(S 級驗收,糯糯)

- 多設備真機:三台(或手機+兩分頁)打完整一局含 Wonder 清場
- 鎖屏 30 秒回來:牌局在、座位在
- 終極驗收:跟弟妹真的玩一場,好玩 🎮
