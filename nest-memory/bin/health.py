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
import subprocess
import sys
from datetime import datetime, timezone, timedelta

BASE = "/srv/nest-memory"
HEALTH_DIR = f"{BASE}/health"
ALERT_STATE = f"{HEALTH_DIR}/alert_state.json"
STATUS_FILE = f"{HEALTH_DIR}/health_status.json"
NOTIFY = ["/root/chatnest-next/.venv/bin/python", f"{BASE}/bin/notify.py"]
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


def main() -> int:
    os.umask(0o077)
    now = datetime.now(TZ)
    checks = {
        "disk_free": check_disk(),
        "backup_last_success": age_check(
            f"{HEALTH_DIR}/backup_last_success.json", 26, 50, "backup"),
        "raw_mirror": age_check(
            f"{HEALTH_DIR}/mirror_last_run.json", 0.5, 2, "raw mirror"),
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

    today = f"{now:%Y-%m-%d}"
    if now.hour == 9 and state.get("digest_last_date") != today and warnings:
        subprocess.run(
            NOTIFY + ["Nest Memory 日摘要(warning)", ";".join(warnings)],
            check=False, timeout=30)
        state["digest_last_date"] = today

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
