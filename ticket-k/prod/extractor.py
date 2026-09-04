#!/usr/bin/env python3
"""Nest Memory — Phase 2 Event Extractor(Haiku 書記官)。

以 nestmemory 身份執行。批次讀 raw_messages → Haiku 抽取「有證據的狀態變化」
→ 本地驗證/指紋冪等/密令掃描/升級規則 → 寫入 events(模型只提案,commit 在本地)。

硬規則落實:
- subject 必須在 Registry 內;不在 → 轉 subject_proposals(PROPOSE_NEW_SUBJECT)
- impact/confidence 只有 low/medium/high;非法值 → 降級+escalate
- 來源必須引用本批次內的 raw rowid;無有效來源 → 丟棄(來源不足)
- fingerprint 冪等:同批重跑不產生 duplicate
- 密令掃描:命中 → secret=1(egress deny)
- deterministic escalation:低信心高影響/同 subject 衝突/隱私安全身分類
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

DB = "/srv/nest-memory/db/memory.db"
TOKEN_FILE = "/srv/nest-memory/state/.claude_token"
HEALTH_FILE = "/srv/nest-memory/health/extract_last_run.json"
API_URL = "https://api.anthropic.com/v1/messages"
CLI_SYSTEM = "You are Claude Code, Anthropic's official CLI for Claude."
# 預設 Haiku;A/B regression 或正式換模用環境變數覆寫(合稿附帶小案)
MODEL = os.environ.get("NEST_EXTRACTOR_MODEL", "claude-haiku-4-5-20251001")
RETRY_STATUS = {429, 500, 502, 503, 504, 529}
RETRY_DELAY_S = 60
RETRY_MAX = 3
EXTRACTOR_VERSION = "extractor_v2"
# 系統信封:整則都是機器產生的即時提示,不是聊天內容,永不進逐字稿。
# (TICKET-G 牌局喚醒;比照 TIME_ANCHOR_SPEC 的 ephemeral 豁免)
EPHEMERAL_PREFIXES = ("〔牌局喚醒·",)
BATCH_LIMIT = 60
TZ = timezone(timedelta(hours=8))

AUTHORITIES = {
    "owner_direct_statement", "owner_decision", "owner_confirmation",
    "owner_correction", "assistant_proposal", "assistant_inference",
    "assistant_claim", "tool_verified_result", "system_verified_state",
    "quoted_third_party", "external_content",
}
LEVELS = {"low", "medium", "high"}
ESCALATE_TYPES = {"privacy_change", "security_change", "identity_change"}
SECRET_RE = re.compile(
    r"(api[_-]?key|bearer\s+[a-z0-9_\-\.]{16,}|password|passwd|secret|"
    r"BEGIN [A-Z ]*PRIVATE KEY|ssh-(rsa|ed25519)\s+[A-Za-z0-9+/=]{30,}|"
    r"AGE-SECRET-KEY|sk-[A-Za-z0-9_\-]{20,}|token[=:]\s*\S{16,})", re.I)

PROMPT = """你是 Nest Memory 的抽取書記官。從下面的聊天逐字稿中抽取「有證據的狀態變化」(Event),嚴格遵守:

1. Event 是狀態變化,不是摘要。純閒聊、情話、玩笑、系統模板訊息 → 不產生 Event。
   牌局/遊戲的即時互動(誰出什麼牌、輪到誰、名次)是玩樂過程,不是狀態變化 → 不產生 Event。
2. subject_id 只能從下方 Subject Registry 挑選。真的找不到但確實重要 → 放進 subject_proposals 提案,不要硬塞。
3. authority 只能是: owner_direct_statement / owner_decision / owner_confirmation / owner_correction / assistant_proposal / assistant_inference / assistant_claim / tool_verified_result / system_verified_state / quoted_third_party / external_content。
   鐵則: assistant 的提議≠owner 決定;assistant 說「完成了」是 assistant_claim 不是 verified;owner 說「可能/再看看」不構成 decision。
4. impact 和 confidence 只有 low/medium/high。
5. 每個 Event 必須引用至少一個來源訊息的 rowid(從逐字稿的 [rowid] 標記取),並附一句原文引述。
6. value_before 不確定就留 null,不要編造。occurred_at 用來源訊息的時間。
7. 用戶(owner)是糯糯,assistant 是牧牧。

只輸出 JSON,格式:
{"events":[{"subject_id":"...","event_type":"decision_change|state_change|preference_change|correction|milestone|config_change","value_before":null,"value_after":"...","summary":"一句話","authority":"...","impact":"low","confidence":"high","occurred_at":"ISO時間","sources":[{"rowid":123,"quote":"原文"}]}],"subject_proposals":[{"proposed_key":"...","reason":"...","example_quote":"..."}]}

