import os
import subprocess
import uuid
os.environ["MCP_DISABLE_TRANSPORT_SECURITY"] = "1"

from mcp.server.fastmcp import FastMCP, Context
from anchor_memory import AnchorMemory
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--db-path", default="./memory_data")
args = parser.parse_args()

memory = AnchorMemory(db_path=args.db_path)
mcp = FastMCP("anchor-memory", host="0.0.0.0", port=8765, stateless_http=True)


def _caller(ctx) -> str:
    """呼叫端類別，只進注入帳與 log，不決定任何行為（強化與否是依路徑判定的，見 anchor_memory.search）。
    local = 本機（bridge 被動檢索 / wakeup 注入 / wake_runner / 本機腳本）；external = 經公網進來（claude.ai
    connector、CC 窗口）。stateless http 拿不到 clientInfo，所以看 client ip / cloudflare header。"""
    try:
        req = ctx.request_context.request
        if req.headers.get("cf-connecting-ip"):
            return "external"
        ip = req.client[0] if req.client else ""
        return "local" if ip in ("127.0.0.1", "::1") else "external"
    except Exception:
        return "unknown"


# ========== 基本操作 ==========

@mcp.tool()
def store_memory(memory_id: str, text: str, tag: str = "general", tier: str = "long", emotion_score: float = 0.5,
                 source: str = None, entity: str = None, kind: str = "memory", derived_from: list = None) -> str:
    """儲存記憶。kind 預設 memory；daily_digest / letter_digest / digest 是衍生類，derived_from（來源 id 列表）必填，否則拒。"""
    try:
        result = memory.store(memory_id=memory_id, text=text, tag=tag, tier=tier, emotion_score=emotion_score,
                              source=source, entity=entity, kind=kind, derived_from=derived_from)
    except ValueError as e:
        return f"✗ 拒絕儲存：{e}"
    return f"✓ 記憶已儲存：{result}"

@mcp.tool()
def search_memory(query: str, n_results: int = 5, tag: str = None, associate: bool = True, hebbian: bool = True,
                  debug: bool = False, ctx: Context = None) -> str:
    """語意搜尋。檢索永不強化連結、永不累計引用（hebbian 參數保留相容但被忽略）。"""
    results = memory.search(query=query, n_results=n_results, tag=tag, associate=associate, hebbian=hebbian,
                            debug=debug, caller=_caller(ctx))
    if not results:
        return "沒有找到相關記憶"
    output = []
    for r in results:
        via = " (聯想)" if r.get("via_association") else ""
        snippet = r['snippet'][:200] if len(r['snippet']) > 200 else r['snippet']
        line = f"【{r['memory_id']}】[{r['tag']}]{via}\n{snippet}"
        if debug:
            extras = []
            for k in ('raw_distance', 'citation_boost', 'emotion_boost', 'final_score', 'source', 'edge_weight'):
                if k in r:
                    extras.append(f"{k}={r[k]}")
            if extras:
                line += f"\n  debug: {', '.join(extras)}"
        output.append(line)
    return "\n\n".join(output)

@mcp.tool()
def delete_memory(memory_id: str) -> str:
    affected = memory.db.affected_by(memory_id)
    success = memory.delete(memory_id)
    if not success:
        return f"✗ 找不到：{memory_id}"
    note = ""
    if affected["digests"] or affected["card_facts"]:
        note = (f"（受影響：{len(affected['digests'])} 筆衍生 digest、{len(affected['card_facts'])} 條卡片事實；"
                f"lineage / provenance 保留，可用 memory_lineage / cards_affected_by 查）")
    return f"✓ 已刪除：{memory_id}{note}"

# ========== 連結與結構 ==========

@mcp.tool()
def connect_memories(source_id: str, target_id: str, weight: float = 2.0) -> str:
    memory.db.connect(source_id, target_id, weight)
    return f"✓ 已連結：{source_id} ↔ {target_id}"

@mcp.tool()
def get_neighbors(memory_id: str, min_weight: float = 0.5, limit: int = 5) -> str:
    neighbors = memory.db.get_neighbors(memory_id, min_weight=min_weight, limit=limit)
    if not neighbors:
        return "沒有鄰居"
    return "\n".join([f"• {n['memory_id']} (權重: {n['weight']:.2f})" for n in neighbors])

# ========== 情緒與層級 ==========

@mcp.tool()
def set_emotion(memory_id: str, score: float) -> str:
    memory.db.set_emotion_score(memory_id, score)
    return f"✓ 已更新情緒分數：{memory_id} → {score}"

@mcp.tool()
def set_tier(memory_id: str, tier: str) -> str:
    memory.db.set_tier(memory_id, tier)
    return f"✓ 已更新層級：{memory_id} → {tier}"

# ========== 註釋系統 ==========

@mcp.tool()
def annotate_memory(memory_id: str, text: str) -> str:
    aid = memory.db.annotate(memory_id, text)
    return f"✓ 已註釋：{memory_id}（annotation_id: {aid}）"

