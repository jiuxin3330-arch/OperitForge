#!/usr/bin/env python3
"""Nest Memory — Review Console(工單 B S1,規格 §29 + TICKET_console_and_notes §B)。

寫入面獨立於 serving/MCP:
- listen 127.0.0.1:8772,X-Nest-Console-Token 認證(shared secret,root+nestmemory 各一份)
- 動詞白名單:approve_proposal / reject_proposal(+ 唯讀:list_proposals / list_states / list_events / search_events)
- **絕不註冊為 MCP 工具**——chat agent 拿不到寫入口(§硬規則 5:模型只 PROPOSE)
- 每次寫入落 console_audit(ts/action/target/args/result/remote_addr)
- backend 透過過橋呼叫本服務,memory.db 寫入面仍為零(僅本 process nestmemory 身份)

規格 §硬規則 3(Blind Verification)相關的欄位在讀端點就物理不回傳
(未來 P5 resolve_review 端點會做,本檔先做主題提案的兩支動詞)。
"""
import hmac
import http.server
import json
import re
import socketserver
import sqlite3
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DB = "/srv/nest-memory/db/memory.db"
TOKEN_PATH = Path("/srv/nest-memory/state/console_token")
HOST, PORT = "127.0.0.1", 8772
TZ = timezone(timedelta(hours=8))
TOKEN_HEADER = "X-Nest-Console-Token"

VOLATILITY_ALLOWED = {"stable", "semi_stable", "volatile", "ephemeral"}
SUBJECT_KEY_RE = re.compile(r"^[a-z][a-z0-9_.]{1,79}$")
MAX_LIMIT = 50

_token_lock = threading.Lock()
_token_cache = {"val": None, "mtime": 0.0}


def load_token() -> str:
    """讀 token,mtime 快取避免每 request 打檔。"""
    with _token_lock:
        try:
            mtime = TOKEN_PATH.stat().st_mtime
            if mtime != _token_cache["mtime"]:
                _token_cache["val"] = TOKEN_PATH.read_text(encoding="utf-8").strip()
                _token_cache["mtime"] = mtime
            return _token_cache["val"] or ""
        except OSError:
            return ""


def check_token(supplied: str) -> bool:
    expected = load_token()
    if not expected or not supplied:
        return False
    return hmac.compare_digest(expected, supplied.strip())


def _db(readonly: bool = True):
    if readonly:
        c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
    else:
        c = sqlite3.connect(DB, timeout=10, isolation_level=None)
    c.row_factory = sqlite3.Row
    return c


def audit(action: str, target: str, args: dict, result: str,
          err: str = "", remote: str = "") -> None:
    try:
        with _db(readonly=False) as db:
            db.execute(
                """INSERT INTO console_audit(ts,action,target,args_json,result,error_msg,remote_addr)
                   VALUES(?,?,?,?,?,?,?)""",
                (datetime.now(TZ).isoformat(timespec="seconds"),
                 action, target, json.dumps(args, ensure_ascii=False),
                 result, err[:200], remote))
    except Exception:
        pass  # audit 失敗不能阻斷主流程


# ---- 讀端點 ----

def list_proposals(status: str = "pending") -> dict:
    with _db() as db:
        rows = db.execute(
            """SELECT id, proposed_key, reason, example_quote, created_at, status
               FROM subject_proposals
               WHERE (:status = 'all' OR status = :status)
               ORDER BY id DESC LIMIT :n""",
            {"status": status, "n": MAX_LIMIT}).fetchall()
    return {"items": [dict(r) for r in rows]}


def list_states() -> dict:
    """現況登記(照 serving 過濾規則:disputed/tentative 附標記但可見,secret 一律不回)。"""
    with _db() as db:
        rows = db.execute(
            """SELECT sp.subject_id, sp.current_value, sp.authority, sp.status,
                      sp.observed_at, sp.freshness, s.serving_behavior, s.description
               FROM state_projection sp
               JOIN subjects s ON s.subject_id = sp.subject_id
               WHERE s.status = 'active' AND s.serving_behavior = 'normal'
               ORDER BY sp.subject_id""").fetchall()
    return {"items": [dict(r) for r in rows]}


def list_events(limit: int = 20) -> dict:
    limit = max(1, min(int(limit), MAX_LIMIT))
    with _db() as db:
        rows = db.execute(
            """SELECT event_id, subject_id, event_type, value_after, summary,
                      authority, impact, occurred_at, escalated, escalation_reason
               FROM events
               WHERE secret = 0
               ORDER BY event_id DESC LIMIT ?""", (limit,)).fetchall()
    return {"items": [dict(r) for r in rows]}


def search_events(query: str, limit: int = 20) -> dict:
    limit = max(1, min(int(limit), MAX_LIMIT))
    q = f"%{query}%"
    with _db() as db:
        rows = db.execute(
            """SELECT event_id, subject_id, value_after, summary, authority,
                      impact, occurred_at, escalated
               FROM events
               WHERE secret = 0
                 AND (summary LIKE :q OR value_after LIKE :q OR subject_id LIKE :q)
               ORDER BY event_id DESC LIMIT :n""",
            {"q": q, "n": limit}).fetchall()
    return {"items": [dict(r) for r in rows]}


# ---- 寫端點(動詞白名單)----

