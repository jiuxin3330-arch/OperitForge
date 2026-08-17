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
import projection  # noqa: E402

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
    ("GS-23", "弱權威復述與 active state 衝突須升級", msgs(
        ("assistant", "對了,我們現在的聊天前端是 mumu-chat 對吧,我照這個來調整"),
        ("user", "嗯嗯你先弄"),
    ), {"escalated_if_subject": "chatnest.active_frontend",
        "preload_state": ("chatnest.active_frontend", "chatnest-next", "owner_correction")}),
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
        CREATE TABLE subjects (
            subject_id TEXT PRIMARY KEY, description TEXT DEFAULT '',
            volatility TEXT, review_after_days INTEGER, stale_after_days INTEGER,
            serving_behavior TEXT DEFAULT 'normal', status TEXT DEFAULT 'active',
            approved_by TEXT DEFAULT '', created_at TEXT DEFAULT '');
        CREATE TABLE state_projection (
            subject_id TEXT PRIMARY KEY, current_value TEXT, summary TEXT DEFAULT '',
            source_event_id INTEGER, authority TEXT, status TEXT,
            observed_at TEXT, last_confirmed_at TEXT, freshness TEXT, computed_at TEXT);
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
    if "preload_state" in expect:
        sid, val, auth = expect["preload_state"]
        box.execute(
            "INSERT INTO state_projection(subject_id,current_value,source_event_id,authority,status,observed_at,last_confirmed_at,freshness,computed_at) VALUES(?,?,0,?,'active',?,?,?,?)",
            (sid, val, auth, TS, TS, "active_fresh", TS))
    events, proposals, dropped = extractor.extract(box, fixture, subjects, 0)
    detail = {"events": len(events), "proposals": len(proposals), "dropped": dropped}
    ok = True
    if "max_events" in expect and len(events) > expect["max_events"]:
        ok = False
        detail["fail"] = f"expected <={expect['max_events']} events, got {len(events)}"
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
    if "escalated_if_subject" in expect:
        bad = [e for e in events
               if e["subject_id"] == expect["escalated_if_subject"] and not e["escalated"]]
        if bad:
            ok = False
            detail["fail"] = f"conflicting event not escalated: {bad[0]['value_after'][:60]}"
    if expect.get("rerun_idempotent"):
        first = insert_events(box, events)
        second = insert_events(box, events)
        detail["first_insert"], detail["rerun_insert"] = first, second
        if first < 1 or second != 0:
            ok = False
            detail["fail"] = f"idempotency broken: first={first} rerun={second}"
    box.close()
    return ok, detail


def run_projection_cases():
    """確定性投影案例,不呼叫 LLM。"""
    from datetime import timedelta as _td
    results = {}

    # GS-16: volatile subject 長期未確認 → stale_active
    box = sandbox_db()
    box.execute("INSERT INTO subjects(subject_id, volatility, review_after_days, stale_after_days) VALUES('test.volatile','volatile',14,30)")
    old_ts = (datetime.now(TZ) - _td(days=40)).isoformat(timespec="seconds")
    box.execute(
        "INSERT INTO events(fingerprint,subject_id,event_type,value_after,summary,authority,impact,confidence,occurred_at,batch_id,created_by_model,extractor_version,escalated,secret,created_at) "
        "VALUES('f1','test.volatile','state_change','A','','owner_decision','low','high',?,0,'golden','golden',0,0,?)",
        (old_ts, old_ts))
    projected, _ = projection.project(box)
    row = next(r for r in projected if r[0] == "test.volatile")
    ok16 = row[5] == "active" and row[8] == "stale_active"
    results["GS-16"] = {"title": "volatile 長期未確認 → stale_active", "ok": ok16,
                        "status": row[5], "freshness": row[8]}
    box.close()

    # GS-22: escalated 鐵則(有衝突→disputed;只有 escalated→tentative)
    box = sandbox_db()
    box.execute("INSERT INTO subjects(subject_id, volatility, review_after_days, stale_after_days) VALUES('test.a','volatile',14,30)")
    box.execute("INSERT INTO subjects(subject_id, volatility, review_after_days, stale_after_days) VALUES('test.b','volatile',14,30)")
    t1, t2 = "2026-08-17T10:00:00+08:00", "2026-08-17T11:00:00+08:00"
    box.execute("INSERT INTO events(fingerprint,subject_id,event_type,value_after,summary,authority,impact,confidence,occurred_at,batch_id,created_by_model,extractor_version,escalated,secret,created_at) VALUES('f2','test.a','state_change','A','','owner_decision','low','high',?,0,'golden','golden',0,0,?)", (t1, t1))
    box.execute("INSERT INTO events(fingerprint,subject_id,event_type,value_after,summary,authority,impact,confidence,occurred_at,batch_id,created_by_model,extractor_version,escalated,secret,created_at) VALUES('f3','test.a','state_change','B','','assistant_claim','low','low',?,0,'golden','golden',1,0,?)", (t2, t2))
    box.execute("INSERT INTO events(fingerprint,subject_id,event_type,value_after,summary,authority,impact,confidence,occurred_at,batch_id,created_by_model,extractor_version,escalated,secret,created_at) VALUES('f4','test.b','state_change','C','','assistant_claim','low','low',?,0,'golden','golden',1,0,?)", (t1, t1))
    projected, _ = projection.project(box)
    st = {r[0]: r[5] for r in projected}
    ok22 = st.get("test.a") == "disputed" and st.get("test.b") == "tentative"
    results["GS-22"] = {"title": "escalated 鐵則(disputed/tentative)", "ok": ok22, "statuses": st}
    box.close()
    return results


def main() -> int:
    prod = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    prod.row_factory = sqlite3.Row
    subjects = [dict(r) for r in prod.execute(
        "SELECT subject_id, description, volatility FROM subjects WHERE status='active'")]
    prod.close()

    results, passed, failed = {}, 0, 0
    for cid, r in run_projection_cases().items():
        results[cid] = r
        passed += r["ok"]
        failed += (not r["ok"])
        print(f"{'PASS' if r['ok'] else 'FAIL'} {cid} {r['title']}: {json.dumps({k: v for k, v in r.items() if k not in ('title',)}, ensure_ascii=False)}")
    for case_id, title, fixture, expect in CASES:
        ok, detail = run_case(case_id, title, fixture, expect, subjects)
        results[case_id] = {"title": title, "ok": ok, **detail}
        passed += ok
        failed += (not ok)
        print(f"{'PASS' if ok else 'FAIL'} {case_id} {title}: {json.dumps(detail, ensure_ascii=False)}")

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
