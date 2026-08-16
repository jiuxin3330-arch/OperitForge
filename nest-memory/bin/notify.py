#!/usr/bin/env python3
"""Nest Memory — notification sink(借用 chatnest-next 既有推播管道)。

用法: notify.py "標題" "內容"
以 owner / proactive 類別入列 push_outbox + native_push_outbox,
由 backend 的 delivery loop 實際送出。必須用 backend venv 的 python 執行:
/root/chatnest-next/.venv/bin/python
"""
import sqlite3
import sys

sys.path.insert(0, "/root/chatnest-next/backend")

from app.notification_outbox import enqueue_notification  # noqa: E402

DB = "/root/chatnest-next/data/app.sqlite3"


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: notify.py TITLE BODY", file=sys.stderr)
        return 2
    title, body = sys.argv[1], sys.argv[2]
    conn = sqlite3.connect(DB, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        result = enqueue_notification(
            conn,
            user_id="owner",
            category="proactive",
            title=title,
            visible_text=body,
            target_url="/",
            resource_id="nest-memory-health",
            quiet=False,
        )
        conn.commit()
    finally:
        conn.close()
    print(result)
    return 0 if result.get("queued", 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