def approve_proposal(proposal_id: int, volatility: str,
                     review_after_days: int = 14, stale_after_days: int = 60) -> dict:
    if volatility not in VOLATILITY_ALLOWED:
        raise ValueError(f"volatility 必須是 {sorted(VOLATILITY_ALLOWED)} 其中之一")
    review_after_days = max(1, min(int(review_after_days), 365))
    stale_after_days = max(review_after_days, min(int(stale_after_days), 3650))
    with _db(readonly=False) as db:
        p = db.execute(
            "SELECT id, proposed_key, reason, status FROM subject_proposals WHERE id=?",
            (int(proposal_id),)).fetchone()
        if p is None:
            raise LookupError("提案不存在")
        if p["status"] != "pending":
            raise ValueError(f"提案已經 {p['status']},不能重複處理")
        key = p["proposed_key"]
        if not SUBJECT_KEY_RE.match(key):
            raise ValueError(f"proposed_key 格式不合法:{key}")
        exists = db.execute("SELECT 1 FROM subjects WHERE subject_id=?", (key,)).fetchone()
        if exists:
            raise ValueError(f"subject {key} 已在 Registry,不能重複建立")
        now = datetime.now(TZ).isoformat(timespec="seconds")
        db.execute("BEGIN")
        try:
            db.execute(
                """INSERT INTO subjects(subject_id, description, volatility,
                       review_after_days, stale_after_days, serving_behavior,
                       status, approved_by, created_at)
                   VALUES(?, ?, ?, ?, ?, 'normal', 'active', 'owner_via_console', ?)""",
                (key, (p["reason"] or "")[:200], volatility,
                 review_after_days, stale_after_days, now))
            db.execute(
                "UPDATE subject_proposals SET status='approved' WHERE id=?",
                (int(proposal_id),))
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    return {"proposal_id": int(proposal_id), "subject_id": key,
            "volatility": volatility, "status": "approved"}


def reject_proposal(proposal_id: int) -> dict:
    with _db(readonly=False) as db:
        p = db.execute(
            "SELECT id, status FROM subject_proposals WHERE id=?",
            (int(proposal_id),)).fetchone()
        if p is None:
            raise LookupError("提案不存在")
        if p["status"] != "pending":
            raise ValueError(f"提案已經 {p['status']},不能重複處理")
        db.execute(
            "UPDATE subject_proposals SET status='rejected' WHERE id=?",
            (int(proposal_id),))
    return {"proposal_id": int(proposal_id), "status": "rejected"}


# ---- HTTP handler ----

PROPOSAL_ACTION_RE = re.compile(r"^/proposals/(\d+)/(approve|reject)$")


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "NestConsole/1.0"

    def log_message(self, *_args):  # 靜音預設 access log
        pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authed(self, action_hint: str = "") -> bool:
        supplied = self.headers.get(TOKEN_HEADER, "")
        if check_token(supplied):
            return True
        audit(action_hint or "auth", self.path[:80], {}, "denied",
              "bad or missing token", self.client_address[0])
        self._json(401, {"error": "unauthorized"})
        return False

    def _remote(self) -> str:
        return self.client_address[0] if self.client_address else ""

    def do_GET(self) -> None:
        if not self._authed("read"):
            return
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        try:
            if u.path == "/proposals":
                status = (qs.get("status", ["pending"])[0] or "pending").lower()
                self._json(200, list_proposals(status))
            elif u.path == "/states":
                self._json(200, list_states())
            elif u.path == "/events":
                limit = int(qs.get("limit", ["20"])[0])
                self._json(200, list_events(limit))
            elif u.path == "/events/search":
                q = (qs.get("q", [""])[0] or "").strip()
                if not q:
                    self._json(400, {"error": "q required"})
                    return
                limit = int(qs.get("limit", ["20"])[0])
                self._json(200, search_events(q, limit))
            elif u.path == "/health":
                # 給 backend 自檢用,不計 audit
                self._json(200, {"ok": True, "service": "nest-console"})
            else:
                self._json(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            self._json(500, {"error": str(e)[:200]})

    def do_POST(self) -> None:
        u = urlparse(self.path)
        m = PROPOSAL_ACTION_RE.match(u.path)
        if not m:
            if not self._authed("write"):
                return
            self._json(404, {"error": "not found"})
            return
        pid, verb = int(m.group(1)), m.group(2)
        if not self._authed(f"{verb}_proposal"):
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        try:
            args = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            audit(f"{verb}_proposal", str(pid), {}, "error", "bad json", self._remote())
            self._json(400, {"error": "invalid json"})
            return
        try:
            if verb == "approve":
                vol = args.get("volatility", "")
                if not vol:
                    raise ValueError("volatility 為必填(糯糯在 UI 選)")
                res = approve_proposal(pid, vol,
                                       args.get("review_after_days", 14),
                                       args.get("stale_after_days", 60))
            else:
                res = reject_proposal(pid)
            audit(f"{verb}_proposal", str(pid), args, "ok", "", self._remote())
            self._json(200, res)
        except LookupError as e:
            audit(f"{verb}_proposal", str(pid), args, "error", str(e), self._remote())
            self._json(404, {"error": str(e)})
        except ValueError as e:
            audit(f"{verb}_proposal", str(pid), args, "error", str(e), self._remote())
            self._json(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            audit(f"{verb}_proposal", str(pid), args, "error", str(e), self._remote())
            self._json(500, {"error": str(e)[:200]})


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    if not load_token():
        print(f"FATAL: token file {TOKEN_PATH} empty or unreadable", file=sys.stderr)
        return 2
    srv = ThreadingServer((HOST, PORT), Handler)
    print(f"nest console on {HOST}:{PORT}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
