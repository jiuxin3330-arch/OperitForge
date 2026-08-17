#!/usr/bin/env python3
"""Nest Memory — Raw Mirror v2(Phase 1:SQLite 正典 + JSONL export)。

以 nestmemory 身份執行。conversations.db 唯讀(靠 ACL),
寫入 /srv/nest-memory/db/memory.db(canon)與 raw/*.jsonl(export)。
偵測 insert/update/delete;歷次變化進 *_revisions(append-only 證據層)。
"""
import fcntl
import hashlib
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone, timedelta

SRC = "/srv/chatnest-next/data/version-bridge/conversations.db"
BASE = "/srv/nest-memory"
DB = f"{BASE}/db/memory.db"
RAW_DIR = f"{BASE}/raw"
LOCK_FILE = f"{BASE}/state/mirror.lock"
HEALTH_FILE = f"{BASE}/health/mirror_last_run.json"
AUX_TABLES = ["store_meta", "conversations", "session_aliases", "message_branches"]
TZ = timezone(timedelta(hours=8))

MSG_COLS = ["conv_id", "source_id", "role", "text", "thinking",
            "attachments_json", "traces_json", "edited", "timestamp"]


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="microseconds")


def row_hash(row: dict) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def scan_table(src, table, known, records, dest, jsonl, counts):
    """known: {rowid: (hash, deleted)} 現況;產生 ops 並寫入 dest。"""
    now = now_iso()
    seen = set()
    is_msg = table == "messages"
    for r in src.execute(f'SELECT rowid AS __rowid, * FROM "{table}" ORDER BY rowid'):
        row = dict(r)
        rowid = row.pop("__rowid")
        seen.add(rowid)
        h = row_hash(row)
        prev = known.get(rowid)
        if prev is None or prev[1]:          # 新列,或曾標刪除又出現
            op = "insert"
        elif prev[0] != h:
            op = "update"
        else:
            continue
        counts[op] += 1
        rj = json.dumps(row, ensure_ascii=False, default=str)
        if is_msg:
            dest.execute(
                """INSERT INTO raw_messages(source_rowid, conv_id, source_id, role,
                       text, thinking, attachments_json, traces_json, edited,
                       source_timestamp, content_hash, first_captured_at,
                       last_updated_at, deleted, deleted_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,NULL)
                   ON CONFLICT(source_rowid) DO UPDATE SET
                       conv_id=excluded.conv_id, source_id=excluded.source_id,
                       role=excluded.role, text=excluded.text,
                       thinking=excluded.thinking,
                       attachments_json=excluded.attachments_json,
                       traces_json=excluded.traces_json, edited=excluded.edited,
                       source_timestamp=excluded.source_timestamp,
                       content_hash=excluded.content_hash,
                       last_updated_at=excluded.last_updated_at,
                       deleted=0, deleted_at=NULL""",
                (rowid, row["conv_id"], row["source_id"], row["role"], row["text"],
                 row["thinking"], row["attachments_json"], row["traces_json"],
                 row["edited"], row["timestamp"], h, now, now),
            )
            dest.execute(
                "INSERT INTO raw_message_revisions(source_rowid, op, captured_at, row_json) VALUES(?,?,?,?)",
                (rowid, op, now, rj),
            )
            dest.execute(
                """INSERT INTO conv_map(bridge_conv_id, nest_conv_uid, created_at)
                   VALUES(?,?,?) ON CONFLICT(bridge_conv_id) DO NOTHING""",
                (row["conv_id"], uuid.uuid4().hex, now),
            )
        else:
            dest.execute(
                """INSERT INTO raw_aux_rows(source_table, source_rowid, row_json,
                       content_hash, first_captured_at, last_updated_at, deleted, deleted_at)
                   VALUES(?,?,?,?,?,?,0,NULL)
                   ON CONFLICT(source_table, source_rowid) DO UPDATE SET
                       row_json=excluded.row_json, content_hash=excluded.content_hash,
                       last_updated_at=excluded.last_updated_at, deleted=0, deleted_at=NULL""",
                (table, rowid, rj, h, now, now),
            )
            dest.execute(
                "INSERT INTO raw_aux_revisions(source_table, source_rowid, op, captured_at, row_json) VALUES(?,?,?,?,?)",
                (table, rowid, op, now, rj),
            )
        known[rowid] = (h, False)
        records.append({"captured_at": now, "table": table, "op": op,
                        "rowid": rowid, "row": row})
    for gone in [k for k, v in known.items() if k not in seen and not v[1]]:
        counts["delete"] += 1
        if is_msg:
            dest.execute(
                "UPDATE raw_messages SET deleted=1, deleted_at=? WHERE source_rowid=?",
                (now, gone))
            dest.execute(
                "INSERT INTO raw_message_revisions(source_rowid, op, captured_at, row_json) VALUES(?, 'delete', ?, NULL)",
                (gone, now))
        else:
            dest.execute(
                "UPDATE raw_aux_rows SET deleted=1, deleted_at=? WHERE source_table=? AND source_rowid=?",
                (now, table, gone))
            dest.execute(
                "INSERT INTO raw_aux_revisions(source_table, source_rowid, op, captured_at, row_json) VALUES(?,?, 'delete', ?, NULL)",
                (table, gone, now))
        known[gone] = (known[gone][0], True)
        records.append({"captured_at": now, "table": table, "op": "delete",
                        "rowid": gone})


def main() -> int:
    os.umask(0o077)
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0

    started = now_iso()
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=5)
    src.row_factory = sqlite3.Row
    dest = sqlite3.connect(DB, timeout=10)
    dest.execute("PRAGMA journal_mode=WAL")

    counts = {"insert": 0, "update": 0, "delete": 0}
    records = []
    with dest:
        known_msg = {r[0]: (r[1], bool(r[2])) for r in dest.execute(
            "SELECT source_rowid, content_hash, deleted FROM raw_messages")}
        scan_table(src, "messages", known_msg, records, dest, None, counts)
        for table in AUX_TABLES:
            known = {r[0]: (r[1], bool(r[2])) for r in dest.execute(
                "SELECT source_rowid, content_hash, deleted FROM raw_aux_rows WHERE source_table=?",
                (table,))}
            scan_table(src, table, known, records, dest, None, counts)
    src.close()
    dest.close()

    if records:
        out_path = f"{RAW_DIR}/raw-{datetime.now(TZ):%Y%m%d}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    with open(HEALTH_FILE, "w") as f:
        json.dump({"ts": started, "ok": True, **counts}, f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