## Subject Registry(只能用這些)
{SUBJECTS}

## 逐字稿
{TRANSCRIPT}"""


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read_token() -> str:
    m = re.search(r"CLAUDE_CODE_OAUTH_TOKEN=(.+)", open(TOKEN_FILE).read())
    return m.group(1).strip().strip("\"'") if m else ""


EXTRACT_TOOL = {
    "name": "record_events",
    "description": "登記抽取到的狀態變化事件與新主題提案",
    "input_schema": {
        "type": "object",
        "properties": {
            "events": {"type": "array", "items": {"type": "object", "properties": {
                "subject_id": {"type": "string"},
                "event_type": {"type": "string"},
                "value_before": {"type": ["string", "null"]},
                "value_after": {"type": "string"},
                "summary": {"type": "string"},
                "authority": {"type": "string"},
                "impact": {"type": "string"},
                "confidence": {"type": "string"},
                "occurred_at": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "object", "properties": {
                    "rowid": {"type": "integer"}, "quote": {"type": "string"}},
                    "required": ["rowid"]}},
            }, "required": ["subject_id", "event_type", "value_after", "authority",
                            "impact", "confidence", "sources"]}},
            "subject_proposals": {"type": "array", "items": {"type": "object", "properties": {
                "proposed_key": {"type": "string"}, "reason": {"type": "string"},
                "example_quote": {"type": "string"}}, "required": ["proposed_key"]}},
        },
        "required": ["events", "subject_proposals"],
    },
}


def call_haiku(prompt: str, model: str | None = None) -> dict:
    """tool-use 強制結構化輸出:API 層保證 JSON 合法,不靠模型手寫。

    429/5xx 退避重試 60s×3(合稿附帶小案;2026-08-30 batch 24 實際被 429 打掛)。
    其他錯誤照舊直接拋,batch 落 failed 留痕。"""
    body = json.dumps({
        "model": model or MODEL, "max_tokens": 8000,
        "system": CLI_SYSTEM,
        "tools": [EXTRACT_TOOL],
        "tool_choice": {"type": "tool", "name": "record_events"},
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    data = None
    for attempt in range(RETRY_MAX + 1):
        req = urllib.request.Request(API_URL, data=body, headers={
            "authorization": f"Bearer {read_token()}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as exc:
            if exc.code in RETRY_STATUS and attempt < RETRY_MAX:
                print(f"call_haiku: HTTP {exc.code},{RETRY_DELAY_S}s 後重試"
                      f"({attempt + 1}/{RETRY_MAX})", file=sys.stderr)
                time.sleep(RETRY_DELAY_S)
                continue
            raise
    for block in data.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "record_events":
            return block.get("input") or {}
    raise ValueError("no tool_use block in response")


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def is_ephemeral(msg) -> bool:
    """系統信封訊息(整則丟棄,連 rowid 都不給引用)。"""
    return str(msg.get("text") or "").lstrip().startswith(EPHEMERAL_PREFIXES)


def extract(db, messages, subjects, batch_id, model=None):
    """回傳 (valid_events, proposals, dropped, container_drops)。

    container_drops>0 代表整個 events/subject_proposals 容器沒解出來 —— 那不是
    「這批沒東西」,是「這批沒讀到」,由 commit_batch 判成 failed 讓明晚重試。
    """
    messages = [m for m in messages if not is_ephemeral(m)]
    if not messages:
        return [], [], 0, 0
    transcript = "\n".join(
        f"[{m['rowid']}] {m['ts']} {m['role']}: {m['text'][:600]}"
        for m in messages)
    subj_desc = "\n".join(
        f"- {s['subject_id']}({s['volatility']}): {s['description']}"
        for s in subjects)
    parsed = call_haiku(PROMPT.replace("{SUBJECTS}", subj_desc)
                              .replace("{TRANSCRIPT}", transcript), model)
    return parse_response(db, parsed, messages, subjects, batch_id)



def _dump_container(name, raw, batch_id):
    """把解不開的原文落檔,供事後查證。

    2026-09-02 那天只能靠重跑猜模型到底回了什麼 —— 落檔就是為了不用再猜。
    batch_id 0 是 golden fixture 的批號,測試不該在生產的 health/ 底下留垃圾。
    """
    if not batch_id:
        return
    try:
        directory = os.path.join(os.path.dirname(HEALTH_FILE), "extract_dumps")
        os.makedirs(directory, mode=0o700, exist_ok=True)
        path = os.path.join(directory, f"batch_{batch_id}_{name}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
        os.chmod(path, 0o600)
        print(f"parse_response: 原文已落檔 {path}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 — 落檔失敗不該反殺這批
        print(f"parse_response: 落檔失敗:{exc}", file=sys.stderr)


def _unwrap_container(name, raw, batch_id):
    """模型偶發把 events / subject_proposals 整個陣列包成一個 JSON 字串。

    TICKET-K:兩個模型(Sonnet 5、Haiku 4.5)都會偶發這種格式抖動,
    不是哪一個模型特有的毛病 —— 所以這裡解開它,而不是換模型。

    解得開就用;解不開把原文落檔後照原樣交回去,由呼叫端當成容器層丟棄處理。
    """
    if not isinstance(raw, str):
        return raw
    try:
        inner = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 — 壞 JSON 是預期情況之一
        print(f"parse_response: {name} 字串容器解不開:{exc}", file=sys.stderr)
        _dump_container(name, raw, batch_id)
        return raw
    if isinstance(inner, list):
        print(f"parse_response: {name} 為 JSON 字串容器,已解開({len(inner)} 元素)",
              file=sys.stderr)
        return inner
    print(f"parse_response: {name} 字串容器解開後不是 list({type(inner).__name__})",
          file=sys.stderr)
    _dump_container(name, raw, batch_id)
    return raw


def parse_response(db, parsed, messages, subjects, batch_id):
    """純解析(無 LLM 呼叫,golden runner 可直接餵 fixture)。

    TICKET-C 加固:模型偶爾在 events/subject_proposals 陣列混入純字串或缺欄位
    元素(batch 14/16 的 AttributeError 根因)。逐元素驗型別:壞元素丟棄+計數
    +記 stderr,絕不整批 fail。raw 原文在庫,丟棄的只是該元素的整理結果。

    TICKET-K 補上一層區分:逐元素丟棄照舊(commit),但整個容器沒讀到
    (container_drops)要讓這批 failed —— 見 commit_batch。
    """
    if not isinstance(parsed, dict):
        print(f"parse_response: 回傳非 dict({type(parsed).__name__}),整批視為空", file=sys.stderr)
        parsed = {}
    valid_rowids = {m["rowid"] for m in messages}
    subj_ids = {s["subject_id"] for s in subjects}
    events, proposals, dropped, container_drops = [], [], 0, 0

    raw_proposals = _unwrap_container("subject_proposals", parsed.get("subject_proposals") or [], batch_id)
    if not isinstance(raw_proposals, list):
        print(f"parse_response: subject_proposals 非 list({type(raw_proposals).__name__}),丟棄", file=sys.stderr)
        dropped += 1
        container_drops += 1
        raw_proposals = []
    for p in raw_proposals:
        if isinstance(p, dict) and isinstance(p.get("proposed_key"), str) and p["proposed_key"].strip():
            proposals.append(p)
        else:
            dropped += 1
            print(f"parse_response: 丟棄壞 proposal 元素:{str(p)[:120]}", file=sys.stderr)

    raw_events = _unwrap_container("events", parsed.get("events") or [], batch_id)
    if not isinstance(raw_events, list):
        print(f"parse_response: events 非 list({type(raw_events).__name__}),丟棄", file=sys.stderr)
        dropped += 1
        container_drops += 1
        raw_events = []
    for ev in raw_events:
        if not isinstance(ev, dict):
            dropped += 1
            print(f"parse_response: 丟棄非 dict event 元素:{str(ev)[:120]}", file=sys.stderr)
            continue
        try:
            raw_sources = ev.get("sources") or []
            if not isinstance(raw_sources, list):
                raw_sources = []
            sources = [s for s in raw_sources
                       if isinstance(s, dict)
                       and isinstance(s.get("rowid"), int) and s["rowid"] in valid_rowids]
            if not sources:
                dropped += 1
                continue
            subject = str(ev.get("subject_id") or "")
            if subject not in subj_ids:
                proposals.append({"proposed_key": subject or "(空)",
                                  "reason": "extractor 使用了 Registry 外的 subject",
                                  "example_quote": str(ev.get("summary") or "")[:200]})
                dropped += 1
                continue
            authority = str(ev.get("authority") or "")
            if authority not in AUTHORITIES:
                authority = "assistant_inference"
            impact = ev.get("impact") if ev.get("impact") in LEVELS else "low"
            confidence = ev.get("confidence") if ev.get("confidence") in LEVELS else "low"
            occurred = str(ev.get("occurred_at") or messages[0]["ts"])
            value_after = str(ev.get("value_after") or "")
            if not value_after:
                dropped += 1
                continue
            esc, reasons = 0, []
            if confidence == "low" and impact == "high":
                esc = 1
                reasons.append("low_confidence_high_impact")
            if str(ev.get("event_type")) in ESCALATE_TYPES:
                esc = 1
                reasons.append("sensitive_type")
            conflict = db.execute(
                "SELECT 1 FROM events WHERE subject_id=? AND value_after<>? AND date(occurred_at)=date(?) LIMIT 1",
                (subject, value_after, occurred)).fetchone()
            if conflict:
                esc = 1
                reasons.append("same_day_conflict")
            # 跨日衝突(P3 複審新發現):非 owner 權威的證據與當前 active state 不符
            # → 升級,防止弱權威復述舊說法悄悄蓋掉 owner 糾正。
            # owner_* 權威不觸發:owner 當下陳述優先(規格 §18),真改變不得卡死。
            if not authority.startswith("owner_"):
                try:
                    cur_state = db.execute(
                        "SELECT current_value FROM state_projection WHERE subject_id=? AND status='active'",
                        (subject,)).fetchone()
                    if cur_state and cur_state[0] != value_after:
                        esc = 1
                        reasons.append("conflicts_active_state")
                except sqlite3.OperationalError:
                    pass  # 表尚未建立(初期/沙盒)
            blob = value_after + str(ev.get("summary") or "") + "".join(s.get("quote", "") for s in sources)
            secret = 1 if SECRET_RE.search(blob) else 0
            events.append({
                "fingerprint": sha(f"{subject}|{ev.get('event_type')}|{value_after}|{occurred[:10]}"),
                "subject_id": subject,
                "event_type": str(ev.get("event_type") or "state_change"),
                "value_before": ev.get("value_before"),
                "value_after": value_after,
                "summary": str(ev.get("summary") or "")[:500],
                "authority": authority, "impact": impact, "confidence": confidence,
                "occurred_at": occurred, "batch_id": batch_id,
                "escalated": esc, "escalation_reason": ",".join(reasons) or None,
                "secret": secret, "sources": sources,
            })
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            dropped += 1
            print(f"parse_response: 丟棄壞 event 元素({type(exc).__name__}: {exc}):{str(ev)[:120]}", file=sys.stderr)
    return events, proposals, dropped, container_drops


def _fail_batch(db, batch_id, exc):
    """標 failed 並回傳 health 用的 result。

    不 commit 就代表游標不前進,明晚同一段訊息會再抽一次 —— 重試是這裡唯一的
    補救手段,所以失敗一定要留在帳上,不能安靜地算過去。
    """
    db.execute(
        "UPDATE extraction_batches SET status='failed', finished_at=?, error=? WHERE batch_id=?",
        (now_iso(), f"{type(exc).__name__}: {exc}"[:500], batch_id))
    db.commit()
    return {"ts": now_iso(), "ok": False, "batch_id": batch_id,
            "error": f"{type(exc).__name__}: {exc}"[:200]}


class ContainerDropError(RuntimeError):
    """整個 events / subject_proposals 容器沒讀出來。

    這跟「這批真的沒有值得記的事」是兩回事,可是落到帳上會長得一模一樣:
    0 events、committed、游標前進。2026-09-02 一整天(第一次約會、逛寶雅的
    花椰菜、StackChan 沒電)就是這樣安靜地沒進檔案室的。
    """


def commit_batch(db, batch_id, events, proposals, dropped, container_drops,
                 from_rowid, to_rowid, input_hash):
    """把一批的結果落帳,回傳 health 用的 result dict。

    TICKET-K 第 2 點:容器層丟棄 → 這批標 failed(不 commit、游標不前進、
    明晚自動重試);逐元素丟棄維持現行行為(照樣 commit,raw 原文都還在庫裡)。
    """
    try:
        if container_drops:
            raise ContainerDropError(
                f"頂層容器解析失敗 {container_drops} 處,整批不可信"
            )
        with db:
            n = 0
            for ev in events:
                sources = ev.pop("sources")
                c = db.execute(
                    """INSERT OR IGNORE INTO events(fingerprint,subject_id,event_type,
                           value_before,value_after,summary,authority,impact,confidence,
                           occurred_at,batch_id,created_by_model,extractor_version,
                           escalated,escalation_reason,secret,created_at)
                       VALUES(:fingerprint,:subject_id,:event_type,:value_before,
                           :value_after,:summary,:authority,:impact,:confidence,
                           :occurred_at,:batch_id,:model,:version,:escalated,
                           :escalation_reason,:secret,:now)""",
                    {**ev, "model": MODEL, "version": EXTRACTOR_VERSION, "now": now_iso()})
                if c.rowcount:
                    n += 1
                    for s in sources:
                        db.execute(
                            "INSERT INTO event_sources(event_id,source_rowid,quote) VALUES(?,?,?)",
                            (c.lastrowid, s["rowid"], str(s.get("quote") or "")[:300]))
            for p in proposals:
                if db.execute("SELECT 1 FROM subject_proposals WHERE proposed_key=? AND status='pending'",
                              (str(p.get("proposed_key"))[:100],)).fetchone():
                    continue  # 提案去重:同 key 已有 pending 就不重複入列
                db.execute(
                    """INSERT INTO subject_proposals(proposed_key,reason,example_quote,batch_id,created_at)
                       VALUES(?,?,?,?,?)""",
                    (str(p.get("proposed_key"))[:100], str(p.get("reason") or "")[:300],
                     str(p.get("example_quote") or "")[:300], batch_id, now_iso()))
            db.execute(
                "UPDATE extraction_batches SET status='committed', finished_at=?, events_count=? WHERE batch_id=?",
                (now_iso(), n, batch_id))
            db.execute(
                """INSERT INTO egress_audit(ts,provider,model,purpose,from_rowid,to_rowid,payload_hash,notes)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (now_iso(), "anthropic", MODEL, "event_extraction",
                 from_rowid, to_rowid, input_hash, f"events={n} dropped={dropped}"))
        result = {"ts": now_iso(), "ok": True, "batch_id": batch_id,
                  "events": n, "proposals": len(proposals), "dropped": dropped,
                  "range": [from_rowid, to_rowid]}
    except Exception as exc:  # noqa: BLE001 — batch 必須留下失敗紀錄
        result = _fail_batch(db, batch_id, exc)
    return result


