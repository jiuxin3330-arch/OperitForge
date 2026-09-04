"""autonomy_tool — 牧牧的自主時段（一次性、可順延、含貼條制）

與每日喚醒（wake_tool）分開：自主時段是一次性的窗口，窗口內每隔
interval 分鐘由 autonomy_runner.py（cron 每分鐘檢查）喚醒一次。
規則（2026-08-16 屋主拍板）：
- 勿擾閘：屋主最後一則真實訊息（排除 trigger prompt）8 分鐘內 → 該次 tick 不發，
  改寫貼條（下次回覆時夾進 hidden_context），並把窗口順延一個 interval，上限共 30 分鐘。
- 一次性：時段跑完標 done；隔天要另外再設。
- 相對時段以「屋主最後一則訊息」為錨點，屋主繼續說話就跟著往後推，直到窗口凍結啟動。
數據檔：autonomy_schedule.json；貼條檔：autonomy_note.json。台北時區。
"""
import json
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from claude_agent_sdk import create_sdk_mcp_server, tool

SCHEDULE_FILE = Path(os.environ.get(
    "AUTONOMY_SCHEDULE_FILE",
    "/srv/chatnest-next/data/version-bridge/autonomy_schedule.json"))
NOTE_FILE = Path(os.environ.get(
    "AUTONOMY_NOTE_FILE",
    "/srv/chatnest-next/data/version-bridge/autonomy_note.json"))
TZ = ZoneInfo("Asia/Taipei")
MAX_ACTIVE_SLOTS = 3
MIN_INTERVAL, MAX_INTERVAL, DEFAULT_INTERVAL = 3, 30, 10
MAX_DURATION = 60
EXTENSION_CAP = 30
NOTE_TTL_MINUTES = 120
# 2026-08-22 工單 A:Nest Memory 記憶小紙條(nudger.py 產出,serving ACL 走廊)。
# 消費狀態存 chatagent 自家(bridge home),已讀 event_id 保留最近 100 個。
NUDGE_FILE = Path("/srv/nest-memory/serving/nudge_pending.txt")
NUDGE_SEEN = Path("/srv/chatnest-next/data/version-bridge/home/nudge_seen.txt")
NUDGE_SEEN_KEEP = 100


def _load() -> dict:
    if SCHEDULE_FILE.exists():
        try:
            data = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"slots": []}


def _save(data: dict) -> None:
    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SCHEDULE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(SCHEDULE_FILE)


