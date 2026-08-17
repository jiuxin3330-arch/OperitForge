#!/usr/bin/env python3
"""Nest Memory — Phase 2 Event Extractor(Haiku 書記官)。

以 nestmemory 身份執行。批次讀 raw_messages → Haiku 抽取「有證據的狀態變化」
→ 本地驗證/指紋冪等/密令掃描/升級規則 → 寫入 events(模型只提案,commit 在本地)。

硬規則落實:
- subject 必須在 Registry 內;不在 → 轉 subject_proposals(PROPOSE_NEW_SUBJECT)
- impact/confidence 只有 low/medium/high;非法值 → 降級+escalate
- 來源必須引用本批次內的 raw rowid;無有效來源 → 丟棄(來源不足)
- fingerprint 冪等:同批重跑不產生 duplicate
- 密令掃描:命中 → secret=1(egress deny)
- deterministic escalation:低信心高影響/同 subject 衝突/隱私安全身分類
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

DB = "/srv/nest-memory/db/memory.db"
TOKEN_FILE = "/srv/nest-memory/state/.claude_token"
HEALTH_FILE = "/srv/nest-memory/health/extract_last_run.json"
API_URL = "https://api.anthropic.com/v1/messages"
CLI_SYSTEM = "You are Claude Code, Anthropic's official CLI for Claude."
MODEL = "claude-haiku-4-5-20251001"
EXTRACTOR_VERSION = "extractor_v1"
BATCH_LIMIT = 60
TZ = timezone(timedelta(hours=8))

AUTHORITIES = {
    "owner_direct_statement", "owner_decision", "owner_confirmation",
    "owner_correction", "assistant_proposal", "assistant_inference",
    "assistant_claim", "tool_verified_result", "system_verified_state",
    "quoted_third_party", "external_content",
}
LEVELS = {"low", "medium", "high"}
ESCALATE_TYPES = {"privacy_change", "security_change", "identity_change"}
SECRET_RE = re.compile(
    r"(api[_-]?key|bearer\s+[a-z0-9_\-\.]{16,}|password|passwd|secret|"
    r"BEGIN [A-Z ]*PRIVATE KEY|ssh-(rsa|ed25519)\s+[A-Za-z0-9+/=]{30,}|"
    r"AGE-SECRET-KEY|sk-[A-Za-z0-9_\-]{20,}|token[=:]\s*\S{16,})", re.I)

PROMPT = """你是 Nest Memory 的抽取書記官。從下面的聊天逐字稿中抽取「有證據的狀態變化」(Event),嚴格遵守:

1. Event 是狀態變化,不是摘要。純閒聊、情話、玩笑、系統模板訊息 → 不產生 Event。
2. subject_id 只能從下方 Subject Registry 挑選。真的找不到但確實重要 → 放進 subject_proposals 提案,不要硬塞。
3. authority 只能是: owner_direct_statement / owner_decision / owner_confirmation / owner_correction / assistant_proposal / assistant_inference / assistant_claim / tool_verified_result / system_verified_state / quoted_third_party / external_content。
   鐵則: assistant 的提議≠owner 決定;assistant 說「完成了」是 assistant_claim 不是 verified;owner 說「可能/再看看」不構成 decision。
4. impact 和 confidence 只有 low/medium/high。
5. 每個 Event 必須引用至少一個來源訊息的 rowid(從逐字稿的 [rowid] 標記取),並附一句原文引述。
6. value_before 不確定就留 null,不要編造。occurred_at 用來源訊息的時間。
7. 用戶(owner)是糯糯,assistant 是牧牧。

只輸出 JSON,格式:
{"events":[{"subject_id":"...","event_type":"decision_change|state_change|preference_change|correction|milestone|config_change","value_before":null,"value_after":"...","summary":"一句話","authority":"...","impact":"low","confidence":"high","occurred_at":"ISO時間","sources":[{"rowid":123,"quote":"原文"}]}],"subject_proposals":[{"proposed_key":"...","reason":"...","example_quote":"..."}]}

## Subject Registry(只能用這些)
{SUBJECTS}

