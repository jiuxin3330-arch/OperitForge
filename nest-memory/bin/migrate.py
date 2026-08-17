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