@mcp.tool()
def get_annotations(memory_id: str) -> str:
    anns = memory.db.get_annotations(memory_id)
    if not anns:
        return "沒有註釋"
    return "\n".join([f"[{a.get('timestamp', '?')}] {a.get('text', '')}" for a in anns])

@mcp.tool()
def search_annotations(query: str, limit: int = 5) -> str:
    rows = memory.db.search_annotations(query, limit=limit)
    if not rows:
        return "沒有找到相關註釋"
    return "\n".join([f"【{r['memory_id']}】{r.get('text', '')[:100]}" for r in rows])

# ========== 冷啟動與留言 ==========

@mcp.tool()
def wakeup(n_high_emotion: int = 5, n_random: int = 2, high_emotion_days: int = 3, ctx: Context = None) -> str:
    result = memory.db.wakeup(n_high_emotion=n_high_emotion, n_random=n_random, high_emotion_days=high_emotion_days)
    # 注入帳（invariant ③）：開場注入的 pinned / 高情緒 / 隨機都記；wakeup 本身不強化（本來就沒有）
    try:
        ids = [m.get("memory_id") for k in ("pinned", "high_emotion", "random_old") for m in result.get(k, [])]
        memory.db.record_injection(ids, path="wakeup", caller=_caller(ctx))
    except Exception:
        pass
    import json
    return json.dumps(result, ensure_ascii=False, indent=2)

@mcp.tool()
def leave_comment(memory_id: str, content: str, author: str = "ai", reply_to: str = None) -> str:
    cid = memory.db.insert_comment(memory_id=memory_id, content=content, author=author, reply_to=reply_to)
    return f"✓ 留言已新增：{cid}"

@mcp.tool()
def get_comments(memory_id: str) -> str:
    rows = memory.db.get_comments(memory_id)
    if not rows:
        return "沒有留言"
    return "\n".join([f"[{r.get('author', '?')}] {r.get('content', '')}" for r in rows])

@mcp.tool()
def mark_comments_read(comment_ids: list, reader: str = "ai") -> str:
    memory.db.mark_comments_read(comment_ids, reader=reader)
    return f"✓ 已標記 {len(comment_ids)} 則留言為已讀"

# ========== 釘選 ==========

@mcp.tool()
def pin_memory(memory_id: str) -> str:
    memory.db.pin(memory_id)
    return f"✓ 已釘選：{memory_id}"

@mcp.tool()
def unpin_memory(memory_id: str) -> str:
    memory.db.unpin(memory_id)
    return f"✓ 已取消釘選：{memory_id}"

# ========== 引用與整合 ==========

@mcp.tool()
def cite_memory(memory_id: str) -> str:
    """明確引用 → 強化（第 1 次全額、2–3 次減半、之後趨零、有上限）。這是唯一會強化節點的路徑之一（另一個是 annotate）。"""
    r = memory.db.cite(memory_id)
    if not r:
        return f"✗ 找不到：{memory_id}"
    return (f"✓ 已引用：{memory_id}（第 {r['reinforced_count']} 次，+{r['increment']:.3f} → "
            f"reinforcement {r['reinforcement']:.3f}）")

@mcp.tool()
def consolidate(conversation_text: str) -> str:
    """被動整合：比對對話文字，把同時出現的記憶建邊（遞減封頂）。最近被 search/wakeup 注入過的記憶不算——複述不是強化。"""
    result = memory.consolidate(conversation_text)
    import json
    return json.dumps(result, ensure_ascii=False)

# ========== 維護 ==========

@mcp.tool()
def dream_pass() -> str:
    stats = memory.dream_pass()
    return f"🌙 整理完成：清理 {stats.get('decayed_memories', 0)} 筆，修剪 {stats.get('pruned_edges', 0)} 條連結"

@mcp.tool()
def graph_stats() -> str:
    total = memory.count()
    all_mems = memory.db.list_all(limit=total)
    tags = {}
    tiers = {}
    for m in all_mems:
        tags[m.get("tag", "unknown")] = tags.get(m.get("tag", "unknown"), 0) + 1
        tiers[m.get("tier", "unknown")] = tiers.get(m.get("tier", "unknown"), 0) + 1
    lines = [f"📊 共 {total} 筆記憶"]
    lines.append("標籤分佈：" + ", ".join(f"{k}:{v}" for k, v in sorted(tags.items())))
    lines.append("層級分佈：" + ", ".join(f"{k}:{v}" for k, v in sorted(tiers.items())))
    return "\n".join(lines)

# ========== TICKET-Q Q2：記憶待辦（memory_tasks）==========

@mcp.tool()
def memory_task_create(source_id: str, intent: str) -> str:
    """立一筆「要記但還沒記」的待辦。source_id = 來源訊息/事件 id，intent = 要記什麼的摘要。"""
    try:
        t = memory.db.task_create(source_id, intent)
    except ValueError as e:
        return f"✗ {e}"
    return f"✓ 待辦已建立：{t['id']}（open）"