def main() -> int:
    os.umask(0o077)
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")

    last = db.execute(
        "SELECT COALESCE(MAX(to_rowid),0) FROM extraction_batches WHERE status='committed'"
    ).fetchone()[0]
    messages = [
        {"rowid": r["source_rowid"], "role": r["role"],
         "ts": r["source_timestamp"], "text": r["text"]}
        for r in db.execute(
            """SELECT source_rowid, role, source_timestamp, text FROM raw_messages
               WHERE source_rowid > ? AND deleted=0 ORDER BY source_rowid LIMIT ?""",
            (last, BATCH_LIMIT))]
    if not messages:
        result = {"ts": now_iso(), "ok": True, "batch_id": None,
                  "events": 0, "proposals": 0, "note": "no_new_messages"}
        with open(HEALTH_FILE, "w") as f:
            json.dump(result, f)
        print(json.dumps(result, ensure_ascii=False))  # 呼叫方(離場結算)靠 stdout 判定
        return 0

    subjects = [dict(r) for r in db.execute(
        "SELECT subject_id, description, volatility FROM subjects WHERE status='active'")]
    if not subjects:
        print("Subject Registry 為空,拒絕抽取(需要糯糯人審的初始清單)", file=sys.stderr)
        return 1

    from_rowid, to_rowid = messages[0]["rowid"], messages[-1]["rowid"]
    input_hash = sha("|".join(f"{m['rowid']}:{m['role']}:{len(m['text'])}" for m in messages))
    dup = db.execute(
        "SELECT batch_id FROM extraction_batches WHERE input_hash=? AND status='committed'",
        (input_hash,)).fetchone()
    if dup:
        result = {"ts": now_iso(), "ok": True, "batch_id": dup[0],
                  "events": 0, "proposals": 0, "note": "duplicate_batch"}
        with open(HEALTH_FILE, "w") as f:
            json.dump(result, f)
        print(json.dumps(result, ensure_ascii=False))
        return 0

    cur = db.execute(
        """INSERT INTO extraction_batches(from_rowid,to_rowid,input_hash,model,
               prompt_version,status,started_at) VALUES(?,?,?,?,?,'pending',?)""",
        (from_rowid, to_rowid, input_hash, MODEL, EXTRACTOR_VERSION, now_iso()))
    batch_id = cur.lastrowid
    db.commit()

    try:
        events, proposals, dropped, container_drops = extract(db, messages, subjects, batch_id)
    except Exception as exc:  # noqa: BLE001 — 抽取本身炸掉也要留下失敗紀錄
        result = _fail_batch(db, batch_id, exc)
    else:
        result = commit_batch(db, batch_id, events, proposals, dropped, container_drops,
                              from_rowid, to_rowid, input_hash)
    db.close()
    with open(HEALTH_FILE, "w") as f:
        json.dump(result, f, ensure_ascii=False)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
