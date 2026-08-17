#!/usr/bin/env python3
"""Nest Memory — schema migration(硬規則:schema 變更走版本化 migration)。

用法: migrate.py            套用所有未套用的版本
      migrate.py --status   只看目前版本
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

DB = "/srv/nest-memory/db/memory.db"
TZ = timezone(timedelta(hours=8))

MIGRATIONS = [
    (1, "initial_raw_layer", """
CREATE TABLE raw_messages (
    nest_msg_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    source_rowid    INTEGER NOT NULL UNIQUE,
    conv_id         TEXT NOT NULL,
    source_id       TEXT,
    role            TEXT NOT NULL,
    text            TEXT NOT NULL DEFAULT '',
    thinking        TEXT NOT NULL DEFAULT '',
    attachments_json TEXT NOT NULL DEFAULT '[]',
    traces_json     TEXT NOT NULL DEFAULT '[]',
    edited          INTEGER NOT NULL DEFAULT 0,
    source_timestamp TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    first_captured_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT
);
CREATE INDEX idx_raw_messages_conv ON raw_messages(conv_id, source_rowid);
CREATE INDEX idx_raw_messages_ts ON raw_messages(source_timestamp);

CREATE TABLE raw_message_revisions (
    rev_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_rowid INTEGER NOT NULL,
    op           TEXT NOT NULL CHECK(op IN ('insert','update','delete')),
    captured_at  TEXT NOT NULL,
    row_json     TEXT
);
CREATE INDEX idx_raw_msg_rev_rowid ON raw_message_revisions(source_rowid, rev_id);

CREATE TABLE raw_aux_rows (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_rowid INTEGER NOT NULL,
    row_json     TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    first_captured_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    deleted      INTEGER NOT NULL DEFAULT 0,
    deleted_at   TEXT,
    UNIQUE(source_table, source_rowid)
);

CREATE TABLE raw_aux_revisions (
    rev_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_rowid INTEGER NOT NULL,
    op           TEXT NOT NULL CHECK(op IN ('insert','update','delete')),
    captured_at  TEXT NOT NULL,
    row_json     TEXT
);

CREATE TABLE conv_map (
    bridge_conv_id TEXT PRIMARY KEY,
    nest_conv_uid  TEXT NOT NULL UNIQUE,
    created_at     TEXT NOT NULL
);
"""),
    (2, "event_extraction_layer", """
CREATE TABLE subjects (
    subject_id   TEXT PRIMARY KEY,
    description  TEXT NOT NULL DEFAULT '',
    volatility   TEXT NOT NULL CHECK(volatility IN ('stable','semi_stable','volatile','ephemeral')),
    review_after_days INTEGER,
    stale_after_days  INTEGER,
    serving_behavior  TEXT NOT NULL DEFAULT 'normal',
    status       TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','retired')),
    approved_by  TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);

CREATE TABLE entities (
    entity_id      TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    type           TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE TABLE entity_aliases (
    alias     TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id)
);

CREATE TABLE extraction_batches (
    batch_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    from_rowid INTEGER NOT NULL,
    to_rowid   INTEGER NOT NULL,
    input_hash TEXT NOT NULL,
    model      TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    status     TEXT NOT NULL CHECK(status IN ('pending','committed','failed')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error      TEXT,
    events_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE events (
    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint  TEXT NOT NULL UNIQUE,
    subject_id   TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    value_before TEXT,
    value_after  TEXT NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    authority    TEXT NOT NULL,
    impact       TEXT NOT NULL CHECK(impact IN ('low','medium','high')),
    confidence   TEXT NOT NULL CHECK(confidence IN ('low','medium','high')),
    occurred_at  TEXT NOT NULL,
    batch_id     INTEGER NOT NULL REFERENCES extraction_batches(batch_id),
    created_by_model  TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    escalated    INTEGER NOT NULL DEFAULT 0,
    escalation_reason TEXT,
    secret       INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_events_subject ON events(subject_id, occurred_at);
CREATE INDEX idx_events_batch ON events(batch_id);

CREATE TABLE event_sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     INTEGER NOT NULL REFERENCES events(event_id),
    source_rowid INTEGER NOT NULL,
    quote        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_event_sources_event ON event_sources(event_id);

CREATE TABLE subject_proposals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    proposed_key TEXT NOT NULL,
    reason       TEXT NOT NULL DEFAULT '',
    example_quote TEXT NOT NULL DEFAULT '',
    batch_id     INTEGER,
    status       TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_at   TEXT NOT NULL
);

CREATE TABLE egress_audit (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    provider   TEXT NOT NULL,
    model      TEXT NOT NULL,
    purpose    TEXT NOT NULL,
    from_rowid INTEGER,
    to_rowid   INTEGER,
    payload_hash TEXT NOT NULL,
    notes      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE golden_cases (
    case_id  TEXT PRIMARY KEY,
    title    TEXT NOT NULL,
    fixture_json     TEXT NOT NULL,
    expectation_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE golden_runs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    model   TEXT NOT NULL,
    passed  INTEGER NOT NULL,
    failed  INTEGER NOT NULL,
    details_json TEXT NOT NULL
);
"""),
    (3, "state_projection", """
CREATE TABLE IF NOT EXISTS state_projection (
    subject_id        TEXT PRIMARY KEY,
    current_value     TEXT NOT NULL,
    summary           TEXT NOT NULL DEFAULT '',
    source_event_id   INTEGER NOT NULL,
    authority         TEXT NOT NULL,
    status            TEXT NOT NULL,
    observed_at       TEXT NOT NULL,
    last_confirmed_at TEXT NOT NULL,
    freshness         TEXT NOT NULL,
    computed_at       TEXT NOT NULL
);
"""),
]


def main() -> int:
    os.umask(0o077)
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    db = sqlite3.connect(DB)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)""")
    applied = {r[0] for r in db.execute("SELECT version FROM schema_migrations")}
    if "--status" in sys.argv:
        print(f"applied: {sorted(applied)} / available: {[v for v, _, _ in MIGRATIONS]}")
        return 0
    for version, name, sql in MIGRATIONS:
        if version in applied:
            continue
        with db:
            db.executescript(sql)
            db.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES(?,?,?)",
                (version, name, datetime.now(TZ).isoformat()),
            )
        print(f"applied {version}:{name}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
