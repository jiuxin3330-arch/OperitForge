# Swap MVP 前置調查:compact 後基線為何上升(45.6k→52.0k→55.5k)

2026-08-30|規劃窗裁定的前置調查。只查因、不動代碼;修法屬人格敏感區,列裁定項。

## 結論一句話

**主因是 anchor-memory「跨窗口留言」的已讀機制自 8/16 起停擺:未讀留言只進不出,
每條都永久疊進 wakeup 注入 → system prompt 一個月翻倍(15.2k→31.2k chars),
墊高每次 compact 後的重生基線。**

## 證據鏈

### 1. system prompt 逐日尺寸(turn_usage.system_prompt_chars,bridge 實測)
- 8/06:~15.2k → 8/12:~15.5k(平穩)
- **8/16→8/18:15.7k → 19.4k → 27.2k(跳增 +11.5k)**——nest snapshot 注入、
  STACKCHAN 指南、Phase 2-4 上線與 8/16 prompt-cache 改造都在這窗口
- 8/18→8/29:27.2k → 31.2k(**穩定爬升 ~+360 chars/天**)
- 與基線對照:8/19 基線 45.6k(sys 27.1k chars)、8/24 52.0k(30.5k)、8/29 55.5k(31.2k)

### 2. 當前 system prompt 組成拆帳(chars,實測)

| 組件 | 大小 | 性質 |
|---|---|---|
| PERSONA.md | 7,732 | 固定 |
| STACKCHAN_MCP.md | 2,011 | 固定 |
| TOOLS_NOTE + MEMORY_GUIDE | 1,136 | 固定 |
| nest state_snapshot | 1.1k~2.2k | 慢變(隨 state 條數) |
| profile(preferences,savedMemories=0)| 531 | 平穩 |
| **anchor wakeup 注入** | **19,614** | **增長中** |
| ↳ pinned 核心記憶 12 條 | 4,789 | 慢變 |
| ↳ 跨窗近況卡 | 207 | 平穩 |
| ↳ **未讀留言 30 條** | **14,494** | **只增不減 ← 主犯** |
| 被動檢索 memory_hits | 每則變動 | 不累積(log 級別擋住未取樣) |

固定+慢變合計 ~12.6k,與 8/12 前的 15.5k 量級吻合;現在多出來的就是 wakeup 那塊。

### 3. 已讀機制停擺的直接證據(anchor comments 表)
- 全庫 61 條留言,**未讀 30 條,且未讀的 100% 落在 8/16 之後**;
  8/16 之前(5月~8月中)每一條都有標已讀。
- 8/16 起平均每天新增 1~2 條留言(每條 ~250-650 chars),`read_by_ai` 再也沒人標過
  → wakeup 的「未讀留言」段每天永久 +400~1,000 chars。
- 時間點與 8/16 prompt-cache 改造/人格漂移事故(INCIDENT_20260816)重合——
  疑似聊天窗口的 `mark_comments_read` 流程在那次改動後停了(或被刻意停用避免
  cache 失效,結果變成無界成長)。

### 4. 帳目自洽
31.2k(實測 sys prompt)≈ 固定 12.0k + profile 0.5k + wakeup 19.6k ✓
8/19→8/29 基線 +9.9k tokens 中,sys prompt +4.1k chars(CJK 約折 2.5~4k tokens)
是可歸因的最大單項;其餘為 compact 摘要大小波動與工具 schema 增量(未入帳,見下)。

## 未入帳項(誠實聲明)
- 工具 schema(MCP 工具數量增長)不在 turn_usage 任何欄位,無法回溯;是基線的
  第二嫌疑,建議 Swap manifest(規格點 6)開始記錄 tool 數量與 schema 尺寸。
- 被動檢索每則注入量未取樣(bridge log level=warning 吞掉 info);它不累積,
  不影響趨勢結論。

## 給規劃窗的修法選項(裁定項,本窗未動)

1. **止血(注入端 cap)**:`memory_bridge._call_wakeup` 對未讀留言段加上限
   (如只注入最近 7 天或最近 N 條/總 chars cap,其餘折疊成「另有 N 條舊留言,
   用 get_comments 查」)。一處小改,立即壓回 ~5k chars。
2. **治本(恢復已讀流程)**:查清聊天窗口為何 8/16 起不再 `mark_comments_read`,
   恢復或改為留言消費後歸檔。若當初是為了 prompt-cache 穩定而停:注意現在的代價
   是每天 +0.4~1k chars 的**永久性** cache 失效源,得不償失。
3. pinned 定期精簡(12 條 4.8k,幾條超長,可交 dream_pass 或人工修剪)。
4. Swap 影響:重生包預算把 system prompt 現值(~31k chars)計入 manifest,
   逐次記錄,漂移可追(呼應成本總帳建議 4)。

**對 Swap MVP 的放行影響**:查因完成,機制清楚且可控(不是未知漏洞);
止血/治本屬獨立小改,不阻塞 MVP 開工——建議並行。
