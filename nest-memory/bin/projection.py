#!/usr/bin/env python3
"""Nest Memory — Phase 3 State Projection(確定性投影,無 LLM)。

State 是 Event Ledger 的 materialized projection(規格 §15):
每次執行 = 全量重算(刪掉重建),正典永遠在 events。
鐵則(Phase 2 複審交接):escalated=1 的 event 不得直接生成 active state——
  最新合格事件之後若有 escalated 衝突證據 → active 降為 disputed;
  某 subject 只有 escalated 證據 → tentative。
freshness 由 subject volatility + last_confirmed_at 計算(§17)。
以 nestmemory 身份執行。
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

DB = "/srv/nest-memory/db/memory.db"
HEALTH_FILE = "/srv/nest-memory/health/projection_last_run.json"
TZ = timezone(timedelta(hours=8))


def now() -> datetime:
    return datetime.now(TZ)


def parse_ts(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value))
        return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt
    except ValueError:
        return now()


def freshness_of(last_confirmed: datetime, review_days, stale_days) -> str:
    age = (now() - last_confirmed).days
    if stale_days and age > stale_days:
        return "stale_active"
    if review_days and age > review_days:
        return "active_aging"
    return "active_fresh"


def project(db) -> dict:
    subjects = {r["subject_id"]: dict(r) for r in db.execute(
        "SELECT subject_id, volatility, review_after_days, stale_after_days "
        "FROM subjects WHERE status='active'")}
    rows = db.execute(
        "SELECT event_id, subject_id, value_after, summary, authority, escalated, "
        "occurred_at FROM events ORDER BY occurred_at, event_id").fetchall()
    by_subject = {}
    for r in rows:
        by_subject.setdefault(r["subject_id"], []).append(r)

    projected, counts = [], {"active": 0, "tentative": 0, "disputed": 0}
    for sid, evs in by_subject.items():
        if sid not in subjects:
            continue  # subject 已退役,歷史事件保留於 ledger,不投影
        meta = subjects[sid]
        eligible = [e for e in evs if not e["escalated"]]
        if eligible:
            src = eligible[-1]
            status = "active"
            # 最新合格事件之後仍有 escalated 衝突證據 → disputed
            later_esc = [e for e in evs if e["escalated"]
                         and (e["occurred_at"], e["event_id"]) >
                             (src["occurred_at"], src["event_id"])
                         and e["value_after"] != src["value_after"]]
            if later_esc:
                status = "disputed"
            # 後續相同值的合格事件 = 再確認
            confirms = [e for e in eligible if e["value_after"] == src["value_after"]]
            last_confirmed = parse_ts(confirms[-1]["occurred_at"])
        else:
            src = evs[-1]
            status = "tentative"
            last_confirmed = parse_ts(src["occurred_at"])
        fresh = (freshness_of(last_confirmed, meta["review_after_days"],
                              meta["stale_after_days"])
                 if status == "active" else status)
        counts[status] += 1
        projected.append((
            sid, src["value_after"], src["summary"], src["event_id"],
            src["authority"], status, src["occurred_at"],
            last_confirmed.isoformat(timespec="seconds"), fresh,
            now().isoformat(timespec="seconds")))
    return projected, counts


def main() -> int:
    os.umask(0o077)
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    # state_projection schema 由 migrate.py v3 版本化管理(P3 複審補交①)
    try:
        projected, counts = project(db)
        with db:
            db.execute("DELETE FROM state_projection")  # 全量重算:events 才是正典
            db.executemany(
                """INSERT INTO state_projection(subject_id, current_value, summary,
                       source_event_id, authority, status, observed_at,
                       last_confirmed_at, freshness, computed_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""", projected)
        result = {"ts": now().isoformat(timespec="seconds"), "ok": True,
                  "subjects_projected": len(projected), **counts,
                  "rebuild": "full"}
    except Exception as exc:  # noqa: BLE001 — 失敗必留紀錄
        result = {"ts": now().isoformat(timespec="seconds"), "ok": False,
                  "error": f"{type(exc).__name__}: {exc}"[:200]}
    db.close()
    with open(HEALTH_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