@mcp.tool()
def memory_task_list(status: str = "open", limit: int = 50) -> str:
    """列待辦。status = open | resolved | dismissed | all。"""
    rows = memory.db.task_list(status=None if status == "all" else status, limit=limit)
    if not rows:
        return "沒有待辦"
    out = []
    for t in rows:
        tail = ""
        if t["status"] != "open":
            tail = f" → {t['status']} by {t['resolved_by']} @ {str(t['resolved_at'])[:16]}：{t['reason']}" + \
                   (f"（result_ref={t['result_ref']}）" if t.get("result_ref") else "")
        out.append(f"• {t['id']} [{t['status']}] {t['intent']}（source={t['source_id']}）{tail}")
    return "\n".join(out)

@mcp.tool()
def memory_task_resolve(task_id: str, status: str, resolved_by: str, reason: str, result_ref: str = None) -> str:
    """銷帳。status = resolved | dismissed；resolved_by 與 reason 必填；result_ref 指向最終寫成的 memory_id（可空）。終態不可再轉，沒有刪除。"""
    try:
        t = memory.db.task_resolve(task_id, status, resolved_by, reason, result_ref)
    except ValueError as e:
        return f"✗ {e}"
    return f"✓ {t['id']} → {t['status']}（by {t['resolved_by']}：{t['reason']}）"

# ========== TICKET-Q Q3：實體卡（entity_cards + card_facts）==========

@mcp.tool()
def create_entity_card(name: str, what: str, why: str, timeline: str, owner_token: str, status: str = "candidate") -> str:
    """建卡（只有 owner）。三行卡：what 這是什麼 / why 為什麼重要 / timeline 一句時間線。owner_token 不符一律拒。"""
    try:
        c = memory.db.card_create(name, what, why, timeline, owner_token, status=status)
    except PermissionError as e:
        return f"✗ 拒絕：{e}"
    except ValueError as e:
        return f"✗ {e}"
    return f"✓ 卡已建立：{c['id']}「{c['name']}」[{c['status']}]"

@mcp.tool()
def set_entity_card_status(card_id: str, status: str, owner_token: str) -> str:
    """改卡生命週期（candidate → active → archived），只有 owner。"""
    try:
        c = memory.db.card_set_status(card_id, status, owner_token)
    except PermissionError as e:
        return f"✗ 拒絕：{e}"
    except ValueError as e:
        return f"✗ {e}"
    return f"✓ {c['id']}「{c['name']}」→ {c['status']}"

@mcp.tool()
def update_card_fact(card_id: str, field: str, value: str, provenance: str) -> str:
    """更新既有卡的一個事實（任何身分可用，系統/夜間只能走這條）。舊值補 valid_until + superseded_by，不刪不劃線。provenance = 來源 memory/event id，必填。"""
    try:
        r = memory.db.card_fact_update(card_id, field, value, provenance)
    except ValueError as e:
        return f"✗ {e}"
    sup = f"，取代 {', '.join(r['superseded'])}" if r["superseded"] else "（首筆）"
    return f"✓ {r['card_id']}.{r['field']} = 新事實 {r['fact_id']}{sup}"

@mcp.tool()
def get_entity_card(card_id: str = None, name: str = None, include_history: bool = False) -> str:
    """讀卡（current projection；include_history=true 連被取代的舊事實一起列）。兩個都不給就列全部卡。"""
    import json
    if not card_id and not name:
        rows = memory.db.card_list()
        return "沒有卡" if not rows else "\n".join(f"• {r['id']} 「{r['name']}」[{r['status']}]" for r in rows)
    c = memory.db.card_get(card_id=card_id, name=name, include_history=include_history)
    if not c:
        return "找不到這張卡"
    return json.dumps(c, ensure_ascii=False, indent=2)

@mcp.tool()
def cards_affected_by(source_id: str) -> str:
    """provenance 反查：給一個來源 id，列出引用它的卡片事實（含已被取代的）。source 要刪之前先查這個。"""
    rows = memory.db.cards_affected_by(source_id)
    if not rows:
        return "沒有卡片事實引用這個來源"
    return "\n".join(
        f"• {r['card_name']}({r['card_id']}).{r['field']} = {r['value'][:60]} "
        f"[{'現行' if r['valid_until'] is None else '已取代 by ' + str(r['superseded_by'])}] fact={r['id']}"
        for r in rows)

# ========== TICKET-Q Q4：lineage ==========

@mcp.tool()
def memory_lineage(memory_id: str) -> str:
    """雙向 lineage：給 digest id 回 source ids；給 source id 回衍生的 digest ids。"""
    import json
    return json.dumps(memory.db.lineage_of(memory_id), ensure_ascii=False, indent=2)

# ========== 終端操作（自訂功能）==========

import mcp_path_alias  # 方案 B 雙路並存過渡層

if __name__ == "__main__":
    mcp_path_alias.serve(mcp, "/srv/chatnest-next/runtime/mcp-keys/anchor.key")
