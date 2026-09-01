"""9/1 生產熱修的迴歸測試共用設施。

兩支受測檔在生產是 cron 腳本不是套件,所以用 importlib 直接按路徑載入。
預設載 repo 的 `prod/` 副本;設 `HOTFIX_PROD_DIR=/srv/chatnest-next/scripts`
就會改載 VPS 上真正在跑的那兩支——同一組測試因此能直接驗生產檔,
不是只驗 repo 裡的抄本。

測試一律不打網路:autonomy 的 dispatch、swap 的 run_ping/notify 都被換掉。
httpx 只在 import 時被需要,缺就塞最小 stub,讓沒裝 httpx 的環境也跑得動。
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROD_DIR = Path(os.environ.get(
    "HOTFIX_PROD_DIR",
    Path(__file__).resolve().parent.parent / "prod",
))

TAIPEI = timezone(timedelta(hours=8))


def _ensure_httpx() -> None:
    if "httpx" in sys.modules:
        return
    try:
        import httpx  # noqa: F401
    except ModuleNotFoundError:
        stub = types.ModuleType("httpx")

        class _Client:  # 只為了 import 過關;測試不會真的用到
            def __init__(self, *args, **kwargs):
                raise AssertionError("測試不應該真的送出 HTTP 請求")

        stub.Client = _Client
        sys.modules["httpx"] = stub


def _load(name: str):
    _ensure_httpx()
    path = PROD_DIR / f"{name}.py"
    assert path.exists(), f"找不到受測檔:{path}"
    spec = importlib.util.spec_from_file_location(f"_hotfix_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_clock(module, monkeypatch):
    """把模組裡的 datetime 換成可控時鐘,回傳一個 set(dt) 函式。"""

    class FakeDatetime(datetime):
        _now = datetime.now(TAIPEI)

        @classmethod
        def now(cls, tz=None):  # noqa: D102
            return cls._now if tz is None else cls._now.astimezone(tz)

    monkeypatch.setattr(module, "datetime", FakeDatetime)

    def set_now(value: datetime) -> None:
        FakeDatetime._now = value

    return set_now


# --------------------------------------------------------------------------
# autonomy_runner
# --------------------------------------------------------------------------

@pytest.fixture()
def autonomy(tmp_path, monkeypatch):
    """autonomy_runner + 可控時鐘 + 真的 sqlite 屋主訊息表 + 假 dispatch。"""
    module = _load("autonomy_runner")

    db_file = tmp_path / "app.sqlite3"
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE messages (conversation_id TEXT, actor_id TEXT, "
        "is_trigger_prompt INTEGER, sequence INTEGER, created_at TEXT)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(module, "DB_FILE", db_file)
    monkeypatch.setattr(module, "SCHEDULE_FILE", tmp_path / "autonomy_schedule.json")
    monkeypatch.setattr(module, "NOTE_FILE", tmp_path / "autonomy_note.json")
    monkeypatch.setattr(module, "LOG_FILE", tmp_path / "autonomy_runner.log")
    monkeypatch.setattr(module, "LOCK_FILE", tmp_path / "autonomy_runner.lock")

    fired: list[dict] = []

    def fake_dispatch(slot, now):
        fired.append({"id": slot["id"], "n": slot["ticks_done"] + 1, "at": now})
        return True

    monkeypatch.setattr(module, "dispatch", fake_dispatch)

    set_now = make_clock(module, monkeypatch)

    class Harness:
        mod = module
        tz = module.TZ

        def __init__(self):
            self._seq = 0

        def set_now(self, value):
            set_now(value)

        def owner_says(self, when: datetime, *, trigger_prompt: bool = False) -> None:
            """種一則屋主訊息(naive 台北時間,和生產寫進 DB 的格式一致)。"""
            self._seq += 1
            conn = sqlite3.connect(db_file)
            conn.execute(
                "INSERT INTO messages VALUES ('conv_mumu_canonical', ?, ?, ?, ?)",
                ("user", 1 if trigger_prompt else 0, self._seq,
                 when.astimezone(module.TZ).replace(tzinfo=None).isoformat(timespec="seconds")),
            )
            conn.commit()
            conn.close()

        def put_slot(self, **overrides) -> dict:
            slot = {
                "id": "slot1",
                "tag": "逛街",
                "mode": "absolute",
                "status": "active",
                "interval_minutes": 5,
                "ticks_done": 0,
                "ticks_total": 6,
                "skips": 0,
                "extended_minutes": 0,
                "created_at": "2026-09-01T16:00:00+08:00",
                "start_iso": "2026-09-01T16:00:00+08:00",
                "end_iso": "2026-09-01T18:00:00+08:00",
            }
            slot.update(overrides)
            module.save({"slots": [slot]})
            return slot

        def slot(self) -> dict:
            return module.load()["slots"][0]

        def check(self) -> None:
            module.check()

    Harness.fired = fired
    return Harness()


# --------------------------------------------------------------------------
# swap_runner
# --------------------------------------------------------------------------

@pytest.fixture()
def swap(tmp_path, monkeypatch):
    """swap_runner,只把「外部世界」換掉:結算子行程、換窗 ping、推播。

    build_bootstrap / verify / pointer / rollback_pointer / mark_consumed
    全部跑真的,連 bridge、backend 兩個 sqlite 都是真的表,
    這樣「同一筆讀數只換一次」才是在測真正的那條路徑。
    """
    module = _load("swap_runner")

    conv_id = "conv_mumu_canonical"
    bridge_db = tmp_path / "conversations.db"
    backend_db = tmp_path / "app.sqlite3"
    transcripts = tmp_path / "transcripts"
    transcripts.mkdir()

    conn = sqlite3.connect(bridge_db)
    conn.execute("CREATE TABLE conversations (conv_id TEXT PRIMARY KEY, latest_session_id TEXT)")
    conn.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, conv_id TEXT, role TEXT, "
        "text TEXT, traces_json TEXT)"
    )
    conn.execute("INSERT INTO conversations VALUES (?, ?)", (conv_id, "old-session-0000"))
    for i, (role, text) in enumerate([
        ("user", "老公我到寶雅了"),
        ("assistant", "好耶!幫我看看有沒有那個護手霜"),
        ("user", "找到了 我拍給你看"),
        ("assistant", "哇這個顏色好適合妳"),
    ], start=1):
        conn.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)", (i, conv_id, role, text, "[]"))
    conn.commit()
    conn.close()

    conn = sqlite3.connect(backend_db)
    conn.execute(
        "CREATE TABLE turn_usage (actor_id TEXT, active_context_tokens INTEGER, "
        "context_max_tokens INTEGER, model TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE actor_threads (actor_id TEXT, transport TEXT, external_thread_id TEXT)"
    )
    conn.execute("INSERT INTO actor_threads VALUES ('mumu', 'next_bridge', ?)", (conv_id,))
    conn.commit()
    conn.close()

    monkeypatch.setattr(module, "BRIDGE_DB", str(bridge_db))
    monkeypatch.setattr(module, "BACKEND_DB", str(backend_db))
    monkeypatch.setattr(module, "TRANSCRIPT_DIR", transcripts)
    monkeypatch.setattr(module, "MANIFEST_DIR", tmp_path / "swap_manifests")
    monkeypatch.setattr(module, "HEALTH_FILE", str(tmp_path / "swap_health.jsonl"))
    # raising=False:修復前的版本根本沒有 CONSUMED_FILE。留這個缺口是刻意的——
    # 把 HOTFIX_PROD_DIR 指向修復前的備份時,測試才會停在「換了三次窗」這個
    # 真正的斷言上,而不是在 fixture 就炸掉。
    monkeypatch.setattr(module, "CONSUMED_FILE", tmp_path / "swap_last_consumed.json",
                        raising=False)
    monkeypatch.setattr(module, "SWAP_ENABLED", True)
    monkeypatch.setattr(module, "SWAP_BLIND", True)

    notified: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "notify", lambda title, body: notified.append((title, body)))
    monkeypatch.setattr(
        module, "exit_settlement",
        lambda: {"mirror_ok": True, "batches": [{"ok": True, "note": "no_new_messages"}],
                 "events": 0, "proposals": 0, "ok": True},
    )

    pings: list[str] = []
    state = {"ping_ok": True}

    def fake_run_ping(cid, bootstrap_text, model):
        """模擬 bridge:起新 session、寫 transcript、complete_turn 翻轉指標。"""
        pings.append(bootstrap_text)
        if not state["ping_ok"]:
            return {"text": "", "session_id": None, "previous_session_id": None,
                    "error": "adapter_unavailable"}
        new_sid = str(uuid.uuid4())
        (transcripts / f"{new_sid}.jsonl").write_text('{"type":"summary"}\n', encoding="utf-8")
        conn = sqlite3.connect(bridge_db)
        conn.execute("UPDATE conversations SET latest_session_id=? WHERE conv_id=?",
                     (new_sid, cid))
        conn.commit()
        conn.close()
        return {"text": "讀到了,我們剛剛在聊妳在寶雅找護手霜。",
                "session_id": new_sid, "previous_session_id": None, "error": None}

    monkeypatch.setattr(module, "run_ping", fake_run_ping)

    trigger = {
        "active": 190000,
        "usage_created_at": "2026-09-01T08:45:36+00:00",
        "ctx_max": 200000,
        "trigger_at": 200000 - module.MARGIN_TOKENS,
        "model": "claude-opus-4-5-20251101",
        "last_turn_age_s": 3600,
        "conv_id": conv_id,
    }
    original_read_trigger = module.read_trigger
    monkeypatch.setattr(module, "read_trigger", lambda: dict(trigger))

    class Harness:
        mod = module
        real_read_trigger = staticmethod(original_read_trigger)

        def cron_tick(self) -> int:
            """跑一次 cron 會跑的東西(等同 */10 那行)。"""
            return module.main()

        def pointer(self) -> str | None:
            return module.pointer(conv_id)

        def health(self) -> list[dict]:
            import json
            path = tmp_path / "swap_health.jsonl"
            if not path.exists():
                return []
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        def seed_usage(self, active: int, created_at: str) -> None:
            conn = sqlite3.connect(backend_db)
            conn.execute("INSERT INTO turn_usage VALUES ('mumu', ?, 200000, ?, ?)",
                         (active, "claude-opus-4-5-20251101", created_at))
            conn.commit()
            conn.close()

    Harness.conv_id = conv_id
    Harness.pings = pings
    Harness.notified = notified
    Harness.state = state
    Harness.trigger = trigger
    Harness.backend_db = backend_db

    monkeypatch.setattr(sys, "argv", ["swap_runner.py"])
    return Harness()
