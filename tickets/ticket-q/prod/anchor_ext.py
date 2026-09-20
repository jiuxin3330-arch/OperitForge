"""anchor-memory 儲存層擴充（TICKET-Q，2026-09-21）。

AnchorDB 的 mixin。只用 self._conn() / self.log_event() / self.MAX_EDGE_WEIGHT，不碰其他內部。

內容：
  Q1  migration（新欄位、污染期快照）、reinforce()（節點，遞減封頂）、reinforce_pairs()（邊，遞減封頂）、
      injections 帳（record_injection / recently_injected）
  Q2  memory_tasks：task_create / task_list / task_get / task_resolve；沒有刪除方法
  Q3  entity_cards + card_facts：card_create（owner）/ card_set_status（owner）/ card_fact_update（任何人）/
      card_get / card_list / cards_affected_by（provenance 反查）
  Q4  memory_lineage：lineage_of（雙向）；insert 時由 anchor_db 呼叫 _write_lineage
"""
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta

import anchor_config as cfg


def _now() -> str:
    return datetime.utcnow().isoformat()


class TicketQMixin:

    # ══════════════════════════════════════════════════════════════
    # Q1 ── migration
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _add_column(conn, table: str, col: str, decl: str) -> bool:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if col in cols:
            return False
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        return True

    def _migrate_ticketq(self):
        """冪等。第一次跑：加欄、建表、把 usage_count / edges.weight 快照到 legacy_*，標記污染期。"""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # memories：乾淨的 reinforcement 訊號 + legacy 快照 + digest schema
            self._add_column(conn, "memories", "reinforced_count", "INTEGER DEFAULT 0")
            self._add_column(conn, "memories", "reinforcement", "REAL DEFAULT 0.0")
            self._add_column(conn, "memories", "last_reinforced", "TEXT")
            self._add_column(conn, "memories", "legacy_usage_count", "INTEGER")
            self._add_column(conn, "memories", "kind", "TEXT DEFAULT 'memory'")
            self._add_column(conn, "memories", "derived_from", "TEXT")
            # edges：遞減計數 + legacy 快照
            self._add_column(conn, "edges", "hebb_count", "INTEGER DEFAULT 0")
            self._add_column(conn, "edges", "legacy_weight", "REAL")
            # 注入帳（invariant ③）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS injections (
                    memory_id        TEXT PRIMARY KEY,
                    last_injected_at TEXT NOT NULL,
                    last_path        TEXT NOT NULL,
                    last_caller      TEXT DEFAULT 'unknown',
                    count            INTEGER DEFAULT 1
                )
            """)
            # Q2 memory_tasks
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_tasks (
                    id          TEXT PRIMARY KEY,
                    source_id   TEXT NOT NULL,
                    intent      TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'open',
                    created_at  TEXT NOT NULL,
                    resolved_at TEXT,
                    resolved_by TEXT,
                    reason      TEXT,
                    result_ref  TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON memory_tasks(status)")
            # Q3 entity_cards + card_facts
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entity_cards (
                    id          TEXT PRIMARY KEY,
                    name        TEXT NOT NULL UNIQUE,
                    status      TEXT NOT NULL DEFAULT 'candidate',
                    what        TEXT NOT NULL,
                    why         TEXT NOT NULL,
                    timeline    TEXT NOT NULL,
                    created_by  TEXT NOT NULL,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS card_facts (
                    id            TEXT PRIMARY KEY,
                    card_id       TEXT NOT NULL REFERENCES entity_cards(id),
                    field         TEXT NOT NULL,
                    value         TEXT NOT NULL,
                    valid_from    TEXT NOT NULL,
                    valid_until   TEXT,
                    superseded_by TEXT,
                    provenance    TEXT NOT NULL,
                    created_at    TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_card ON card_facts(card_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_prov ON card_facts(provenance)")
            # Q4 lineage（derived ↔ source，雙向索引）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_lineage (
                    derived_id TEXT NOT NULL,
                    source_id  TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (derived_id, source_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lineage_source ON memory_lineage(source_id)")

            # 一次性污染快照：只在第一次跑時做
            row = conn.execute("SELECT value FROM schema_meta WHERE key='pollution_snapshot_at'").fetchone()
            if not row:
                now = _now()
                conn.execute("UPDATE memories SET legacy_usage_count = usage_count")
                conn.execute("UPDATE edges SET legacy_weight = weight")
                for k, v in (("pollution_cutoff", cfg.POLLUTION_CUTOFF),
                             ("pollution_snapshot_at", now),
                             ("ticketq_schema", "1")):
                    conn.execute("INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)",
                                 (k, v, now))
            conn.commit()

    def get_meta(self, key: str):
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    # ══════════════════════════════════════════════════════════════
    # Q1 ── reinforcement（節點 / 邊），遞減封頂
    # ══════════════════════════════════════════════════════════════

    def reinforce(self, memory_id: str, reason: str = "cite") -> dict:
        """cn 明確動作（cite / annotate）才走這裡。第 1 次全額、2–3 次減半、之後趨零、累積封頂。"""
        now = _now()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT reinforced_count, reinforcement FROM memories WHERE memory_id=?", (memory_id,)
            ).fetchone()
            if not row:
                return None
            n = row["reinforced_count"] or 0
            inc = cfg.reinforce_increment(n)
            new = min((row["reinforcement"] or 0.0) + inc, cfg.REINFORCE_CAP)
            conn.execute(
                "UPDATE memories SET reinforced_count=?, reinforcement=?, last_reinforced=?, last_used=? "
                "WHERE memory_id=?",
                (n + 1, new, now, now, memory_id),
            )
            conn.commit()
        self.log_event(memory_id, "reinforced", f"reason={reason} n={n + 1} inc={inc:.4f} total={new:.4f}")
        return {"memory_id": memory_id, "reinforced_count": n + 1, "reinforcement": new, "increment": inc}

    def reinforce_pairs(self, pairs: list, base: float = None) -> int:
        """邊強化（consolidate 專用）。每條邊自己的 hebb_count 決定遞減倍率；封頂 MAX_EDGE_WEIGHT。
        legacy 邊 hebb_count 從 0 起算——污染期的累積不算次數。回傳實際動到的邊數。"""
        base = cfg.EDGE_REINFORCE_BASE if base is None else base
        now = _now()
        touched = 0
        with self._conn() as conn:
            for a, b in pairs:
                for s, t in ((a, b), (b, a)):
                    row = conn.execute(
                        "SELECT weight, hebb_count FROM edges WHERE source_id=? AND target_id=?", (s, t)
                    ).fetchone()
                    if row:
                        n = row["hebb_count"] or 0
                        inc = base * cfg.reinforce_step(n)
                        w = min((row["weight"] or 0.0) + inc, self.MAX_EDGE_WEIGHT)
                        conn.execute(
                            "UPDATE edges SET weight=?, hebb_count=?, last_fired=? WHERE source_id=? AND target_id=?",
                            (w, n + 1, now, s, t),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO edges (source_id, target_id, weight, created, last_fired, hebb_count) "
                            "VALUES (?, ?, ?, ?, ?, 1)",
                            (s, t, base * cfg.reinforce_step(0), now, now),
                        )
                    touched += 1
            conn.commit()
        return touched

    # ── 注入帳（invariant ③）──

    def record_injection(self, ids: list, path: str, caller: str = "unknown"):
        """search / wakeup 回傳過什麼就記什麼。這不是強化，只是帳。"""
        ids = [i for i in ids if i]
        if not ids:
            return
        now = _now()
        with self._conn() as conn:
            for mid in ids:
                conn.execute("""
                    INSERT INTO injections (memory_id, last_injected_at, last_path, last_caller, count)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(memory_id) DO UPDATE SET
                        last_injected_at = excluded.last_injected_at,
                        last_path = excluded.last_path,
                        last_caller = excluded.last_caller,
                        count = injections.count + 1
                """, (mid, now, path, caller))
            conn.commit()

    def recently_injected(self, ids: list, window_minutes: int = None) -> set:
        window = cfg.INJECTION_WINDOW_MINUTES if window_minutes is None else window_minutes
        if not ids:
            return set()
        cutoff = (datetime.utcnow() - timedelta(minutes=window)).isoformat()
        qmarks = ",".join("?" * len(ids))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT memory_id FROM injections WHERE memory_id IN ({qmarks}) AND last_injected_at >= ?",
                list(ids) + [cutoff],
            ).fetchall()
        return {r["memory_id"] for r in rows}

    # ══════════════════════════════════════════════════════════════
    # Q2 ── memory_tasks（狀態物件；無刪除）
    # ══════════════════════════════════════════════════════════════

    def task_create(self, source_id: str, intent: str) -> dict:
        source_id = (source_id or "").strip()
        intent = (intent or "").strip()
        if not source_id or not intent:
            raise ValueError("source_id 與 intent 必填")
        tid = f"task_{uuid.uuid4().hex[:10]}"
        now = _now()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO memory_tasks (id, source_id, intent, status, created_at) VALUES (?, ?, ?, 'open', ?)",
                (tid, source_id, intent, now),
            )
            conn.commit()
        self.log_event(None, "task_created", f"{tid} source={source_id}")
        return self.task_get(tid)

    def task_get(self, task_id: str) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM memory_tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def task_list(self, status: str = None, limit: int = 50) -> list:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM memory_tasks WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memory_tasks ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    def task_resolve(self, task_id: str, status: str, resolved_by: str, reason: str,
                     result_ref: str = None) -> dict:
        """open → resolved | dismissed。resolved_by 與 reason 必填；終態不可再轉；沒有刪除。"""
        resolved_by = (resolved_by or "").strip()
        reason = (reason or "").strip()
        if not resolved_by or not reason:
            raise ValueError("resolved_by 與 reason 必填（invariant ⑤ 尾款）")
        task = self.task_get(task_id)
        if not task:
            raise ValueError(f"找不到 task：{task_id}")
        allowed = cfg.TASK_TRANSITIONS.get(task["status"], ())
        if status not in allowed:
            raise ValueError(f"不合法的狀態轉移：{task['status']} → {status}（允許：{list(allowed) or '無，終態'}）")
        now = _now()
        with self._conn() as conn:
            conn.execute(
                "UPDATE memory_tasks SET status=?, resolved_at=?, resolved_by=?, reason=?, result_ref=? WHERE id=?",
                (status, now, resolved_by, reason, result_ref, task_id),
            )
            conn.commit()
        self.log_event(result_ref, f"task_{status}", f"{task_id} by={resolved_by} reason={reason[:80]}")
        return self.task_get(task_id)

    # ══════════════════════════════════════════════════════════════
    # Q3 ── entity_cards + card_facts
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def _owner_ok(token: str) -> bool:
        """Owner key 在 root 0600 的檔案裡。檔案不存在 → 一律拒（fail closed）。"""
        if not token:
            return False
        try:
            with open(cfg.OWNER_KEY_PATH, encoding="utf-8") as fh:
                expected = fh.read().strip()
        except OSError:
            return False
        if not expected:
            return False
        return hmac.compare_digest(str(token).strip(), expected)

    def card_create(self, name: str, what: str, why: str, timeline: str,
                    owner_token: str, status: str = "candidate", created_by: str = "owner") -> dict:
        if not self._owner_ok(owner_token):
            raise PermissionError("建卡需要 owner 身分（owner_token 不符或未提供）")
        name = (name or "").strip()
        if not name or not (what or "").strip() or not (why or "").strip() or not (timeline or "").strip():
            raise ValueError("name / what / why / timeline 必填")
        if status not in cfg.CARD_STATUSES:
            raise ValueError(f"status 必須是 {cfg.CARD_STATUSES}")
        cid = f"card_{uuid.uuid4().hex[:10]}"
        now = _now()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO entity_cards (id, name, status, what, why, timeline, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cid, name, status, what.strip(), why.strip(), timeline.strip(), created_by, now, now),
            )
            # 三行卡面同時落成 facts，provenance = owner 建卡動作，之後才可被 supersede
            for field, value in (("what", what.strip()), ("why", why.strip()), ("timeline", timeline.strip())):
                conn.execute(
                    "INSERT INTO card_facts (id, card_id, field, value, valid_from, provenance, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"fact_{uuid.uuid4().hex[:10]}", cid, field, value, now, f"owner:card_create:{cid}", now),
                )
            conn.commit()
        self.log_event(None, "card_created", f"{cid} name={name} status={status}")
        return self.card_get(card_id=cid)

    def card_set_status(self, card_id: str, status: str, owner_token: str) -> dict:
        if not self._owner_ok(owner_token):
            raise PermissionError("改卡狀態需要 owner 身分")
        if status not in cfg.CARD_STATUSES:
            raise ValueError(f"status 必須是 {cfg.CARD_STATUSES}")
        with self._conn() as conn:
            row = conn.execute("SELECT status FROM entity_cards WHERE id=?", (card_id,)).fetchone()
            if not row:
                raise ValueError(f"找不到卡：{card_id}")
            conn.execute("UPDATE entity_cards SET status=?, updated_at=? WHERE id=?", (status, _now(), card_id))
            conn.commit()
        self.log_event(None, "card_status", f"{card_id} {row['status']} → {status}")
        return self.card_get(card_id=card_id)

    def card_fact_update(self, card_id: str, field: str, value: str, provenance: str) -> dict:
        """任何身分可用（系統/夜間只能走這條）。structured supersession：
        舊 fact 補 valid_until + superseded_by，新 fact 指回；不刪、不劃線。"""
        field = (field or "").strip()
        value = (value or "").strip()
        provenance = (provenance or "").strip()
        if not field or not value or not provenance:
            raise ValueError("field / value / provenance 必填（provenance 是來源 memory/event id）")
        now = _now()
        new_id = f"fact_{uuid.uuid4().hex[:10]}"
        with self._conn() as conn:
            card = conn.execute("SELECT id FROM entity_cards WHERE id=?", (card_id,)).fetchone()
            if not card:
                raise ValueError(f"找不到卡：{card_id}")
            old = conn.execute(
                "SELECT id FROM card_facts WHERE card_id=? AND field=? AND valid_until IS NULL", (card_id, field)
            ).fetchall()
            conn.execute(
                "INSERT INTO card_facts (id, card_id, field, value, valid_from, provenance, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id, card_id, field, value, now, provenance, now),
            )
            for o in old:
                conn.execute(
                    "UPDATE card_facts SET valid_until=?, superseded_by=? WHERE id=?", (now, new_id, o["id"])
                )
            if field in ("what", "why", "timeline"):
                conn.execute(f"UPDATE entity_cards SET {field}=?, updated_at=? WHERE id=?", (value, now, card_id))
            else:
                conn.execute("UPDATE entity_cards SET updated_at=? WHERE id=?", (now, card_id))
            conn.commit()
        self.log_event(provenance, "card_fact", f"{card_id}.{field} new={new_id} superseded={[o['id'] for o in old]}")
        return {"card_id": card_id, "field": field, "fact_id": new_id, "superseded": [o["id"] for o in old]}

    def card_get(self, card_id: str = None, name: str = None, include_history: bool = False) -> dict:
        with self._conn() as conn:
            if card_id:
                row = conn.execute("SELECT * FROM entity_cards WHERE id=?", (card_id,)).fetchone()
            elif name:
                row = conn.execute("SELECT * FROM entity_cards WHERE name=?", (name,)).fetchone()
            else:
                return None
            if not row:
                return None
            card = dict(row)
            if include_history:
                facts = conn.execute(
                    "SELECT * FROM card_facts WHERE card_id=? ORDER BY created_at", (card["id"],)
                ).fetchall()
            else:
                facts = conn.execute(
                    "SELECT * FROM card_facts WHERE card_id=? AND valid_until IS NULL ORDER BY created_at",
                    (card["id"],),
                ).fetchall()
        card["facts"] = [dict(f) for f in facts]
        return card

    def card_list(self, status: str = None) -> list:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT id, name, status, updated_at FROM entity_cards WHERE status=? ORDER BY name", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT id, name, status, updated_at FROM entity_cards ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def cards_affected_by(self, source_id: str) -> list:
        """provenance 反查（invariant ④）：給一個來源 id，列出引用它的 facts（含卡名、是否現行）。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT f.*, c.name AS card_name, c.status AS card_status FROM card_facts f "
                "JOIN entity_cards c ON c.id = f.card_id WHERE f.provenance = ? ORDER BY f.created_at",
                (source_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ══════════════════════════════════════════════════════════════
    # Q4 ── lineage
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def validate_kind(kind: str, derived_from) -> list:
        """回傳正規化後的 derived_from list。kind 不合法或 derived 類缺 provenance → ValueError。"""
        kind = kind or "memory"
        if kind not in cfg.MEMORY_KINDS:
            raise ValueError(f"kind 必須是 {cfg.MEMORY_KINDS}")
        if isinstance(derived_from, str):
            try:
                derived_from = json.loads(derived_from)
            except json.JSONDecodeError:
                derived_from = [derived_from]
        derived_from = [str(x).strip() for x in (derived_from or []) if str(x).strip()]
        if kind in cfg.DERIVED_KINDS and not derived_from:
            raise ValueError(f"kind={kind} 是 derived，derived_from 必填（來源 event/message id 列表）")
        return derived_from

    @staticmethod
    def _write_lineage(conn, derived_id: str, sources: list):
        now = _now()
        conn.execute("DELETE FROM memory_lineage WHERE derived_id=?", (derived_id,))
        for s in sources:
            conn.execute(
                "INSERT OR IGNORE INTO memory_lineage (derived_id, source_id, created_at) VALUES (?, ?, ?)",
                (derived_id, s, now),
            )

    def lineage_of(self, memory_id: str) -> dict:
        """雙向：這筆的來源（sources）與以這筆為來源的衍生（derivatives）。"""
        with self._conn() as conn:
            srcs = conn.execute(
                "SELECT source_id FROM memory_lineage WHERE derived_id=? ORDER BY source_id", (memory_id,)
            ).fetchall()
            ders = conn.execute(
                "SELECT l.derived_id, m.kind FROM memory_lineage l LEFT JOIN memories m ON m.memory_id = l.derived_id "
                "WHERE l.source_id=? ORDER BY l.derived_id",
                (memory_id,),
            ).fetchall()
            me = conn.execute("SELECT kind FROM memories WHERE memory_id=?", (memory_id,)).fetchone()
        return {
            "memory_id": memory_id,
            "kind": me["kind"] if me else None,
            "sources": [r["source_id"] for r in srcs],
            "derivatives": [{"memory_id": r["derived_id"], "kind": r["kind"]} for r in ders],
        }

    def affected_by(self, source_id: str) -> dict:
        """刪 source 前後都能查：受影響的 digest 與 card facts。"""
        lin = self.lineage_of(source_id)
        return {"source_id": source_id, "digests": lin["derivatives"], "card_facts": self.cards_affected_by(source_id)}
