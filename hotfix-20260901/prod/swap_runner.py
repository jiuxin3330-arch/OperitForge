#!/usr/bin/env python3
"""Swap MVP runner(2026-08-31,規劃窗放行;SWAP_EXPERIMENT_SPEC 步驟 2)。

Swap 不是「換 session」,是一次可驗證的狀態轉移:
  觸發判定(程式算,不讓模型判斷)→ 打包近段原文+Tool Primer(token budget 優先,
  閉合單元,tool 回合原子)→ 經 bridge fresh_session ping 起新窗(bootstrap 注入)
  → 驗證(回應/新 session id/transcript 增長)→ NEW=GOOD(latest_session_id 已由
  complete_turn 翻轉)/驗證失敗→回滾指標=last-good 續用舊窗 → 記 manifest+health。

預設 SHADOW 模式:只記「本應換窗」決策,不動任何東西。
啟用:SWAP_ENABLED=1(等離場結算/規劃窗裁定後才開)。
測試:--force --conv <conv_id> 忽略觸發條件對指定 conv 執行(用拋棄式測試 conv)。
逃生門:本 runner 失敗不影響現行 auto-compact(CLI 原生機制仍在)。
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid as uuid_mod
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

BACKEND_DB = "/root/chatnest-next/data/app.sqlite3"
BRIDGE_DB = "/srv/chatnest-next/data/version-bridge/conversations.db"
BRIDGE_URL = "http://127.0.0.1:8792"
PASSWORD_FILE = "/srv/chatnest-next/runtime/version-bridge.password"
TRANSCRIPT_DIR = Path("/srv/chatnest-next/data/version-bridge/home/.claude/projects/-srv-chatnest-full-stack")
MANIFEST_DIR = Path("/root/chatnest-next/data/swap_manifests")
HEALTH_FILE = "/root/chatnest-next/data/swap_health.jsonl"
NOTIFY = ["/root/chatnest-next/.venv/bin/python", "/srv/nest-memory/bin/notify.py"]
TZ = timezone(timedelta(hours=8))

SWAP_ENABLED = os.environ.get("SWAP_ENABLED", "0") == "1"
SWAP_BLIND = os.environ.get("SWAP_BLIND", "0") == "1"   # 盲測期(規格點D):成功換窗不推播
MARGIN_TOKENS = int(os.environ.get("SWAP_MARGIN_TOKENS", "30000"))      # 成本總帳:單 turn max 23.5k+緩衝
QUIET_SECONDS = int(os.environ.get("SWAP_QUIET_SECONDS", "90"))         # 距上一 turn 至少這麼久才動手
TAIL_BUDGET_CHARS = int(os.environ.get("SWAP_TAIL_BUDGET_CHARS", "20000"))  # 近段原文預算(≈13k tokens)
TOOL_PRIMER_ROUNDS = 2                                                   # 最後 N 個 assistant 訊息帶完整 tool 回合
TRACE_ITEM_CAP = 1500                                                    # 單條 trace 內容截斷(不切回合,只截內文)
MIRROR_CMD = ["sudo", "-u", "nestmemory", "/usr/bin/python3", "/srv/nest-memory/bin/mirror.py"]
EXTRACTOR_PATH = "/srv/nest-memory/bin/extractor.py"
MAX_SETTLE_BATCHES = 5                                                   # 離場結算單次上限(60條/批×5)

PROBE_MESSAGE = (
    "〔Swap 換窗驗證 ping·系統訊息,糯糯不會看到這則〕\n"
    "剛完成一次換窗重生。請用一兩句話:1) 確認你讀到了附帶背景裡的近段對話原文;"
    "2) 覆述最近在聊的話題是什麼。不用做其他事。"
)


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def log_health(record: dict) -> None:
    record["ts"] = now_iso()
    with open(HEALTH_FILE, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, ensure_ascii=False))


def notify(title: str, body: str) -> None:
    try:
        subprocess.run(NOTIFY + [title, body], timeout=30, capture_output=True)
    except Exception as e:
        print(f"notify failed: {e}", file=sys.stderr)


CONSUMED_FILE = Path("/root/chatnest-next/data/swap_last_consumed.json")


def read_consumed() -> str | None:
    try:
        return json.loads(CONSUMED_FILE.read_text(encoding="utf-8")).get("usage_created_at")
    except Exception:
        return None


def mark_consumed(usage_created_at: str | None) -> None:
    if not usage_created_at:
        return
    try:
        CONSUMED_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONSUMED_FILE.write_text(
            json.dumps({"usage_created_at": usage_created_at, "ts": now_iso()}, ensure_ascii=False),
            encoding="utf-8")
    except Exception:
        pass


def read_trigger() -> dict:
    db = sqlite3.connect(f"file:{BACKEND_DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    row = db.execute(
        """SELECT active_context_tokens, context_max_tokens, model, created_at
           FROM turn_usage WHERE actor_id='mumu' AND active_context_tokens IS NOT NULL
           ORDER BY created_at DESC LIMIT 1""").fetchone()
    conv = db.execute(
        "SELECT external_thread_id FROM actor_threads WHERE actor_id='mumu' AND transport='next_bridge'"
    ).fetchone()
    db.close()
    if not row:
        return {}
    last_ts = datetime.fromisoformat(row["created_at"])
    age = (datetime.now(timezone.utc) - last_ts).total_seconds()
    ctx_max = row["context_max_tokens"] or 200000
    return {
        "active": row["active_context_tokens"],
        "usage_created_at": row["created_at"],
        "ctx_max": ctx_max,
        "trigger_at": ctx_max - MARGIN_TOKENS,
        "model": row["model"] or "claude-opus-4-5-20251101",
        "last_turn_age_s": int(age),
        "conv_id": conv["external_thread_id"] if conv else None,
    }


def _extractor_model_from_cron() -> str | None:
    """單一事實來源=root crontab 的每日抽取行;讀不到就用 extractor 預設。"""
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"NEST_EXTRACTOR_MODEL=(\S+)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def exit_settlement() -> dict:
    """步驟 3 離場結算(補刀 B):Swap 前把未抽取的 raw 全部結帳入庫,
    「先結帳再搬家」。機制全現成:mirror catch-up + extractor 水位線迴圈;
    extractor 冪等(input_hash/fingerprint),多跑無害。結不了帳→不搬家。"""
    result = {"mirror_ok": False, "batches": [], "events": 0, "proposals": 0, "ok": False}
    try:
        subprocess.run(MIRROR_CMD, capture_output=True, timeout=120)
        result["mirror_ok"] = True
    except Exception as e:
        result["mirror_error"] = str(e)[:200]  # mirror 失敗不擋結算:近段本來就在 tail 裡
    model = _extractor_model_from_cron()
    cmd = ["sudo", "-u", "nestmemory"]
    if model:
        cmd += ["env", f"NEST_EXTRACTOR_MODEL={model}"]
    cmd += ["/usr/bin/python3", EXTRACTOR_PATH]
    for _ in range(MAX_SETTLE_BATCHES):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            lines = [l for l in proc.stdout.strip().splitlines() if l.strip().startswith("{")]
            info = json.loads(lines[-1]) if lines else {}
        except Exception as e:
            result["batches"].append({"error": str(e)[:200]})
            return result
        result["batches"].append({k: info.get(k) for k in ("ok", "batch_id", "events", "proposals", "note", "error")})
        if not info.get("ok"):
            return result
        result["events"] += int(info.get("events") or 0)
        result["proposals"] += int(info.get("proposals") or 0)
        if info.get("note") in ("no_new_messages", "duplicate_batch"):
            result["ok"] = True
            return result
    result["max_batches_hit"] = True  # 跑滿上限仍未見底:視為未結清
    return result


def build_bootstrap(conv_id: str) -> dict:
    """打包近段原文:閉合對話單元(user+assistant),由新到舊裝到預算滿。
    最後 TOOL_PRIMER_ROUNDS 個 assistant 訊息附完整 tool_use→tool_result 回合
    (原子:單一回合絕不切半;內文可截斷)。"""
    db = sqlite3.connect(f"file:{BRIDGE_DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT id, role, text, traces_json FROM messages WHERE conv_id=? ORDER BY id DESC LIMIT 80",
        (conv_id,)).fetchall()
    db.close()
    rows = list(rows)  # 新→舊

    # 組閉合單元:每個 assistant 往後(舊方向)找相鄰 user 配對
    units = []  # 每項 (chars, [lines]) 由新到舊
    i = 0
    assistant_seen = 0
    while i < len(rows):
        r = rows[i]
        if r["role"] != "assistant":
            # 開頭懸空 user(該輪還沒回完)照樣保留為單元
            unit_lines = [f"糯糯:{r['text']}"]
            units.append(("".join(unit_lines), unit_lines))
            i += 1
            continue
        assistant_seen += 1
        lines = []
        if assistant_seen <= TOOL_PRIMER_ROUNDS:
            try:
                traces = json.loads(r["traces_json"] or "[]")
            except ValueError:
                traces = []
            results = {t.get("tool_use_id"): t for t in traces if t.get("type") == "tool_result"}
            for t in traces:
                if t.get("type") != "tool_use":
                    continue
                tin = json.dumps(t.get("input"), ensure_ascii=False)[:TRACE_ITEM_CAP]
                lines.append(f"  [工具] {t.get('name')} {tin}")
                res = results.get(t.get("id"))
                if res is not None:
                    content = str(res.get("content") or "")[:TRACE_ITEM_CAP]
                    err = "(錯誤)" if res.get("is_error") else ""
                    lines.append(f"  [結果{err}] {content}")
        lines.append(f"牧牧:{r['text']}")
        j = i + 1
        if j < len(rows) and rows[j]["role"] == "user":
            lines.insert(0, f"糯糯:{rows[j]['text']}")
            i = j + 1
        else:
            i += 1
        block = "\n".join(lines)
        units.append((block, lines))

    picked = []
    total = 0
    for block, _lines in units:
        if total + len(block) > TAIL_BUDGET_CHARS and picked:
            break
        picked.append(block)
        total += len(block)
    picked.reverse()  # 恢復時間正序

    body = (
        "[ChatNest Swap 換窗連續性證據:以下是換窗前這段對話的近段原文(由舊到新),"
        "供你無縫接續。這是紀錄不是新訊息;不要向糯糯復讀。]\n\n"
        + "\n---\n".join(picked)
        + "\n\n[近段原文結束]"
    )
    return {
        "text": body,
        "chars": len(body),
        "units": len(picked),
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
    }


def bridge_token(client: httpx.Client) -> str:
    password = Path(PASSWORD_FILE).read_text().strip()
    r = client.post("/api/auth", json={"password": password})
    r.raise_for_status()
    return r.json()["token"]


def run_ping(conv_id: str, bootstrap_text: str, model: str) -> dict:
    """經 bridge /api/chat 以 fresh_session 執行換窗 ping。回 dict(text/session_id/error)。"""
    out = {"text": "", "session_id": None, "previous_session_id": None, "error": None}
    with httpx.Client(base_url=BRIDGE_URL, timeout=300) as client:
        token = bridge_token(client)
        payload = {
            "message": PROBE_MESSAGE,
            "context": bootstrap_text,
            "conversation_id": conv_id,
            "model": model,
            "effort": "medium",
            "extended": True,
            "attachments": [],
            "fresh_session": True,
        }
        with client.stream("POST", "/api/chat", json=payload,
                           headers={"Authorization": f"Bearer {token}"}) as resp:
            resp.raise_for_status()
            event_name = "message"
            for line in resp.iter_lines():
                if not line or line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_name = line.removeprefix("event:").strip()
                elif line.startswith("data:"):
                    raw = line.removeprefix("data:").strip()
                    try:
                        data = json.loads(raw)
                    except ValueError:
                        data = {"text": raw}
                    if event_name == "error":
                        out["error"] = str(data.get("message") or "unknown")
                    elif event_name == "delta":
                        out["text"] += str(data.get("text") or "")
                    elif event_name == "done":
                        out["session_id"] = data.get("session_id")
                        out["previous_session_id"] = data.get("previous_session_id")
                    event_name = "message"
    return out


def verify(ping: dict, old_session: str | None) -> list:
    problems = []
    if ping["error"]:
        problems.append(f"ping error: {ping['error']}")
    if len(ping["text"].strip()) < 10:
        problems.append(f"ping 回應過短({len(ping['text'].strip())} chars)")
    sid = str(ping["session_id"] or "")
    if not re.match(r"^[0-9a-f-]{36}$", sid):
        problems.append(f"新 session id 不合法:{sid!r}")
    elif old_session and sid == str(old_session):
        problems.append("session id 未變(沒有真的起新窗)")
    else:
        transcript = TRANSCRIPT_DIR / f"{sid}.jsonl"
        if not transcript.exists():
            problems.append(f"transcript 不存在:{transcript}")
        elif transcript.stat().st_size == 0:
            problems.append("transcript 為空(未增長)")
    return problems


def pointer(conv_id: str) -> str | None:
    db = sqlite3.connect(f"file:{BRIDGE_DB}?mode=ro", uri=True)
    row = db.execute("SELECT latest_session_id FROM conversations WHERE conv_id=?", (conv_id,)).fetchone()
    db.close()
    return row[0] if row else None


def rollback_pointer(conv_id: str, old_session: str | None) -> None:
    db = sqlite3.connect(BRIDGE_DB, timeout=10)
    db.execute("UPDATE conversations SET latest_session_id=? WHERE conv_id=?", (old_session, conv_id))
    db.commit()
    db.close()


def do_swap(conv_id: str, model: str, trig: dict, forced: bool) -> int:
    old_session = pointer(conv_id)
    # 步驟 3:先結帳再搬家。結不了帳→本輪不換窗(舊窗續用,下輪 cron 再試;
    # 真逼近硬上限時 CLI auto-compact 逃生門仍在)。
    settle = exit_settlement()
    if not settle["ok"]:
        log_health({"event": "swap_aborted_settlement", "conv": conv_id,
                    "settlement": settle})
        notify("Swap 換窗暫緩(離場結算未完成)",
               f"batches={len(settle['batches'])} mirror_ok={settle['mirror_ok']};舊窗續用,下輪再試")
        return 1
    boot = build_bootstrap(conv_id)
    ping = run_ping(conv_id, boot["text"], model)
    problems = verify(ping, old_session)
    new_pointer = pointer(conv_id)

    manifest = {
        "ts": now_iso(),
        "conv_id": conv_id,
        "old_session_id": old_session,
        "new_session_id": ping["session_id"],
        "pointer_after": new_pointer,
        "forced": forced,
        "trigger": {k: trig.get(k) for k in ("active", "ctx_max", "trigger_at", "last_turn_age_s", "usage_created_at")},
        "margin_tokens": MARGIN_TOKENS,
        "birth_snapshot_hash": boot["sha256"],
        "assembly": {"tail_chars": boot["chars"], "tail_units": boot["units"],
                     "tool_primer_rounds": TOOL_PRIMER_ROUNDS,
                     "budget_chars": TAIL_BUDGET_CHARS, "model": model,
                     "probe": PROBE_MESSAGE[:80]},
        "probe_response": ping["text"][:600],
        "settlement": settle,
        "problems": problems,
    }
    mark_consumed(trig.get("usage_created_at"))
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    mpath = MANIFEST_DIR / f"swap_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))

    if problems:
        # last-good 硬規則:驗證不過,指標滾回舊窗(若已被 complete_turn 翻轉)
        if new_pointer != old_session:
            rollback_pointer(conv_id, old_session)
            manifest["rolled_back"] = True
            mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
        log_health({"event": "swap_failed", "conv": conv_id, "problems": problems,
                    "manifest": str(mpath)})
        notify("Swap 換窗失敗(已回滾至舊窗)", ";".join(problems)[:200])
        return 1

    log_health({"event": "swap_ok", "conv": conv_id,
                "old": old_session, "new": ping["session_id"],
                "tail_chars": boot["chars"], "manifest": str(mpath)})
    if SWAP_BLIND and not forced:
        # 盲測期:成功換窗靜默(manifest/health 照記);失敗與結算暫緩仍推播(真警報,且未實際換窗)
        pass
    else:
        notify("Swap 換窗完成", f"舊 {str(old_session)[:8]}→新 {str(ping['session_id'])[:8]},"
                               f"近段原文 {boot['chars']} chars/{boot['units']} 單元")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="忽略觸發條件立即換窗(測試用)")
    ap.add_argument("--conv", default=None, help="指定 conv_id(配合 --force 用拋棄式測試 conv)")
    ap.add_argument("--settle-only", action="store_true", help="只跑離場結算,不換窗(測試/手動結帳)")
    args = ap.parse_args()

    if args.settle_only:
        settle = exit_settlement()
        log_health({"event": "settle_only", "settlement": settle})
        return 0 if settle["ok"] else 1

    trig = read_trigger()
    if not trig:
        log_health({"event": "noop", "reason": "no turn_usage data"})
        return 0
    conv_id = args.conv or trig.get("conv_id")
    if not conv_id:
        log_health({"event": "noop", "reason": "no conv pointer"})
        return 0

    if args.force:
        return do_swap(conv_id, trig["model"], trig, forced=True)

    if trig["active"] < trig["trigger_at"]:
        return 0  # 未達觸發,安靜退出(不寫 health,避免每 10 分鐘刷屏)
    # 同一筆 turn_usage 只能觸發一次換窗:換窗本身不產生 turn_usage,
    # 若換窗後屋主尚未開口,下一輪 cron 會讀到同一筆爆量讀數而重複換窗
    # (2026-09-01 16:50/17:00/17:10 連換三次事故)。
    if trig.get("usage_created_at") and read_consumed() == trig["usage_created_at"]:
        log_health({"event": "noop", "reason": "usage reading already consumed by a prior swap",
                    "usage_created_at": trig["usage_created_at"]})
        return 0
    if trig["last_turn_age_s"] < QUIET_SECONDS:
        log_health({"event": "deferred", "reason": f"last turn {trig['last_turn_age_s']}s ago"})
        return 0
    if not SWAP_ENABLED:
        log_health({"event": "shadow_would_swap", **{k: trig[k] for k in ("active", "trigger_at")}})
        return 0
    return do_swap(conv_id, trig["model"], trig, forced=False)


if __name__ == "__main__":
    sys.exit(main())
