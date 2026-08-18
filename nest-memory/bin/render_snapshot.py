#!/usr/bin/env python3
"""Nest Memory — Serving renderer(Phase 4 S2)。

把 state_projection 渲染成 RECORDED STATE 快照檔。
低頻變動(硬規則 16):內容沒變就不改寫檔案,mtime 不動,緩存前綴不破。
排程:projection(03:40)之後 03:50 執行,身份 nestmemory。
bridge 只讀 /srv/nest-memory/serving/state_snapshot.txt(ACL 唯讀);
檔案不存在時 bridge 自動不注入(fail-safe)。
"""
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime

import serving_common as sc

STATUS_FILE = "/srv/nest-memory/health/serving_render_last.json"


def main() -> int:
    os.umask(0o077)
    ok, changed, n_lines, err = True, False, 0, ""
    try:
        db = sqlite3.connect(f"file:{sc.DB}?mode=ro", uri=True)
        text = sc.render_text(db)
        db.close()
        n_lines = len([l for l in text.splitlines() if l.startswith("・")])
        new_hash = hashlib.sha256(text.encode()).hexdigest()
        old_hash = ""
        if os.path.exists(sc.SNAPSHOT_PATH):
            with open(sc.SNAPSHOT_PATH, encoding="utf-8") as f:
                old_hash = hashlib.sha256(f.read().encode()).hexdigest()
        if new_hash != old_hash:
            tmp = sc.SNAPSHOT_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.chmod(tmp, 0o644)  # 目錄 ACL 管門禁;chatagent 需可讀
            os.replace(tmp, sc.SNAPSHOT_PATH)
            changed = True
    except Exception as e:  # noqa: BLE001 — health 要看到失敗
        ok, err = False, str(e)
    with open(STATUS_FILE, "w") as f:
        json.dump({"ts": datetime.now(sc.TZ).isoformat(timespec="seconds"),
                   "ok": ok, "changed": changed, "entries": n_lines,
                   "error": err}, f, ensure_ascii=False)
    print(f"render: ok={ok} changed={changed} entries={n_lines} {err}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
