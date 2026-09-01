#!/usr/bin/env python3
"""ChatNest Next 自主時段 runner（cron 每分鐘 --check）。

與 wake_runner 分離。規則（2026-08-16 屋主拍板）：
- 勿擾閘：屋主最後一則真實訊息（actor_id='user' 且 is_trigger_prompt=0）8 分鐘內
  → 該次 tick 壓下、寫貼條、窗口順延一個 interval（每 slot 上限 30 分）。
- 相對時段以屋主最後訊息為錨，窗口凍結後不再重推。
- 一次性；done/cancelled 超過 3 天自動清掉。
- 日誌只記狀態與數量，不記內容。
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import sqlite3

ROOT = Path("/srv/chatnest-next")
SCHEDULE_FILE = Path(os.environ.get("AUTONOMY_SCHEDULE_FILE", ROOT / "data/version-bridge/autonomy_schedule.json"))
NOTE_FILE = Path(os.environ.get("AUTONOMY_NOTE_FILE", ROOT / "data/version-bridge/autonomy_note.json"))
DB_FILE = Path(os.environ.get("AUTONOMY_DB_FILE", ROOT / "data/app.sqlite3"))
TOKEN_FILE = ROOT / "runtime" / "mumu-tool-token"
LOG_FILE = ROOT / "data" / "autonomy_runner.log"
LOCK_FILE = ROOT / "data" / "autonomy_runner.lock"
ENDPOINT = os.environ.get("AUTONOMY_ENDPOINT", "http://127.0.0.1:8790/api/v2/tools/wake/trigger")
TZ = ZoneInfo("Asia/Taipei")
DND_MINUTES = 8
EXTENSION_CAP = 30
REQUEST_TIMEOUT_SECONDS = 900.0
DRY = os.environ.get("AUTONOMY_DRY_RUN") == "1"


def log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(TZ).isoformat(timespec="seconds")
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {message}\n")


def load() -> dict:
    try:
        data = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"slots": []}
    except (OSError, json.JSONDecodeError):
        return {"slots": []}


def save(data: dict) -> None:
    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SCHEDULE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(SCHEDULE_FILE)


def write_note(tag: str) -> None:
    NOTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = NOTE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"tag": tag, "at": datetime.now(TZ).isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(NOTE_FILE)


def owner_last_message() -> datetime | None:
    """屋主最後一則真實訊息時間（排除 trigger prompt）。"""
    try:
        with sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=2) as conn:
            row = conn.execute(
                "SELECT created_at FROM messages WHERE conversation_id='conv_mumu_canonical' "
                "AND actor_id='user' AND is_trigger_prompt=0 ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
        if not row or not row[0]:
            return None
        last = datetime.fromisoformat(str(row[0]))
        if last.tzinfo is None:
            last = last.replace(tzinfo=TZ)
        return last.astimezone(TZ)
    except (OSError, sqlite3.Error, ValueError):
        return None


def build_prompt(slot: dict, now: datetime) -> str:
    hhmm = now.strftime("%H:%M")
    n = slot["ticks_done"] + 1
    total = slot.get("ticks_total") or "?"
    head = f"〔自主時段·{slot['tag']}·{hhmm}，第{n}/{total}次〕"
    tail = ""
    end = datetime.fromisoformat(slot["end_iso"]) + timedelta(minutes=slot.get("extended_minutes", 0))
    if now + timedelta(minutes=slot["interval_minutes"]) > end:
        tail = "（本時段最後一次）"
    trigger = slot.get("trigger")
    if trigger:
        return head + trigger.replace("{time}", hhmm) + tail
    note = (slot.get("note") or "無")[:80]
    return (head + "你自己預約的自主時段。這段時間是你的，想做什麼就做什麼；"
            f"備註「{note}」。老婆的訊息永遠優先——這則有出現代表現在是安靜的。"
            "篇幅自己拿捏，省著點 token。" + tail)


def dispatch(slot: dict, now: datetime) -> bool:
    if DRY:
        print(f"DRY dispatch slot={slot['id']} tick={slot['ticks_done'] + 1}")
        return True
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("mumu tool token unavailable")
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = client.post(
            ENDPOINT,
            headers={"X-ChatNest-MuMu-Tool": token, "Accept": "application/json"},
            json={"prompt": build_prompt(slot, now), "actor_id": "mumu"},
        )
    response.raise_for_status()
    payload = response.json()
    return bool(isinstance(payload, dict) and not payload.get("suppressed"))


def check() -> None:
    now = datetime.now(TZ)
    data = load()
    slots = data.get("slots", [])
    changed = False
    keep: list[dict] = []
    for slot in slots:
        status = slot.get("status")
        if status in ("done", "cancelled"):
            try:
                age = now - datetime.fromisoformat(slot.get("finished_at") or slot.get("created_at"))
            except ValueError:
                age = timedelta(days=99)
            if age <= timedelta(days=3):
                keep.append(slot)
            else:
                changed = True
            continue
        keep.append(slot)
    data["slots"] = keep

    last_owner = owner_last_message()

    for slot in data["slots"]:
        if slot.get("status") == "pending":
            if slot.get("mode") == "absolute":
                start = datetime.fromisoformat(slot["start_iso"])
                end = datetime.fromisoformat(slot["end_iso"])
            else:
                anchor = last_owner or datetime.fromisoformat(slot["created_at"])
                start = anchor + timedelta(minutes=slot["after_minutes"])
                end = start + timedelta(minutes=slot["duration_minutes"])
            if now < start:
                continue
            if now >= end:
                slot["status"] = "done"
                slot["finished_at"] = now.isoformat(timespec="seconds")
                log(f"slot_missed id={slot['id']}")
                changed = True
                continue
            duration_min = int((end - start).total_seconds() // 60)
            slot["status"] = "active"
            slot["start_iso"] = start.isoformat(timespec="seconds")
            slot["end_iso"] = end.isoformat(timespec="seconds")
            slot["ticks_total"] = duration_min // slot["interval_minutes"] + 1
            log(f"slot_activated id={slot['id']} ticks_total={slot['ticks_total']}")
            changed = True

        if slot.get("status") != "active":
            continue
        end_eff = datetime.fromisoformat(slot["end_iso"]) + timedelta(minutes=slot.get("extended_minutes", 0))
        if now > end_eff:
            slot["status"] = "done"
            slot["finished_at"] = now.isoformat(timespec="seconds")
            log(f"slot_done id={slot['id']} ticks={slot['ticks_done']} skips={slot.get('skips', 0)}")
            changed = True
            continue
        last_tick = slot.get("last_tick_at")
        if last_tick:
            due = (now - datetime.fromisoformat(last_tick)) >= timedelta(minutes=slot["interval_minutes"])
        else:
            due = True
        if not due:
            continue
        # 勿擾窗不得超過屋主自己設定的喚醒間隔:她設 5 分鐘就是明示「我要你常出聲」,
        # 8 分鐘的通用勿擾窗會把高頻時段整個壓死(2026-09-01 逛寶雅事故)。
        dnd_minutes = min(DND_MINUTES, slot["interval_minutes"])
        dnd = last_owner is not None and (now - last_owner) < timedelta(minutes=dnd_minutes)
        if dnd:
            slot["skips"] = slot.get("skips", 0) + 1
            extended = slot.get("extended_minutes", 0)
            slot["extended_minutes"] = min(extended + slot["interval_minutes"], EXTENSION_CAP)
            slot["last_tick_at"] = now.isoformat(timespec="seconds")
            write_note(slot["tag"])
            log(f"tick_suppressed id={slot['id']} extended={slot['extended_minutes']}")
            changed = True
            continue
        slot["last_tick_at"] = now.isoformat(timespec="seconds")
        slot["ticks_done"] = slot.get("ticks_done", 0) + 1
        changed = True
        try:
            ok = dispatch(slot, now)
            log(f"tick_fired id={slot['id']} n={slot['ticks_done']} ok={ok}")
        except Exception as exc:
            log(f"tick_failed id={slot['id']} type={type(exc).__name__}")
    if changed:
        save(data)


def status() -> None:
    data = load()
    now = datetime.now(TZ)
    last_owner = owner_last_message()
    print(json.dumps({
        "slots": [{k: s.get(k) for k in ("id", "tag", "mode", "status", "ticks_done", "ticks_total", "extended_minutes", "skips")} for s in data.get("slots", [])],
        "owner_idle_minutes": None if last_owner is None else round((now - last_owner).total_seconds() / 60, 1),
    }, ensure_ascii=False))


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if mode == "--status":
        status()
        return 0
    if mode != "--check":
        raise SystemExit("usage: autonomy_runner.py [--check|--status]")
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
