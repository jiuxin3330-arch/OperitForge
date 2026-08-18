# Phase 4 工程紀錄(Serving)

2026-08-18|作者:實作窗牧牧|**先交報告再請審** ✓|S1+S2 完成,S3 程式碼就位待糯糯在場開閘

## 驗收前置(硬規則 15)
- 語感打樣:版本 A(完整框架)經糯糯驗收定稿 ✓(2026-08-18,聊天窗)
- 尾註「另有 N 項存在衝突證據」:糯糯授權老公裁量 → **留**(誠實提示,§18 姿態的一部分)
- 15 subjects 現值人審:糯糯核可 ✓

## S1 已完成:Memory Service MCP(唯一記憶出口,§19)
- serving_service.py:mcp SDK 2.0(MCPServer),streamable-http,127.0.0.1:8771,stateless
- 三個唯讀工具:nest_get_state / nest_search_events / nest_get_evidence
  * disputed/tentative 附「⚠ 存在衝突證據」警示;escalated 事件標「⚠待審」
  * evidence 回:事件+來源引文+原訊息節錄(role/時間/前200字)
- privacy/secret 程式強制(§21/§22,不靠 prompt):secret=1 事件不查得;SECRET_RE 命中=deny(不遮罩);serving_behavior≠normal 一律不外供
- egress audit(§23):/srv/nest-memory/state/serving_audit.jsonl,每呼叫記 ts/tool/args/rows/denied/payload_sha256+chars,不存完整 payload
- systemd nest-serving.service(User=nestmemory,ProtectSystem=strict+ReadWritePaths)
- bridge 掛入 mcp_servers "nest" + allowed_tools 三工具,重啟無損

## S2 已完成:Serving renderer(快照落檔)
- serving_common.py:共用過濾+渲染(語感範本=糯糯驗收版 A,改措辭=硬規則 12 回歸範圍)
- render_snapshot.py:只列 active;disputed/tentative 進尾註計數;freshness/authority 中文標籤;值截 100 字
- 低頻變動(硬規則 16):sha256 比對,內容沒變不改寫(實測二跑 changed=False,mtime 不動)
- 首發:11 active 列出+4 disputed 尾註,與打樣一致;cron 03:50(projection 03:40 之後)
- ACL 走廊(登記 ACL_LEDGER.md):chatagent 僅 traverse /srv/nest-memory + 讀 serving/;實測讀 db/、audit 皆 denied

## S3 程式碼就位,開關未開
- claude.py:_nest_state_snapshot(),插入位置=memory_hits 之後、MEMORY_GUIDE/anchor 之前
- 開關 NEST_STATE_SNAPSHOT(version-bridge.env,現=0);檔案缺失=自動不注入(fail-safe)
- 回滾點:version-bridge-app.prev-p4 完整複本 + 開關歸 0 重啟(兩層)
- 開閘條件:糯糯在場,開後由她體感驗收(技術指標不構成 verified)

## Health / Golden
- health 第十項 serving:renderer 新鮮度(26h/74h)+ MCP 8771 存活;十項全綠
- Golden 新增 GS-24(disputed 不進 snapshot)、GS-25(secret/local_only 強制不外供):全量 9 passed / 0 failed

## 踩雷實錄
1. mcp SDK 2.0 改版:FastMCP 併入 MCPServer(mcp.server),v1 的 import 路徑全失效;host/port 移到 run() kwargs。
2. systemd ProtectSystem=strict + SQLite WAL:唯讀連線也要碰 -shm,db 目錄必須進 ReadWritePaths,否則「unable to open database file」。
3. freshness 欄位在 disputed 列的值是 'disputed',標籤表要涵蓋,否則英文漏進中文快照。

## 設計裁量(供複審)
1. audit 用 JSONL 不進 memory.db:audit 是營運日誌非記憶正典(硬規則 1 針對記憶資料);放 state/ 不在 ACL 走廊內。
2. snapshot 檔 0644+目錄 ACL 管門禁:檔案本身無敏感(已過濾),門禁由目錄層 ACL 承擔。
3. secret 命中=整條不供(deny)而非遮罩:遮罩留下「有東西被藏」的痕跡反而誘導追問,deny+audit 較乾淨。
4. session_bootstrap(§8)未含在本次:單獨打樣排 P5,不混批。

## 待辦(P4 收尾)
- [ ] S3 開閘(糯糯在場)→ 她體感驗收 → 才標 verified
- [ ] 開閘後觀察一輪 turn_usage(State Snapshot 預計 +1–2k,平日躺快取)
- [ ] local_only 實測案例:目前 17 subjects 全 normal,建議擇一敏感主題(如 relationship.agreements)由糯糯決定是否標 local_only,順帶驗證整條 deny 鏈
