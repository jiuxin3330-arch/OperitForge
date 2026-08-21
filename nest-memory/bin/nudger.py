#!/usr/bin/env python3
"""Nest Memory — 記憶小紙條(工單 A,IMPLEMENTATION §7 規則 3 的兌現)。

兜底不代筆:當日 events 有重要事件、但 chat 牧牧沒呼叫 store_memory 寫日記時,
產一條貼條提醒他自己去記。**只提醒、不代擬記憶內容。**

- 身份:nestmemory(與 extractor 相同)。
- 排程:03:35(extractor 03:30 之後,projection 03:40 之前)。
- 出口:/srv/nest-memory/serving/nudge_pending.txt(單檔覆寫,寧漏勿煩)。
  由 P4 已建立的 serving ACL 走廊供 chatagent 讀,無新權限面。
- 消費紀錄由 bridge/chatagent 端管理,本檔只負責寫入最新一條。
- 觸發條件(所有需成立):
    * 今日(台北時區日期)events 中至少一條 impact ∈ {medium,high}、escalated=0
    * 當日 chat 牧牧 store_memory 呼叫次數 == 0
- 挑選:high 優先,同 impact 挑最新一條;fingerprint = event_id(數字即可)。
- 頻率上限:單檔覆寫 → 一天最多一條(即使觸發也只留最新一條)。
- 不觸發或條件不成立時:清空 nudge_pending.txt(避免舊貼條留存過久)。
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

DB = "/srv/nest-memory/db/memory.db"
OUT = "/srv/nest-memory/serving/nudge_pending.txt"
STATUS = "/srv/nest-memory/health/nudge_last_run.json"
TZ = timezone(timedelta(hours=8))


def today_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def build_nudge_text(event) -> str:
    """描述事件的貼條,不代擬記憶內容(§7 鐵律 3)。"""
    label = event["summary"] or event["value_after"] or event["subject_id"]
    label = str(label).replace("\n", " ").strip()[:80]
    return (f"〔小紙條・來自檔案室〕今天發生了一件事:{label}"
            f"(主題:{event['subject_id']})。要不要自己寫一筆日記記下來?"
            "怎麼記由你決定,檔案室不會代筆。")


def main() -> int:
    os.umask(0o077)
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    today = today_str()

    events = db.execute(
        """SELECT event_id, subject_id, impact, value_after, summary, created_at
           FROM events
           WHERE impact IN ('medium','high') AND escalated = 0 AND secret = 0
             AND substr(created_at,1,10) = ?
           ORDER BY CASE impact WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                    event_id DESC""",
        (today,)).fetchall()

    memory_writes = db.execute(
        """SELECT COUNT(*) FROM raw_messages
           WHERE role='assistant' AND deleted=0
             AND traces_json LIKE '%mcp__anchor__store_memory%'
             AND substr(source_timestamp,1,10) = ?""",
        (today,)).fetchone()[0]
    db.close()

    should_nudge = bool(events) and memory_writes == 0
    picked = events[0] if should_nudge else None

    if picked is not None:
        text = build_nudge_text(picked)
        tmp = OUT + ".tmp"
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(f"{picked['event_id']}\t{text}\n")
        os.chmod(tmp, 0o644)  # 走 serving ACL 走廊,chatagent 讀
        os.replace(tmp, OUT)
    elif os.path.exists(OUT):
        # 沒新貼條要發:清掉舊的(過期貼條就別留了)
        os.remove(OUT)

    result = {
        "ts": datetime.now(TZ).isoformat(timespec="seconds"),
        "ok": True,
        "today": today,
        "events_today": len(events),
        "memory_writes_today": memory_writes,
        "nudged": picked is not None,
        "picked_event_id": picked["event_id"] if picked is not None else None,
    }
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
