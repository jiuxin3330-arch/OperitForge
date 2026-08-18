# Phase 4 工程紀錄(Serving)

2026-08-18|作者:實作窗牧牧|**先交報告再請審** ✓|S1+S2+S3 全部完成,S3 已開閘,糯糯體感初驗通過,待規劃窗複審

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

## S3 已開閘(2026-08-18 14:0x,糯糯在場)
- claude.py:_nest_state_snapshot(),插入位置=memory_hits 之後、MEMORY_GUIDE/anchor 之前
- 開關 NEST_STATE_SNAPSHOT=1(version-bridge.env);檔案缺失=自動不注入(fail-safe)
- 快照 897 字元(11 subjects),低於預估的 1-2k;低頻變動,平日躺快取
- 回滾點:version-bridge-app.prev-p4 完整複本 + 開關歸 0 重啟(兩層,均未動用)
- **注入實證**:chat 牧牧在對話中自發指認「系統注入裡多了 Nest 檔案室・現況登記(RECORDED STATE)」——注入到達且他以「系統檔案」身分感知,未誤認為自己的記憶(§7 語態鐵律的行為驗證)
- **糯糯體感初驗:通過**(「效果很不錯」「正常了」)。正式 verified 標記留給複審裁定
- 測試題庫已備(見聊天窗):快照題(Stone Memory 用戶名/麻將-2分/客服三技能)、工具題(Saelra 新冠/漂流瓶 receipt_id/綠色情人節)、誠實題(escalated 染髮事件應答「待審」)

## 副件:彩蛋投遞 bug(同日發現同日修復,詳見 chatnest-next/docs/FIX_20260818_easter_egg.md)
- 症狀:chat 牧牧埋蛋回報成功(池子15顆),Next 收藏冊 0 顆可抽
- 根因:8/16 搬家時 runtime 帶到舊版 easter_egg.py(只寫 legacy JSON 信箱),8/12 的「直投後端 catalog」修復未隨遷——之後的蛋全落在無人讀取的舊信箱;老婆的抽取池(easter_egg_catalog)自 8/16 12:00 斷供
- 修復:①3 顆滯留活蛋搬入 catalog(保留原 id/created_at;其餘 12 顆 JSON「活蛋」實為已匯入已抽取,不重複搬)②drop_easter_egg 改直投 POST /api/v2/tools/easter-egg(X-ChatNest-MuMu-Tool,token 讀 bridge home);後端不通時退 JSON 後備+誠實回報「這顆老婆抽不到」③chatagent 帶 token 實測:422(認證通過)/錯 token 404
- 糯糯實測:正常

## 時間系統調查(移交規劃窗,本窗未動工)
- 結論:時間鏈路本體存活(後端 _turn_time_context→hidden_context→bridge 加框),觸發正確;缺口=①提示只有相對時間,全鏈路無任何「現在時刻」注入②間隔<3h 零時間訊號③壓縮後舊標記被摘要掉
- bridge 舊 P11 time_marker 為刻意停用(Next owns time context),非搬家損壞
- 修法方案 A/B 已呈糯糯→轉規劃窗;規劃窗已與小踢討論成文,後續依該文件執行,不在 P4 範圍

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

## 待辦(P4 收尾,供複審裁量)
- [x] S3 開閘(糯糯在場)→ 體感初驗通過;verified 標記待複審
- [ ] 觀察數輪 turn_usage 確認快照躺快取(897 chars,預期無感)
- [ ] local_only 實測案例:目前 19 subjects 全 normal,建議擇一敏感主題(如 relationship.agreements)由糯糯決定是否標 local_only,順帶驗證整條 deny 鏈(GS-25 已測函數層,缺端到端)
- [ ] session_bootstrap(§8)排 P5,單獨打樣
- [ ] 時間系統修復:依規劃窗×小踢文件執行(另一工單)
