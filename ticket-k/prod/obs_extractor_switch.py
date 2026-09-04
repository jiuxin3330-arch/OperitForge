#!/usr/bin/env python3
"""extractor 模型切換觀察器(2026-08-30 規劃窗裁定:切 Sonnet 5 後觀察 7 天)。

每日 cron(extractor 之後)執行:統計當日 batch 的 events/proposals/escalated,
對照 Haiku 期基線(20 批,6.05 events/批,escalated 24.8%),異常推播告警。
觀察期:2026-08-31 ~ 2026-09-06;期滿發總結推播後自動安靜(仍寫 log)。

TICKET-K(2026-09-03):原本這裡會建議「回切 Haiku」。已證實那個建議不成立
——「events 被包成 JSON 字串」是 Sonnet 5 與 Haiku 4.5 都會偶發的格式抖動
(同一批訊息重跑,Haiku 那次的 JSON 本身還壞在 char 3483),不是哪個模型特有。
換模型救不了這件事,extractor 的 _unwrap_container 才是。所以建議已移除。
"""
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

DB = "/srv/nest-memory/db/memory.db"
TZ = timezone(timedelta(hours=8))
LOG = "/srv/nest-memory/health/model_switch_watch.jsonl"
WATCH_END = "2026-09-06"
BASELINE = {"events_per_batch": 6.05, "escalated_ratio": 0.248}
NOTIFY = ["/root/chatnest-next/.venv/bin/python", "/srv/nest-memory/bin/notify.py"]


def notify(title, body):
    try:
        subprocess.run(NOTIFY + [title, body], timeout=30, capture_output=True)
    except Exception as e:
        print(f"notify failed: {e}", file=sys.stderr)


def main() -> int:
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    batches = db.execute(
        "SELECT batch_id, model, status, events_count, error FROM extraction_batches "
        "WHERE started_at LIKE ? AND model LIKE 'claude-%'", (today + "%",)).fetchall()
    ev = db.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(escalated),0) esc FROM events "
        "WHERE created_at LIKE ? AND created_by_model LIKE 'claude-%'", (today + "%",)).fetchone()
    props = db.execute(
        "SELECT COUNT(*) FROM subject_proposals WHERE created_at LIKE ?", (today + "%",)).fetchone()[0]
    # 當日待抽 raw 量(有料才該有產出)
    last_ok = db.execute(
        "SELECT COALESCE(MAX(to_rowid),0) FROM extraction_batches WHERE status='committed'").fetchone()[0]
    pending_raw = db.execute(
        "SELECT COUNT(*) FROM raw_messages WHERE source_rowid > ? AND deleted=0", (last_ok,)).fetchone()[0]
    db.close()

    failed = [b for b in batches if b["status"] == "failed"]
    models = sorted({b["model"] for b in batches})
    events_n, esc_n = ev["n"], ev["esc"]
    esc_ratio = (esc_n / events_n) if events_n else 0.0

    # TICKET-K:「這批沒讀到」與「這批真的沒事」要分開講。
    # 2026-09-02 那天看到的是後者的措辭,實際是前者 —— 於是沒有人去追。
    container_failed = [b for b in failed
                        if "ContainerDropError" in str(b["error"] or "")]
    other_failed = [b for b in failed if b not in container_failed]

    alerts = []
    if container_failed:
        alerts.append(
            f"頂層解析失敗 {len(container_failed)} 批:模型把 events/subject_proposals "
            "整個包成字串或 JSON 壞掉。批次已標 failed、游標沒前進,明晚會自動重抽;"
            "原文在 health/extract_dumps/。這不是漏抽,是還沒抽到")
    if other_failed:
        alerts.append(f"batch 失敗 {len(other_failed)} 次:{other_failed[0]['error']}")
    if batches and events_n == 0 and any(b["status"] == "committed" for b in batches):
        alerts.append("有跑批且成功入帳但 0 events(內容真的沒有值得記的事,或抽取過嚴)")
    if events_n > 15:
        alerts.append(f"events {events_n} 條(>基線 6/批 的 2.5 倍,疑過抽)")
    if events_n and esc_ratio > 0.5:
        alerts.append(f"escalated 比例 {esc_ratio:.0%}(基線 25%)")
    if props > 3:
        alerts.append(f"proposals {props} 條/日(>3,疑亂提案)")

    rec = {"date": today, "models": models, "batches": len(batches),
           "failed": len(failed), "events": events_n, "escalated": esc_n,
           "escalated_ratio": round(esc_ratio, 3), "proposals": props,
           "pending_raw_after": pending_raw,
           "container_failed": len(container_failed), "alerts": alerts}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))

    if today > WATCH_END:
        return 0  # 觀察期滿,安靜記錄
    if alerts:
        notify("檔案室書記官觀察告警",
               f"Sonnet 5 切換觀察:{';'.join(alerts)}")
    if today == WATCH_END:
        try:
            lines = [json.loads(l) for l in open(LOG)]
            tot_e = sum(r["events"] for r in lines)
            tot_a = sum(len(r["alerts"]) for r in lines)
            notify("書記官切換觀察期滿",
                   f"7 天合計 events={tot_e}、告警={tot_a} 次。無異常則 Sonnet 5 轉正,詳見 model_switch_watch.jsonl")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
