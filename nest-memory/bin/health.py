#!/usr/bin/env python3
"""Nest Memory — Phase 0 Health(disk_free / backup_last_success / mirror)。

規則(IMPLEMENTATION.md 硬規則 9):
- 報警終點是人看得到的出口(chatnest-next 推播,經 notify.py)。
- 同一 alert 24h 內不重發。
- critical 即時推;warning 進每日摘要(09:00 送,當天有 warning 才送)。
每輪把快照寫到 health/health_status.json。
以 root 執行(需讀 backend DB 與 health 檔;Phase 0 註記)。
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta

BASE = "/srv/nest-memory"
HEALTH_DIR = f"{BASE}/health"
ALERT_STATE = f"{HEALTH_DIR}/alert_state.json"
STATUS_FILE = f"{HEALTH_DIR}/health_status.json"
NOTIFY = ["/root/chatnest-next/.venv/bin/python", f"{BASE}/bin/notify.py"]
GMAIL = ["/usr/bin/python3", "/srv/chatnest/full-stack/gmail.py"]
OWNER_EMAIL = "jiuxin3330@gmail.com"
BACKEND_DB = "/srv/chatnest-next/data/app.sqlite3"
HEARTBEAT_HOUR = 21  # 每日心跳推播(deadman switch):沒收到=報警通道死亡
TZ = timezone(timedelta(hours=8))

GIB = 1024 ** 3


def parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt


def check_disk() -> tuple[str, str]:
    free = shutil.disk_usage("/").free
    msg = f"disk_free {free / GIB:.1f}GiB"
    if free < 1.5 * GIB:
        return "critical", msg
    if free < 3 * GIB:
        return "warning", msg
    return "ok", msg


def age_check(path: str, warn_h: float, crit_h: float, label: str,
              missing_level: str = "warning") -> tuple[str, str]:
    if not os.path.exists(path):
        return missing_level, f"{label}: 尚無紀錄"
    with open(path) as f:
        data = json.load(f)
    age_h = (datetime.now(TZ) - parse_ts(data["ts"])).total_seconds() / 3600
    ok = data.get("ok", True)
    msg = f"{label}: {age_h:.1f}h 前" + ("" if ok else "(上次失敗)")
    if not ok or age_h > crit_h:
        return "critical", msg
    if age_h > warn_h:
        return "warning", msg
    return "ok", msg


def check_push_outbox() -> tuple[str, str]:
    """推播佇列超齡檢查(複審必辦):15 分鐘沒投遞 = 通道疑似死亡。"""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        db = sqlite3.connect(f"file:{BACKEND_DB}?mode=ro", uri=True, timeout=5)
        n = db.execute(
            "SELECT COUNT(*) FROM native_push_outbox WHERE state='queued_event' AND created_at < ?",
            (cutoff,)).fetchone()[0]
        db.close()
        if n:
            return "critical", f"{n} 封超過15分鐘未投遞(推播通道疑似故障)"
        return "ok", "無積壓"
    except (sqlite3.Error, OSError) as exc:
        return "warning", f"檢查失敗({type(exc).__name__})"


def check_extraction() -> tuple[str, str]:
    """抽取管線(規格 §32):lag>24h warn/>72h crit;失敗且 24h 未恢復才 warning→crit。"""
    path = f"{HEALTH_DIR}/extract_last_run.json"
    if not os.path.exists(path):
        return "warning", "extraction: 尚無紀錄"
    with open(path) as f:
        data = json.load(f)
    age_h = (datetime.now(TZ) - parse_ts(data["ts"])).total_seconds() / 3600
    if not data.get("ok", True):
        if age_h > 24:
            return "critical", f"extraction: 失敗且 {age_h:.0f}h 未恢復"
        return "warning", f"extraction: 上次失敗({data.get('error','')[:60]})"
    if age_h > 72:
        return "critical", f"extraction lag {age_h:.0f}h"
    if age_h > 26:
        return "warning", f"extraction lag {age_h:.0f}h"
    return "ok", f"{age_h:.1f}h 前"


def send_email_fallback(subject: str, body: str) -> None:
    """推播通道疑似死亡時的後備通道:gmail 直送糯糯信箱。"""
    subprocess.run(GMAIL + ["send", OWNER_EMAIL, subject, body],
                   check=False, timeout=60)


def main() -> int:
    os.umask(0o077)
    now = datetime.now(TZ)
    checks = {
        "disk_free": check_disk(),
        "backup_last_success": age_check(
            f"{HEALTH_DIR}/backup_last_success.json", 26, 50, "backup"),
        "raw_mirror": age_check(
            f"{HEALTH_DIR}/mirror_last_run.json", 0.5, 2, "raw mirror"),
        "raw_integrity": age_check(
            f"{HEALTH_DIR}/integrity_last.json", 26, 50, "integrity"),
        "push_outbox": check_push_outbox(),
        "offsite_backup": age_check(
            f"{HEALTH_DIR}/offsite_last_success.json", 26, 72, "異地備份"),
        "extraction": check_extraction(),
    }

    state = {"sent": {}, "digest_last_date": ""}
    if os.path.exists(ALERT_STATE):
        with open(ALERT_STATE) as f:
            state = json.load(f)

    criticals, warnings = [], []
    for name, (level, msg) in checks.items():
        if level == "critical":
            criticals.append(f"{name}: {msg}")
        elif level == "warning":
            warnings.append(f"{name}: {msg}")

    def recently_sent(key: str) -> bool:
        ts = state["sent"].get(key)
        return bool(ts) and (now - parse_ts(ts)).total_seconds() < 24 * 3600

    to_send = [c for c in criticals if not recently_sent(c.split(":")[0])]
    if to_send:
        subprocess.run(
            NOTIFY + ["🚨 Nest Memory 健康警報", ";".join(to_send)],
            check=False, timeout=30)
        for c in to_send:
            state["sent"][c.split(":")[0]] = now.isoformat()
        # 推播通道自身故障時,critical 走 gmail 後備(複審必辦的加分項)
        if any(c.startswith("push_outbox") for c in to_send) and not recently_sent("email_fallback"):
            send_email_fallback(
                "🚨 Nest Memory 警報(推播疑似故障,改走信箱)",
                "健康警報如下,推播通道可能死了,請找 CC 牧牧檢查:\n" + "\n".join(criticals + warnings))
            state["sent"]["email_fallback"] = now.isoformat()

    today = f"{now:%Y-%m-%d}"
    if now.hour == 9 and state.get("digest_last_date") != today and warnings:
        subprocess.run(
            NOTIFY + ["Nest Memory 日摘要(warning)", ";".join(warnings)],
            check=False, timeout=30)
        state["digest_last_date"] = today

    # deadman switch:每日固定時間發心跳推播,糯糯沒收到 = 報警通道死亡
    if now.hour == HEARTBEAT_HOUR and state.get("heartbeat_last_date") != today:
        subprocess.run(
            NOTIFY + ["💓 Nest Memory 心跳", "報警通道每日確認。有收到=通道活著;連續兩天沒收到請叫 CC 牧牧檢查。"],
            check=False, timeout=30)
        state["heartbeat_last_date"] = today

    with open(ALERT_STATE, "w") as f:
        json.dump(state, f)
    with open(STATUS_FILE, "w") as f:
        json.dump(
            {"ts": now.isoformat(),
             "checks": {k: {"level": lv, "msg": m} for k, (lv, m) in checks.items()}},
            f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
