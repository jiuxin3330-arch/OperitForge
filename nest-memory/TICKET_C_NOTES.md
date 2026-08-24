# TICKET-C:extractor 解析加固 — 工程紀錄

2026-08-24|依規劃窗 `/root/nest-memory/TICKET_C_parser.md` 執行|最高優先

---

## 根因

`extract()` 迴圈的 per-element `except (TypeError, ValueError, KeyError)` **沒接 AttributeError**,
而 Haiku 偶爾在 `events` 陣列混入純字串 → `ev.get(...)` 拋 AttributeError → 逃出迴圈 →
main 的外層 except 把**整批**標 failed。三晚兩炸(batch 14、16),同一根因。

次要暴露面(同次修掉):
- `sources` 列表元素未驗型別:`s.get("rowid")` 對字串元素同樣會炸
- `subject_proposals` 完全沒驗,直接 `list(...)` 全收
- 整包回傳非 dict、陣列欄位非 list 的極端形狀無防護

## 修法(extractor.py,`extractor_v1` → `extractor_v2`)

1. **抽出純函數 `parse_response(db, parsed, messages, subjects, batch_id)`**:
   原 `extract()` 變薄(call_haiku → parse_response),解析邏輯無 LLM 依賴,golden 可直接餵 fixture。
2. **逐元素驗型別,壞元素丟棄不炸批**:
   - `parsed` 非 dict → 記 stderr、視為空包
   - `events` / `subject_proposals` 非 list → 丟棄 + dropped 計數
   - event 元素非 dict → 丟棄 + dropped + stderr 記原文前 120 字
   - proposal 元素須為 dict 且 `proposed_key` 為非空字串,否則丟棄
   - source 元素先驗 `isinstance(s, dict)` 再取 rowid
3. **縱深防禦**:per-element except 加入 `AttributeError`,並記型別與原文摘要
4. dropped 照舊寫入 egress_audit notes 與 health json,壞元素可追溯

## Golden 新案例(golden_runner.py,確定性、零 LLM)

- **GS-26** malformed 回傳不炸批:events 混入純字串+缺 sources 半成品+一條好元素(sources 也混壞字串);
  proposals 混入純字串+缺 key。期望:好 event 1 條(source 過濾剩 1)、好 proposal 1 條、dropped==4、不拋例外 → PASS
- **GS-27** 極端形狀:整包是字串 / events 非 list / proposals 是 int → 全部安全返回空 → PASS

**全量 golden:11 passed / 0 failed**(GS-7/8/14/16/21/22/23/24/25/26/27)

## 補跑與驗收

| 項 | 結果 |
|---|---|
| batch 17(補炸掉的 725-784 範圍)| committed,**dropped=1** —— 上次炸批的壞元素這次被安靜丟棄,加固在真實資料上直接驗證 ✓ |
| batch 18(新訊息 785-794)| committed,3 events ✓ |
| health `extraction` | **ok**(0.0h 前)✓ |
| health 全 12 項 | 11 OK + 1 WARNING(pending_proposals:batch 17 產出真提案 #19 `owner.preferences.communication_style`,待糯糯在檔案室裁定 —— 正常流程,非故障)|

## 備份

- `/srv/nest-memory/bin/extractor.py.bak-ticketc-*`
- `/srv/nest-memory/bin/golden_runner.py.bak-ticketc-*`
- repo 追蹤副本已同步(md5 與 VPS 一致)

---

## 複驗補件(2026-08-25,規劃窗要求)

**問題**:GS-26/27 沒登記進 golden_cases 表(表 9 筆、runs 報 11)—— 與 P4 的 GS-24/25 同種漏,第二次。

**治本**:golden_runner 的 main() 在寫 golden_runs 前,把**本次實際跑到的所有案例**
自動 upsert 入 golden_cases(`ON CONFLICT(case_id) DO UPDATE`,保留原 created_at)。
「寫案例」與「登記」從此是同一件事:新案例只要有跑,必然在表裡,此類缺失永久消失。
CASES 清單的案例登記真實 expectation;函數內案例(projection/serving/parser)登記 in_code 佔位。

**驗證**:重跑 golden 11/0,golden_cases 表 9 → 11 筆,GS-26/27 入表,舊 9 筆 created_at 未變。