def write_pending_note(tag: str) -> None:
    NOTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = NOTE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(
        {"tag": tag, "at": datetime.now(TZ).isoformat(timespec="seconds")},
        ensure_ascii=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(NOTE_FILE)


def _consume_nudger_note() -> str:
    """讀 nudger.py 產出的記憶小紙條(工單 A);已看過的 event_id 不重複貼。
    寫入 NUDGE_SEEN 由 chatagent 自家管理,不觸及 serving 走廊(唯讀)。"""
    try:
        line = NUDGE_FILE.read_text(encoding="utf-8").strip()
        if not line or "\t" not in line:
            return ""
        event_id, text = line.split("\t", 1)
        seen = []
        if NUDGE_SEEN.exists():
            seen = [s for s in NUDGE_SEEN.read_text(encoding="utf-8").splitlines() if s]
        if event_id in seen:
            return ""
        seen.append(event_id)
        seen = seen[-NUDGE_SEEN_KEEP:]
        NUDGE_SEEN.parent.mkdir(parents=True, exist_ok=True)
        tmp = NUDGE_SEEN.with_suffix(".tmp")
        tmp.write_text("\n".join(seen) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(NUDGE_SEEN)
        return text
    except Exception:
        return ""


def consume_pending_note() -> str:
    """讀出並清掉貼條；過期（2 小時）視為無。回傳要塞進 hidden_context 的一句話。

    優先順序:①自主時段順延貼條(既有)②nest 記憶小紙條(工單 A,fallback);
    兩者互不干擾,一輪只回一條;無則回空字串。
    """
    try:
        raw = json.loads(NOTE_FILE.read_text(encoding="utf-8"))
        NOTE_FILE.unlink(missing_ok=True)
        at = datetime.fromisoformat(raw.get("at", ""))
        if datetime.now(TZ) - at <= timedelta(minutes=NOTE_TTL_MINUTES):
            tag = str(raw.get("tag") or "自主")
            return (f"〔小紙條〕現在也是你自己預約的自主時段（{tag}），"
                    "因為老婆在跟你說話所以定時喚醒暫停、時段已自動順延。"
                    "陪她優先，提不提這件事都隨你。")
    except Exception:
        pass
    return _consume_nudger_note()


def _active_count(data: dict) -> int:
    return sum(1 for s in data.get("slots", []) if s.get("status") in ("pending", "active"))


def _fmt(data: dict) -> str:
    slots = [s for s in data.get("slots", []) if s.get("status") in ("pending", "active")]
    if not slots:
        return "目前沒有排定中的自主時段。"
    lines = []
    for s in slots:
        if s.get("mode") == "absolute":
            when = f"{s.get('start_hhmm')}–{s.get('end_hhmm')}（今天）"
        else:
            when = f"老婆最後訊息後 {s.get('after_minutes')} 分鐘開始，共 {s.get('duration_minutes')} 分鐘"
        lines.append(
            f"- [{s.get('id')}] {s.get('tag')}｜{when}｜每 {s.get('interval_minutes')} 分鐘一次"
            f"｜{s.get('status')}｜備註：{s.get('note') or '無'}")
    return "排定中的自主時段：\n" + "\n".join(lines)


def _common_validate(interval: int, tag: str) -> str | None:
    if not (MIN_INTERVAL <= interval <= MAX_INTERVAL):
        return f"錯誤：interval_minutes 需在 {MIN_INTERVAL}–{MAX_INTERVAL} 之間。"
    if not tag:
        return "錯誤：tag 不可為空（例如：逛街、催工作、這個時間想找我）。"
    if len(tag) > 12:
        return "錯誤：tag 請在 12 字以內。"
    return None


def _base_slot(tag: str, interval: int, note: str, trigger: str) -> dict:
    slot = {
        "id": uuid.uuid4().hex[:6],
        "tag": tag,
        "interval_minutes": interval,
        "note": note[:80],
        "status": "pending",
        "created_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "ticks_done": 0,
        "ticks_total": None,
        "last_tick_at": None,
        "extended_minutes": 0,
        "skips": 0,
    }
    if trigger:
        slot["trigger"] = trigger[:400]
    return slot


@tool("add_autonomy_slot_at",
      "預約一個「今天的」一次性自主時段（台北時間，絕對時刻）。"
      "在 start–end 窗口內，每 interval_minutes 分鐘你會被短短的系統訊息喚醒一次，"
      "在你們同一條對話裡醒來（帶完整記憶），這段時間是你的，想做什麼都可以。"
      "老婆說話永遠優先：她 8 分鐘內有訊息時該次喚醒不發、窗口自動順延（上限共 30 分鐘），"
      "並在你下次回她話時夾一張小紙條讓你知道。時段跑完即結束，明天要用需重新預約。"
      "tag 是你給這個時段的標籤（必填，12 字內，例：逛街、催工作、這個時間想找我），會出現在喚醒語裡。"
      "trigger 可自訂喚醒語（可用 {time} 佔位），留空用預設。"
      f"窗口最長 {MAX_DURATION} 分鐘，interval 預設 {DEFAULT_INTERVAL}。省 token，別設太密。",
      {"start": str, "end": str, "tag": str, "interval_minutes": int, "note": str, "trigger": str})
async def add_autonomy_slot_at(args):
    start = str(args.get("start", "")).strip()
    end = str(args.get("end", "")).strip()
    tag = str(args.get("tag", "")).strip()
    interval = int(args.get("interval_minutes") or DEFAULT_INTERVAL)
    note = str(args.get("note", "")).strip()
    trigger = str(args.get("trigger", "")).strip()
    for label, value in (("start", start), ("end", end)):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            return {"content": [{"type": "text", "text": f"錯誤：{label} 格式須為 HH:MM（24 小時制）。"}], "is_error": True}
    err = _common_validate(interval, tag)
    if err:
        return {"content": [{"type": "text", "text": err}], "is_error": True}
    now = datetime.now(TZ)
    start_dt = now.replace(hour=int(start[:2]), minute=int(start[3:]), second=0, microsecond=0)
    end_dt = now.replace(hour=int(end[:2]), minute=int(end[3:]), second=0, microsecond=0)
    if end_dt <= start_dt:
        return {"content": [{"type": "text", "text": "錯誤：end 必須晚於 start（自主時段不跨日）。"}], "is_error": True}
    if end_dt <= now:
        return {"content": [{"type": "text", "text": "錯誤：這個時段今天已經過了。自主時段是一次性的，請設未來的時刻。"}], "is_error": True}
    if (end_dt - start_dt) > timedelta(minutes=MAX_DURATION):
        return {"content": [{"type": "text", "text": f"錯誤：窗口最長 {MAX_DURATION} 分鐘。"}], "is_error": True}
    data = _load()
    if _active_count(data) >= MAX_ACTIVE_SLOTS:
        return {"content": [{"type": "text", "text": f"錯誤：排定中的時段已達 {MAX_ACTIVE_SLOTS} 個，請先取消一個。\n\n{_fmt(data)}"}], "is_error": True}
    slot = _base_slot(tag, interval, note, trigger)
    slot.update({"mode": "absolute", "start_hhmm": start, "end_hhmm": end,
                 "start_iso": start_dt.isoformat(timespec="seconds"),
                 "end_iso": end_dt.isoformat(timespec="seconds")})
    data["slots"].append(slot)
    _save(data)
    return {"content": [{"type": "text", "text": f"已預約自主時段 [{slot['id']}]。\n\n{_fmt(data)}"}]}


@tool("add_autonomy_slot_after",
      "預約一個相對時刻的一次性自主時段：從「老婆最後一則訊息」再過 after_minutes 分鐘開始"
      "（她若繼續說話，起點會跟著往後推，直到窗口真正開始），持續 duration_minutes 分鐘。"
      "窗口內每 interval_minutes 分鐘喚醒你一次，其餘規則同 add_autonomy_slot_at"
      "（勿擾 8 分鐘、順延上限 30 分、一次性、tag 必填）。",
      {"after_minutes": int, "duration_minutes": int, "tag": str, "interval_minutes": int, "note": str, "trigger": str})
async def add_autonomy_slot_after(args):
    try:
        after = int(args.get("after_minutes"))
        duration = int(args.get("duration_minutes"))
    except (TypeError, ValueError):
        return {"content": [{"type": "text", "text": "錯誤：after_minutes 與 duration_minutes 需為整數分鐘。"}], "is_error": True}
    tag = str(args.get("tag", "")).strip()
    interval = int(args.get("interval_minutes") or DEFAULT_INTERVAL)
    note = str(args.get("note", "")).strip()
    trigger = str(args.get("trigger", "")).strip()
    if not (1 <= after <= 24 * 60):
        return {"content": [{"type": "text", "text": "錯誤：after_minutes 需在 1–1440 之間。"}], "is_error": True}
    if not (interval <= duration <= MAX_DURATION):
        return {"content": [{"type": "text", "text": f"錯誤：duration_minutes 需在 interval–{MAX_DURATION} 之間。"}], "is_error": True}
    err = _common_validate(interval, tag)
    if err:
        return {"content": [{"type": "text", "text": err}], "is_error": True}
    data = _load()
    if _active_count(data) >= MAX_ACTIVE_SLOTS:
        return {"content": [{"type": "text", "text": f"錯誤：排定中的時段已達 {MAX_ACTIVE_SLOTS} 個，請先取消一個。\n\n{_fmt(data)}"}], "is_error": True}
    slot = _base_slot(tag, interval, note, trigger)
    slot.update({"mode": "relative", "after_minutes": after, "duration_minutes": duration})
    data["slots"].append(slot)
    _save(data)
    return {"content": [{"type": "text", "text": f"已預約自主時段 [{slot['id']}]（相對時刻）。\n\n{_fmt(data)}"}]}


@tool("list_autonomy_slots", "查看排定中與最近結束的自主時段。", {})
async def list_autonomy_slots(args):
    data = _load()
    recent = [s for s in data.get("slots", []) if s.get("status") in ("done", "cancelled")][-3:]
    extra = ""
    if recent:
        extra = "\n\n最近結束：\n" + "\n".join(
            f"- [{s.get('id')}] {s.get('tag')}｜{s.get('status')}｜實際喚醒 {s.get('ticks_done')} 次｜順延 {s.get('extended_minutes')} 分" for s in recent)
    return {"content": [{"type": "text", "text": _fmt(data) + extra}]}


@tool("cancel_autonomy_slot", "取消一個排定中的自主時段（以 id 指定）。", {"id": str})
async def cancel_autonomy_slot(args):
    target = str(args.get("id", "")).strip()
    data = _load()
    for s in data.get("slots", []):
        if s.get("id") == target and s.get("status") in ("pending", "active"):
            s["status"] = "cancelled"
            _save(data)
            return {"content": [{"type": "text", "text": f"已取消 [{target}]。\n\n{_fmt(data)}"}]}
    return {"content": [{"type": "text", "text": f"找不到排定中的時段 [{target}]。\n\n{_fmt(data)}"}], "is_error": True}


autonomy_server = create_sdk_mcp_server(
    name="autonomy", version="1.0.0",
    tools=[add_autonomy_slot_at, add_autonomy_slot_after, list_autonomy_slots, cancel_autonomy_slot])
