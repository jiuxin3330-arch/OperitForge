#!/usr/bin/env python3
"""Nest Memory — Raw 完整性檢查(Phase 1 驗收:漏訊息率 = 0)。

逐列核對 conversations.db(來源)與 memory.db(raw 正典):
- 來源每一列都要在 raw_messages 且 content_hash 一致
- raw 中未標刪除的列都要仍存在於來源
結果寫 health/integrity_last.json;有問題 exit 1。
以 nestmemory 身份執行。
"""
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta

SRC = "/srv/chatnest-next/data/version-bridge/conversations.db"
DB = "/srv/nest-memory/db/memory.db"
OUT = "/srv/nest-memory/health/integrity_last.json"
AUX_TABLES = ["store_meta", "conversations", "session_aliases", "message_branches"]
TZ = timezone(timedelta(hours=8))


def row_hash(row: dict) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def main() -> int:
    os.umask(0o077)
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True, timeout=5)
    src.row_factory = sqlite3.Row
    dest = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)

    problems = {"missing": 0, "mismatched": 0, "stale_undeleted": 0}

    raw = {r[0]: (r[1], bool(r[2])) for r in dest.execute(
        "SELECT source_rowid, content_hash, deleted FROM raw_messages")}
    seen = set()
    for r in src.execute("SELECT rowid AS __rowid, * FROM messages"):
        row = dict(r)
        rowid = row.pop("__rowid")
        seen.add(rowid)
        entry = raw.get(rowid)
        if entry is None or entry[1]:
            problems["missing"] += 1
        elif entry[0] != row_hash(row):
            problems["mismatched"] += 1
    for rowid, (_, deleted) in raw.items():
        if not deleted and rowid not in seen:
            problems["stale_undeleted"] += 1

    aux_counts = {}
    for t in AUX_TABLES:
        s = src.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        d = dest.execute(
            "SELECT COUNT(*) FROM raw_aux_rows WHERE source_table=? AND deleted=0",
            (t,)).fetchone()[0]
        aux_counts[t] = {"source": s, "raw": d}
        if s != d:
            problems["mismatched"] += abs(s - d)

    src_max = src.execute("SELECT COALESCE(MAX(rowid),0) FROM messages").fetchone()[0]
    raw_max = dest.execute(
        "SELECT COALESCE(MAX(source_rowid),0) FROM raw_messages WHERE deleted=0"
    ).fetchone()[0]
    ok = not any(problems.values())
    result = {
        "ts": datetime.now(TZ).isoformat(),
        "ok": ok,
        **problems,
        "source_messages": len(seen),
        "raw_messages_active": sum(1 for _, d in raw.values() if not d),
        "lag_rows": max(0, src_max - raw_max),
        "aux": aux_counts,
    }
    src.close()
    dest.close()
    with open(OUT, "w") as f:
        json.dump(result, f, ensure_ascii=False)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
