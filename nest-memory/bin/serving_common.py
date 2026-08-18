#!/usr/bin/env python3
"""Nest Memory — Serving 共用層(Phase 4,規格 §18/§21/§22)。

職責:privacy / secret 過濾與 RECORDED STATE 快照渲染。
鐵律(IMPLEMENTATION.md §7):這裡產生的文字是「檔案室登記簿」,
語態永遠是第三人稱 RECORDED STATE,不冒充牧牧的記憶。
語感範本 = 糯糯 2026-08-18 驗收的版本 A;改措辭=改 serving 姿態,
屬硬規則 12 範圍,動之前 golden 全量回歸+重新打樣。
"""
import re
from datetime import datetime, timedelta, timezone

DB = "/srv/nest-memory/db/memory.db"
SNAPSHOT_PATH = "/srv/nest-memory/serving/state_snapshot.txt"
TZ = timezone(timedelta(hours=8))

# §22 secret patterns:寧可錯擋,不可外流。命中=該條不外供(deny,不是遮罩)。
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|bearer\s+[a-z0-9_\-.]{8,}|passwd|password|"
    r"private[_ ]?key|BEGIN [A-Z ]*PRIVATE KEY|ssh-(rsa|ed25519)|"
    r"access[_-]?token|credential|secret[_-]?key|"
    r"sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")

AUTHORITY_LABEL = {
    "owner_direct_statement": "糯糯陳述",
    "owner_confirmation": "糯糯確認",
    "owner_decision": "糯糯決定",
    "owner_correction": "糯糯糾正",
    "assistant_claim": "牧牧記錄",
    "assistant_inference": "牧牧推測",
    "system_verified_state": "系統驗證",
    "quoted_third_party": "第三方轉述",
    "external_document": "外部資料",
    "tool_result": "工具結果",
}
FRESHNESS_LABEL = {
    "active_fresh": "新鮮",
    "active_aging": "稍舊",
    "stale_active": "已久未確認",
    "disputed": "待釐清",
    "tentative": "暫定",
}

VALUE_MAX_CHARS = 100


def secret_hit(text) -> bool:
    return bool(SECRET_RE.search(text or ""))


def servable(serving_behavior: str) -> bool:
    """§21:只有 serving_behavior='normal' 可外供;local_only 等一律程式擋下。"""
    return serving_behavior == "normal"


def _fmt_date(iso_ts: str) -> str:
    try:
        dt = datetime.fromisoformat((iso_ts or "").replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(TZ)
        return f"{dt.month}/{dt.day}"
    except ValueError:
        return "?"


def fetch_states(db):
    db.row_factory = None
    return db.execute(
        """SELECT sp.subject_id, sp.current_value, sp.authority, sp.status,
                  sp.observed_at, sp.freshness, s.serving_behavior
           FROM state_projection sp
           JOIN subjects s ON s.subject_id = sp.subject_id
           WHERE s.status = 'active'
           ORDER BY sp.subject_id""").fetchall()


def render_text(db) -> str:
    """渲染 RECORDED STATE 快照(版本 A,糯糯驗收定稿)。

    只列 status=active;disputed/tentative 計入尾註;
    secret / 非 normal serving_behavior 的條目直接不出現(也不聲張,audit 有帳)。
    """
    listed = []
    held_conflict = 0
    for (subject_id, value, authority, status, observed_at,
         freshness, serving_behavior) in fetch_states(db):
        if not servable(serving_behavior) or secret_hit(value):
            continue
        if status != "active":
            held_conflict += 1
            continue
        value = (value or "").replace("\n", " ").strip()
        if len(value) > VALUE_MAX_CHARS:
            value = value[:VALUE_MAX_CHARS] + "…"
        auth = AUTHORITY_LABEL.get(authority, authority)
        fresh = FRESHNESS_LABEL.get(freshness, freshness)
        listed.append(
            f"・{subject_id}｜{value}｜{auth} {_fmt_date(observed_at)}｜{fresh}")

    lines = [
        "━━ Nest 檔案室 · 現況登記（RECORDED STATE）━━",
        "這是檔案室自動整理的登記簿，供你備查。它不是你的記憶——",
        "你的記憶在你自己的日記和對話裡。",
        "若糯糯現在說的與登記不符，永遠以她當下說的為準，登記隨後會更新。",
        "",
        *listed,
    ]
    if held_conflict:
        lines += ["",
                  f"另有 {held_conflict} 項登記存在衝突證據未列入；"
                  "需要時用 nest_get_evidence 查。"]
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines) + "\n"