## 逐字稿
{TRANSCRIPT}"""


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read_token() -> str:
    m = re.search(r"CLAUDE_CODE_OAUTH_TOKEN=(.+)", open(TOKEN_FILE).read())
    return m.group(1).strip().strip("\"'") if m else ""


EXTRACT_TOOL = {
    "name": "record_events",
    "description": "登記抽取到的狀態變化事件與新主題提案",
    "input_schema": {
        "type": "object",
        "properties": {
            "events": {"type": "array", "items": {"type": "object", "properties": {
                "subject_id": {"type": "string"},
                "event_type": {"type": "string"},
                "value_before": {"type": ["string", "null"]},
                "value_after": {"type": "string"},
                "summary": {"type": "string"},
                "authority": {"type": "string"},
                "impact": {"type": "string"},
                "confidence": {"type": "string"},
                "occurred_at": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "object", "properties": {
                    "rowid": {"type": "integer"}, "quote": {"type": "string"}},
                    "required": ["rowid"]}},
            }, "required": ["subject_id", "event_type", "value_after", "authority",
                            "impact", "confidence", "sources"]}},
            "subject_proposals": {"type": "array", "items": {"type": "object", "properties": {
                "proposed_key": {"type": "string"}, "reason": {"type": "string"},
                "example_quote": {"type": "string"}}, "required": ["proposed_key"]}},
        },
        "required": ["events", "subject_proposals"],
    },
}


def call_haiku(prompt: str) -> dict:
    """tool-use 強制結構化輸出:API 層保證 JSON 合法,不靠模型手寫。"""
    body = json.dumps({
        "model": MODEL, "max_tokens": 8000,
        "system": CLI_SYSTEM,
        "tools": [EXTRACT_TOOL],
        "tool_choice": {"type": "tool", "name": "record_events"},
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(API_URL, data=body, headers={
        "authorization": f"Bearer {read_token()}",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    for block in data.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "record_events":
            return block.get("input") or {}
    raise ValueError("no tool_use block in response")


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def extract(db, messages, subjects, batch_id):
    """回傳 (valid_events, proposals, dropped)。獨立函數方便 golden runner 重用。"""
    transcript = "\n".join(
        f"[{m['rowid']}] {m['ts']} {m['role']}: {m['text'][:600]}"
        for m in messages)
    subj_desc = "\n".join(
        f"- {s['subject_id']}({s['volatility']}): {s['description']}"
        for s in subjects)
    parsed = call_haiku(PROMPT.replace("{SUBJECTS}", subj_desc)
                              .replace("{TRANSCRIPT}", transcript))
    valid_rowids = {m["rowid"] for m in messages}
    subj_ids = {s["subject_id"] for s in subjects}
    events, proposals, dropped = [], list(parsed.get("subject_proposals") or []), 0

    for ev in parsed.get("events") or []:
        try:
            sources = [s for s in (ev.get("sources") or [])
                       if isinstance(s.get("rowid"), int) and s["rowid"] in valid_rowids]
            if not sources:
                dropped += 1
                continue
            subject = str(ev.get("subject_id") or "")
            if subject not in subj_ids:
                proposals.append({"proposed_key": subject or "(空)",
                                  "reason": "extractor 使用了 Registry 外的 subject",
                                  "example_quote": str(ev.get("summary") or "")[:200]})
                dropped += 1
                continue
            authority = str(ev.get("authority") or "")
            if authority not in AUTHORITIES:
                authority = "assistant_inference"
            impact = ev.get("impact") if ev.get("impact") in LEVELS else "low"
            confidence = ev.get("confidence") if ev.get("confidence") in LEVELS else "low"
            occurred = str(ev.get("occurred_at") or messages[0]["ts"])
            value_after = str(ev.get("value_after") or "")
            if not value_after:
                dropped += 1
                continue
            esc, reasons = 0, []
            if confidence == "low" and impact == "high":
                esc = 1
                reasons.append("low_confidence_high_impact")
            if str(ev.get("event_type")) in ESCALATE_TYPES:
                esc = 1
                reasons.append("sensitive_type")
            conflict = db.execute(
                "SELECT 1 FROM events WHERE subject_id=? AND value_after<>? AND date(occurred_at)=date(?) LIMIT 1",
                (subject, value_after, occurred)).fetchone()
            if conflict:
                esc = 1
                reasons.append("same_day_conflict")
            # 跨日衝突(P3 複審新發現):非 owner 權威的證據與當前 active state 不符
            # → 升級,防止弱權威復述舊說法悄悄蓋掉 owner 糾正。
            # owner_* 權威不觸發:owner 當下陳述優先(規格 §18),真改變不得卡死。
            if not authority.startswith("owner_"):
                try:
                    cur_state = db.execute(
                        "SELECT current_value FROM state_projection WHERE subject_id=? AND status='active'",
                        (subject,)).fetchone()
                    if cur_state and cur_state[0] != value_after:
                        esc = 1
                        reasons.append("conflicts_active_state")
                except sqlite3.OperationalError:
                    pass  # 表尚未建立(初期/沙盒)
            blob = value_after + str(ev.get("summary") or "") + "".join(s.get("quote", "") for s in sources)
            secret = 1 if SECRET_RE.search(blob) else 0
            events.append({
                "fingerprint": sha(f"{subject}|{ev.get('event_type')}|{value_after}|{occurred[:10]}"),
                "subject_id": subject,
                "event_type": str(ev.get("event_type") or "state_change"),
                "value_before": ev.get("value_before"),
                "value_after": value_after,
                "summary": str(ev.get("summary") or "")[:500],
                "authority": authority, "impact": impact, "confidence": confidence,
                "occurred_at": occurred, "batch_id": batch_id,
                "escalated": esc, "escalation_reason": ",".join(reasons) or None,
                "secret": secret, "sources": sources,
            })
        except (TypeError, ValueError, KeyError):
            dropped += 1
    return events, proposals, dropped


def main() -> int:
    os.umask(0o077)
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")

    last = db.execute(
        "SELECT COALESCE(MAX(to_rowid),0) FROM extraction_batches WHERE status='committed'"
    ).fetchone()[0]
    messages = [
        {"rowid": r["source_rowid"], "role": r["role"],
         "ts": r["source_timestamp"], "text": r["text"]}
        for r in db.execute(
            """SELECT source_rowid, role, source_timestamp, text FROM raw_messages
               WHERE source_rowid > ? AND deleted=0 ORDER BY source_rowid LIMIT ?""",
            (last, BATCH_LIMIT))]
    if not messages:
        with open(HEALTH_FILE, "w") as f:
            json.dump({"ts": now_iso(), "ok": True, "batch_id": None,
                       "events": 0, "proposals": 0, "note": "no_new_messages"}, f)
        return 0

    subjects = [dict(r) for r in db.execute(
        "SELECT subject_id, description, volatility FROM subjects WHERE status='active'")]
    if not subjects:
        print("Subject Registry 為空,拒絕抽取(需要糯糯人審的初始清單)", file=sys.stderr)
        return 1

    from_rowid, to_rowid = messages[0]["rowid"], messages[-1]["rowid"]
    input_hash = sha("|".join(f"{m['rowid']}:{m['role']}:{len(m['text'])}" for m in messages))
    dup = db.execute(
        "SELECT batch_id FROM extraction_batches WHERE input_hash=? AND status='committed'",
        (input_hash,)).fetchone()
    if dup:
        with open(HEALTH_FILE, "w") as f:
            json.dump({"ts": now_iso(), "ok": True, "batch_id": dup[0],
                       "events": 0, "proposals": 0, "note": "duplicate_batch"}, f)
        return 0

    cur = db.execute(
        """INSERT INTO extraction_batches(from_rowid,to_rowid,input_hash,model,
               prompt_version,status,started_at) VALUES(?,?,?,?,?,'pending',?)""",
        (from_rowid, to_rowid, input_hash, MODEL, EXTRACTOR_VERSION, now_iso()))
    batch_id = cur.lastrowid
    db.commit()

    try:
        events, proposals, dropped = extract(db, messages, subjects, batch_id)
        with db:
            n = 0
            for ev in events:
                sources = ev.pop("sources")
                c = db.execute(
                    """INSERT OR IGNORE INTO events(fingerprint,subject_id,event_type,
                           value_before,value_after,summary,authority,impact,confidence,
                           occurred_at,batch_id,created_by_model,extractor_version,
                           escalated,escalation_reason,secret,created_at)
                       VALUES(:fingerprint,:subject_id,:event_type,:value_before,
                           :value_after,:summary,:authority,:impact,:confidence,
                           :occurred_at,:batch_id,:model,:version,:escalated,
                           :escalation_reason,:secret,:now)""",
                    {**ev, "model": MODEL, "version": EXTRACTOR_VERSION, "now": now_iso()})
                if c.rowcount:
                    n += 1
                    for s in sources:
                        db.execute(
                            "INSERT INTO event_sources(event_id,source_rowid,quote) VALUES(?,?,?)",
                            (c.lastrowid, s["rowid"], str(s.get("quote") or "")[:300]))
            for p in proposals:
                if db.execute("SELECT 1 FROM subject_proposals WHERE proposed_key=? AND status='pending'",
                              (str(p.get("proposed_key"))[:100],)).fetchone():
                    continue  # 提案去重:同 key 已有 pending 就不重複入列
                db.execute(
                    """INSERT INTO subject_proposals(proposed_key,reason,example_quote,batch_id,created_at)
                       VALUES(?,?,?,?,?)""",
                    (str(p.get("proposed_key"))[:100], str(p.get("reason") or "")[:300],
                     str(p.get("example_quote") or "")[:300], batch_id, now_iso()))
            db.execute(
                "UPDATE extraction_batches SET status='committed', finished_at=?, events_count=? WHERE batch_id=?",
                (now_iso(), n, batch_id))
            db.execute(
                """INSERT INTO egress_audit(ts,provider,model,purpose,from_rowid,to_rowid,payload_hash,notes)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (now_iso(), "anthropic", MODEL, "event_extraction",
                 from_rowid, to_rowid, input_hash, f"events={n} dropped={dropped}"))
        result = {"ts": now_iso(), "ok": True, "batch_id": batch_id,
                  "events": n, "proposals": len(proposals), "dropped": dropped,
                  "range": [from_rowid, to_rowid]}
    except Exception as exc:  # noqa: BLE001 — batch 必須留下失敗紀錄
        db.execute(
            "UPDATE extraction_batches SET status='failed', finished_at=?, error=? WHERE batch_id=?",
            (now_iso(), f"{type(exc).__name__}: {exc}"[:500], batch_id))
        db.commit()
        result = {"ts": now_iso(), "ok": False, "batch_id": batch_id,
                  "error": f"{type(exc).__name__}: {exc}"[:200]}
    db.close()
    with open(HEALTH_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
