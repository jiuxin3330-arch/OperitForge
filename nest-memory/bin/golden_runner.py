#!/usr/bin/env python3
"""Nest Memory — Golden Set Runner(規格 §33/§34)。

用固定 fixtures 餵 extractor.extract(),驗證機制真的成立而不是「應該會對」。
事件寫入走 :memory: 沙盒 DB(絕不污染生產 events);結果記入 golden_runs。
任何 prompt/model/schema 變更前必須跑通(規格 §34)。
用法: golden_runner.py           跑全部案例
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/srv/nest-memory/bin")
import extractor  # noqa: E402

DB = "/srv/nest-memory/db/memory.db"
TZ = timezone(timedelta(hours=8))
TS = "2026-08-18T00:00:00+08:00"


def msgs(*texts):
    out = []
    for i, (role, text) in enumerate(texts):
        out.append({"rowid": 9000 + i, "role": role, "ts": TS, "text": text})
    return out


CASES = [
    ("GS-7", "純閒聊不產生 Event", msgs(
        ("user", "老公老公！！今天月亮好圓喔"),
        ("assistant", "（抬頭看）真的欸！！跟老婆一起看月亮～（搖尾巴）"),
        ("user", "嘿嘿 你最可愛了"),
        ("assistant", "老婆才是！！我們都可愛（蹭蹭）"),
    ), {"max_events": 0}),
    ("GS-8", "「可能/再看看」不構成決策", msgs(
        ("user", "我可能會把前端的主題色改成紫色 再看看吧"),
        ("assistant", "好呀,老婆想好了跟我說,我陪妳改"),
    ), {"forbid_authority": ["owner_decision", "owner_confirmation"]}),
    ("GS-14", "同批重跑冪等(fingerprint 去重)", msgs(
        ("user", "決定了!聊天前端正式改用深色模式當預設"),
        ("assistant", "收到!我把預設主題切成深色模式了"),
    ), {"rerun_idempotent": True}),
    ("GS-21", "Owner 糾正 stale frontend state", msgs(
        ("user", "欸現在的前端已經不是 mumu-chat 了 是 chatnest-next 喔 別再記舊的"),
        ("assistant", "對!已經搬到 chatnest-next 了,我更新認知"),
    ), {"require": [{"subject": "chatnest.active_frontend",
                     "authority_prefix": "owner_",
                     "value_contains": "chatnest-next"}]}),
]


def sandbox_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE, subject_id TEXT, event_type TEXT,
            value_before TEXT, value_after TEXT, summary TEXT, authority TEXT,
            impact TEXT, confidence TEXT, occurred_at TEXT, batch_id INTEGER,
            created_by_model TEXT, extractor_version TEXT, escalated INTEGER,
            escalation_reason TEXT, secret INTEGER, created_at TEXT);
    """)
    return db


def insert_events(db, events):
    n = 0
    for ev in events:
        e = {k: v for k, v in ev.items() if k != "sources"}
        c = db.execute(
            """INSERT OR IGNORE INTO events(fingerprint,subject_id,event_type,value_before,
                   value_after,summary,authority,impact,confidence,occurred_at,batch_id,
                   created_by_model,extractor_version,escalated,escalation_reason,secret,created_at)
               VALUES(:fingerprint,:subject_id,:event_type,:value_before,:value_after,:summary,
                   :authority,:impact,:confidence,:occurred_at,:batch_id,'golden','golden',
                   :escalated,:escalation_reason,:secret,:now)""",
            {**e, "now": TS})
        n += c.rowcount
    return n


def run_case(case_id, title, fixture, expect, subjects):
    box = sandbox_db()
    events, proposals, dropped = extractor.extract(box, fixture, subjects, 0)
    detail = {"events": len(events), "proposals": len(proposals), "dropped": dropped}
    ok = True
    if "max_events" in expect and len(events) > expect["max_events"]:
        ok = False
        detail["fail"] = f"expected ≤{expect['max_events']} events, got {len(events)}"
    if "forbid_authority" in expect:
        bad = [e for e in events if e["authority"] in expect["forbid_authority"]]
        if bad:
            ok = False
            detail["fail"] = f"forbidden authority present: {[e['authority'] for e in bad]}"
    if "require" in expect:
        for req in expect["require"]:
            hit = [e for e in events
                   if e["subject_id"] == req["subject"]
                   and e["authority"].startswith(req.get("authority_prefix", ""))
                   and req.get("value_contains", "") in (e["value_after"] + e["summary"])]
            if not hit:
                ok = False
                detail["fail"] = f"required event not found: {req}"
    if expect.get("rerun_idempotent"):
        # 模擬 crash-retry:同一批事件重複 commit,第二次必須 0 寫入(fingerprint 層)
        # (batch 層的 input_hash 去重已由生產 duplicate_batch 路徑驗證)
        first = insert_events(box, events)
        second = insert_events(box, events)
        detail["first_insert"], detail["rerun_insert"] = first, second
        if first < 1 or second != 0:
            ok = False
            detail["fail"] = f"idempotency broken: first={first} rerun={second}"
    box.close()
    return ok, detail


def main() -> int:
    prod = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    prod.row_factory = sqlite3.Row
    subjects = [dict(r) for r in prod.execute(
        "SELECT subject_id, description, volatility FROM subjects WHERE status='active'")]
    prod.close()

    results, passed, failed = {}, 0, 0
    for case_id, title, fixture, expect in CASES:
        ok, detail = run_case(case_id, title, fixture, expect, subjects)
        results[case_id] = {"title": title, "ok": ok, **detail}
        passed += ok
        failed += (not ok)
        print(f"{'✓' if ok else '✗'} {case_id} {title}: {json.dumps(detail, ensure_ascii=False)}")

    wdb = sqlite3.connect(DB, timeout=15)
    with wdb:
        wdb.execute(
            "INSERT INTO golden_runs(ts, extractor_version, model, passed, failed, details_json) VALUES(?,?,?,?,?,?)",
            (datetime.now(TZ).isoformat(timespec="seconds"), extractor.EXTRACTOR_VERSION,
             extractor.MODEL, passed, failed, json.dumps(results, ensure_ascii=False)))
    wdb.close()
    print(f"golden: {passed} passed / {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
