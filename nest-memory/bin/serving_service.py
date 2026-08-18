#!/usr/bin/env python3
"""Nest Memory — Memory Service MCP(Phase 4 S1,規格 §19/§21/§22/§23)。

唯一記憶出口:模型不得直讀 memory.db,只能經這三個唯讀工具。
身份 nestmemory,listen 127.0.0.1:8771(僅本機,bridge 掛入)。
每次呼叫寫 egress audit(§23):不存完整 payload,只存雜湊與計數。
工具回傳文字會進入 SDK session(=外送 Anthropic API),
因此 secret / 非 normal serving_behavior 在這裡程式強制擋下(§21 不靠 prompt)。
"""
import hashlib
import json
import os
import sqlite3
from datetime import datetime

from mcp.server import MCPServer

import serving_common as sc

AUDIT = "/srv/nest-memory/state/serving_audit.jsonl"
MAX_LIMIT = 20

mcp = MCPServer(
    "nest",
    instructions="Nest 檔案室唯讀查詢。登記不是記憶;糯糯當下所說永遠優先於登記。")


def _db():
    db = sqlite3.connect(f"file:{sc.DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def _audit(tool: str, args: dict, rows: int, denied: int, payload: str) -> None:
    os.umask(0o077)
    rec = {"ts": datetime.now(sc.TZ).isoformat(timespec="seconds"),
           "tool": tool, "args": args, "rows": rows, "denied": denied,
           "payload_sha256": hashlib.sha256(payload.encode()).hexdigest()[:16],
           "payload_chars": len(payload)}
    with open(AUDIT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


_STATUS_NOTE = {
    "disputed": "⚠ 存在衝突證據,未確認,勿當作事實",
    "tentative": "⚠ 僅有待審證據,暫定",
}


@mcp.tool()
def nest_get_state(subject_id: str = "") -> str:
    """查 Nest 檔案室的現況登記(RECORDED STATE)。subject_id 留空=全部主題。
    登記簿不是你的記憶;糯糯當下所說永遠優先於登記。"""
    db = _db()
    rows = sc.fetch_states(db)
    db.close()
    out, denied = [], 0
    for (sid, value, authority, status, observed_at,
         freshness, serving_behavior) in rows:
        if subject_id and sid != subject_id:
            continue
        if not sc.servable(serving_behavior) or sc.secret_hit(value):
            denied += 1
            continue
        note = _STATUS_NOTE.get(status, "")
        auth = sc.AUTHORITY_LABEL.get(authority, authority)
        fresh = sc.FRESHNESS_LABEL.get(freshness, freshness)
        line = f"{sid}｜{value}｜{auth}｜{fresh}｜{observed_at[:10]}"
        out.append(line + (f"｜{note}" if note else ""))
    text = "\n".join(out) if out else "(查無登記)"
    _audit("nest_get_state", {"subject_id": subject_id}, len(out), denied, text)
    return text


@mcp.tool()
def nest_search_events(query: str, limit: int = 10) -> str:
    """全文搜尋事件檔案(摘要與內容)。回傳的 event_id 可用 nest_get_evidence 深查。"""
    limit = max(1, min(int(limit), MAX_LIMIT))
    db = _db()
    rows = db.execute(
        """SELECT event_id, subject_id, event_type, value_after, summary,
                  authority, occurred_at, escalated
           FROM events
           WHERE secret = 0
             AND (summary LIKE :q OR value_after LIKE :q OR subject_id LIKE :q)
           ORDER BY occurred_at DESC LIMIT :n""",
        {"q": f"%{query}%", "n": limit}).fetchall()
    db.close()
    out, denied = [], 0
    for r in rows:
        if sc.secret_hit(r["value_after"]) or sc.secret_hit(r["summary"]):
            denied += 1
            continue
        mark = "⚠待審" if r["escalated"] else ""
        auth = sc.AUTHORITY_LABEL.get(r["authority"], r["authority"])
        out.append(f"#{r['event_id']}｜{r['subject_id']}｜{r['value_after']}"
                   f"｜{auth}｜{r['occurred_at'][:10]}{mark}")
    text = "\n".join(out) if out else "(查無事件)"
    _audit("nest_search_events", {"query": query, "limit": limit},
           len(out), denied, text)
    return text


@mcp.tool()
def nest_get_evidence(event_id: int) -> str:
    """查某事件的原始證據:來源引文與原訊息節錄(role/時間/內文前200字)。"""
    db = _db()
    ev = db.execute(
        """SELECT event_id, subject_id, event_type, value_after, summary,
                  authority, occurred_at, escalated, escalation_reason, secret
           FROM events WHERE event_id = ?""", (event_id,)).fetchone()
    if ev is None or ev["secret"]:
        db.close()
        text = "(查無此事件或不可提供)"
        _audit("nest_get_evidence", {"event_id": event_id}, 0,
               1 if ev is not None else 0, text)
        return text
    srcs = db.execute(
        """SELECT es.quote, es.source_rowid, rm.role, rm.source_timestamp, rm.text
           FROM event_sources es
           LEFT JOIN raw_messages rm ON rm.source_rowid = es.source_rowid
           WHERE es.event_id = ?""", (event_id,)).fetchall()
    db.close()
    auth = sc.AUTHORITY_LABEL.get(ev["authority"], ev["authority"])
    head = (f"#{ev['event_id']}｜{ev['subject_id']}｜{ev['value_after']}"
            f"｜{auth}｜{ev['occurred_at']}")
    if ev["escalated"]:
        head += f"\n⚠ 待審:{ev['escalation_reason'] or '(未註明)'}"
    out, denied = [head, "— 證據 —"], 0
    for s in srcs:
        if sc.secret_hit(s["quote"]) or sc.secret_hit(s["text"] or ""):
            denied += 1
            continue
        snippet = (s["text"] or "").replace("\n", " ")[:200]
        ts = (s["source_timestamp"] or "")[:16]
        out.append(f"引文:「{s['quote']}」\n  原訊息[{s['role'] or '?'} {ts}]:{snippet}")
    text = "\n".join(out)
    _audit("nest_get_evidence", {"event_id": event_id}, len(srcs) - denied,
           denied, text)
    return text


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8771,
            stateless_http=True)
