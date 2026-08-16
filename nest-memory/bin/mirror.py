#!/usr/bin/env python3
"""Nest Memory — Raw Mirror (shadow, append-only sidecar).

讀 version-bridge conversations.db(唯讀),把 insert/update/delete 以
append-only JSONL 落到 /srv/nest-memory/raw/。不改動任何生產程式。

執行身份:root(conversations.db 為 root 0600;Phase 0 註記,後續遷移)。
輸出檔案:0600,目錄 0700,owner nestmemory。
"""
import fcntl
import hashlib
import json
import os
import pwd
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

SRC = "/root/chatnest-next/data/version-bridge/conversations.db"
BASE = "/srv/nest-memory"
RAW_DIR = f"{BASE}/raw"
STATE_FILE = f"{BASE}/state/mirror_state.json"
LOCK_FILE = f"{BASE}/state/mirror.lock"
HEALTH_FILE = f"{BASE}/health/mirror_last_run.json"
TABLES = ["store_meta", "conversations", "session_aliases", "messages", "message_branches"]
TZ = timezone(timedelta(hours=8))

NEST_UID = pwd.getpwnam("nestmemory").pw_uid
NEST_GID = pwd.getpwnam("nestmemory").pw_gid


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="microseconds")


def own(path: str) -> None:
    os.chown(path, NEST_UID, NEST_GID)


def row_hash(row: dict) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def main() -> int:
    os.umask(0o077)
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0  # 前一輪還在跑,跳過

    started = now_iso()
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)

    db = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row

    records = []
    counts = {"insert": 0, "update": 0, "delete": 0}
    for table in TABLES:
        tstate = state.setdefault(table, {"hashes": {}})
        hashes = tstate["hashes"]
        seen = set()
        for r in db.execute(f'SELECT rowid AS __rowid, * FROM "{table}" ORDER BY rowid'):
            row = dict(r)
            rowid = str(row.pop("__rowid"))
            seen.add(rowid)
            h = row_hash(row)
            if rowid not in hashes:
                op = "insert"
            elif hashes[rowid] != h:
                op = "update"
            else:
                continue
            hashes[rowid] = h
            counts[op] += 1
            records.append(
                {"captured_at": now_iso(), "table": table, "op": op,
                 "rowid": int(rowid), "row": row}
            )
        for gone in [k for k in hashes if k not in seen]:
            del hashes[gone]
            counts["delete"] += 1
            records.append(
                {"captured_at": now_iso(), "table": table, "op": "delete",
                 "rowid": int(gone)}
            )
    db.close()

    if records:
        out_path = f"{RAW_DIR}/raw-{datetime.now(TZ):%Y%m%d}.jsonl"
        existed = os.path.exists(out_path)
        with open(out_path, "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        if not existed:
            os.chmod(out_path, 0o600)
            own(out_path)

    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)
    own(STATE_FILE)

    with open(HEALTH_FILE, "w") as f:
        json.dump({"ts": started, "ok": True, **counts}, f)
    own(HEALTH_FILE)
    own(LOCK_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
