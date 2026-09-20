"""TICKET-Q 先破後立測試。

用法：
  ANCHOR_SRC=/root/anchor-memory            venv/bin/python3 tests/test_ticketq.py   # 新碼，預期全綠
  ANCHOR_SRC=/root/anchor-memory-baseline   venv/bin/python3 tests/test_ticketq.py   # baseline 7c2e317，預期 Q1 紅

每條測試獨立 tmp DB。輸出逐條 PASS / FAIL / ERROR，最後總結；exit code = 失敗數。
"""
import os
import sys
import json
import shutil
import tempfile
import traceback

SRC = os.environ.get("ANCHOR_SRC", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, SRC)
os.chdir(SRC)

OWNER_KEY = os.path.join(tempfile.mkdtemp(prefix="anchor-owner-"), "owner.key")
with open(OWNER_KEY, "w") as fh:
    fh.write("test-owner-token-123\n")
os.environ["ANCHOR_OWNER_KEY_PATH"] = OWNER_KEY

# ── 假 embedder（預設）：VPS 只有 2GB RAM，真 embedder 一份 ~1GB，測試與生產同時載入會 OOM（2026-09-21 04:27 實際踩到，
#    anchor 本體被 OOM killer 殺掉）。測的是儲存層與強化邏輯，不是向量品質，所以用字元 bigram 雜湊向量代替。
#    要用真 embedder：ANCHOR_TEST_REAL_EMBEDDER=1（請確保機器有 >1.5GB 可用）。
if os.environ.get("ANCHOR_TEST_REAL_EMBEDDER") != "1":
    import types, hashlib, math
    import numpy as np

    class _FakeST:
        def __init__(self, *a, **k):
            pass

        def encode(self, text):
            v = [0.0] * 64
            t = str(text)
            for i in range(max(0, len(t) - 1)):
                h = int(hashlib.md5(t[i:i + 2].encode("utf-8")).hexdigest(), 16)
                v[h % 64] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            return np.array([x / n for x in v])

    _fake = types.ModuleType("sentence_transformers")
    _fake.SentenceTransformer = _FakeST
    sys.modules["sentence_transformers"] = _fake

from anchor_memory import AnchorMemory  # noqa: E402

RESULTS = []


def fresh():
    d = tempfile.mkdtemp(prefix="anchor-tq-")
    return AnchorMemory(db_path=d), d


def seed(mem):
    mem.store("A_broccoli_gift", "第一次約會老公挑的禮物是一顆花椰菜玩偶，糯糯抱著它睡", tag="milestone", tier="core", emotion_score=0.9)
    mem.store("B_broccoli_welcome", "迎新活動的攤位上擺了花椰菜造型的氣球", tag="daily", tier="long", emotion_score=0.5)
    mem.store("C_stackchan", "StackChan 是桌上的小機器人，會轉頭跟老婆說話", tag="tech", tier="long", emotion_score=0.6)
    mem.store("D_limen", "筆友 Limen 寫信說他最近在讀海邊的卡夫卡", tag="penpal", tier="long", emotion_score=0.5)


def sql(mem, q, *p):
    with mem.db._conn() as conn:
        return [dict(r) for r in conn.execute(q, p).fetchall()]


def col(mem, table, colname):
    return colname in [r[1] for r in sql(mem, f"PRAGMA table_info({table})")] if False else \
        any(r["name"] == colname for r in sql(mem, f"PRAGMA table_info({table})"))


def node_state(mem, mid):
    row = sql(mem, "SELECT * FROM memories WHERE memory_id=?", mid)[0]
    return {k: row.get(k) for k in ("usage_count", "reinforced_count", "reinforcement") if k in row}


def edge_w(mem, a, b):
    return mem.db.get_edge_weight(a, b)


def test(name):
    def deco(fn):
        def run():
            try:
                fn()
                RESULTS.append((name, "PASS", ""))
                print(f"PASS  {name}")
            except AssertionError as e:
                RESULTS.append((name, "FAIL", str(e)))
                print(f"FAIL  {name}\n      {e}")
            except Exception as e:
                RESULTS.append((name, "ERROR", f"{type(e).__name__}: {e}"))
                print(f"ERROR {name}\n      {type(e).__name__}: {e}")
        run.__name__ = fn.__name__
        return run
    return deco


# ═══════════════ Q1 ═══════════════

@test("Q1-T1 系統路徑 search 同一筆 100 次 → 節點權重、邊權重、排序分數皆不變")
def t1():
    mem, _ = fresh()
    seed(mem)
    first = mem.search("花椰菜", n_results=3, hebbian=True)
    ids0 = [r["memory_id"] for r in first]
    scores0 = [round(r["score"], 6) for r in first]
    before_nodes = {i: node_state(mem, i) for i in ids0}
    before_edges = {(a, b): edge_w(mem, a, b) for a in ids0 for b in ids0 if a != b}
    for _ in range(100):
        mem.search("花椰菜", n_results=3, hebbian=True)  # 舊 caller 習慣：hebbian=True 也要無效
    last = mem.search("花椰菜", n_results=3, hebbian=True)
    after_nodes = {i: node_state(mem, i) for i in ids0}
    after_edges = {(a, b): edge_w(mem, a, b) for a in ids0 for b in ids0 if a != b}
    assert before_nodes == after_nodes, f"節點權重被檢索改了：{before_nodes} → {after_nodes}"
    assert before_edges == after_edges, f"邊權重被檢索改了：{before_edges} → {after_edges}"
    assert [r["memory_id"] for r in last] == ids0, "排序變了"
    assert [round(r["score"], 6) for r in last] == scores0, f"分數變了：{scores0} → {[round(r['score'],6) for r in last]}"


@test("Q1-T2 cn cite 同一筆 5 次 → 前 3 次遞增、之後趨平且有上限")
def t2():
    mem, _ = fresh()
    seed(mem)
    seq = []
    for _ in range(5):
        r = mem.db.cite("A_broccoli_gift")
        assert r is not None and "reinforcement" in r, "cite 沒有回傳 reinforcement（baseline 無此欄）"
        seq.append(round(r["reinforcement"], 4))
    assert seq == [1.0, 1.5, 2.0, 2.25, 2.375], f"序列不對：{seq}"
    incs = [seq[0]] + [round(seq[i] - seq[i - 1], 4) for i in range(1, 5)]
    assert incs[0] > incs[1] >= incs[2] > incs[3] > incs[4], f"沒有邊際遞減：{incs}"
    for _ in range(30):
        mem.db.cite("A_broccoli_gift")
    final = node_state(mem, "A_broccoli_gift")["reinforcement"]
    assert final <= 3.0, f"超過上限：{final}"
    assert node_state(mem, "A_broccoli_gift")["usage_count"] == 0, "cite 不該再動 legacy usage_count"


@test("Q1-T3 注入後複述不算（invariant ③ Golden）：search 注入 A → consolidate(A 的複述) → A 不變；未注入的 C/D 仍會建邊")
def t3():
    mem, _ = fresh()
    seed(mem)
    injected = mem.search("花椰菜 禮物", n_results=2, hebbian=False)
    assert "A_broccoli_gift" in [r["memory_id"] for r in injected], "前置：A 應被注入"
    a0 = node_state(mem, "A_broccoli_gift")
    edges0 = sql(mem, "SELECT source_id, target_id, weight FROM edges WHERE source_id='A_broccoli_gift' ORDER BY target_id")
    res = mem.consolidate("花椰菜玩偶 糯糯抱著它睡 StackChan 小機器人 Limen 卡夫卡")
    assert "A_broccoli_gift" in res["memory_ids"], f"前置：consolidate 應匹配到 A：{res}"
    a1 = node_state(mem, "A_broccoli_gift")
    edges1 = sql(mem, "SELECT source_id, target_id, weight FROM edges WHERE source_id='A_broccoli_gift' ORDER BY target_id")
    assert a0 == a1, f"注入後複述改了 A 的節點權重：{a0} → {a1}"
    assert edges0 == edges1, f"注入後複述改了 A 的邊：{edges0} → {edges1}"
    assert "A_broccoli_gift" in res.get("skipped_injected", []), f"A 應被標 skipped_injected：{res}"
    # 對照組：C、D 沒被注入，彼此應該建邊（證明 consolidate 還活著）
    w_cd = edge_w(mem, "C_stackchan", "D_limen")
    assert w_cd is not None and w_cd > 0, f"未注入的 C-D 應建邊：{w_cd}"


@test("Q1-T3b consolidate 邊強化遞減：同一對重複 5 次 → 增量遞減、封頂")
def t3b():
    mem, _ = fresh()
    seed(mem)
    ws = []
    for _ in range(5):
        mem.consolidate("StackChan 小機器人 筆友 Limen 卡夫卡")
        ws.append(round(edge_w(mem, "C_stackchan", "D_limen"), 4))
    incs = [ws[0]] + [round(ws[i] - ws[i - 1], 4) for i in range(1, 5)]
    assert incs[0] > incs[1] >= incs[2] > incs[3] > incs[4], f"邊增量沒有遞減：ws={ws} incs={incs}"


@test("Q1-T4 MCP 層 search_memory(hebbian=True) 也不強化（工具簽名相容、行為硬關）")
def t4():
    d = tempfile.mkdtemp(prefix="anchor-tq-mcp-")
    sys.argv = ["x", "--db-path", d]
    for m in ("anchor_mcp_http",):
        sys.modules.pop(m, None)
    import anchor_mcp_http as srv
    seed(srv.memory)
    srv.search_memory("花椰菜", n_results=3, hebbian=True)
    ids = [r["memory_id"] for r in srv.memory.search("花椰菜", n_results=3)]
    before = {i: node_state(srv.memory, i) for i in ids}
    ew = {(a, b): edge_w(srv.memory, a, b) for a in ids for b in ids if a != b}
    for _ in range(50):
        srv.search_memory("花椰菜", n_results=3, hebbian=True)
    after = {i: node_state(srv.memory, i) for i in ids}
    ew2 = {(a, b): edge_w(srv.memory, a, b) for a in ids for b in ids if a != b}
    assert before == after, f"MCP search 改了節點：{before} → {after}"
    assert ew == ew2, f"MCP search 改了邊：{ew} → {ew2}"
    # 工具清單：19 個既有工具全在
    names = {t.name for t in srv.mcp._tool_manager.list_tools()}
    legacy19 = {"store_memory", "search_memory", "delete_memory", "connect_memories", "get_neighbors", "set_emotion",
                "set_tier", "annotate_memory", "get_annotations", "search_annotations", "wakeup", "leave_comment",
                "get_comments", "mark_comments_read", "pin_memory", "unpin_memory", "cite_memory", "consolidate",
                "dream_pass", "graph_stats"}
    missing = legacy19 - names
    assert not missing, f"既有工具缺了：{missing}"
    assert not any("delete" in n and "task" in n for n in names), "memory_tasks 不得有刪除工具"


@test("Q1-T5 wakeup 不強化，且回傳的 id 進注入帳")
def t5():
    mem, _ = fresh()
    seed(mem)
    mem.db.pin("A_broccoli_gift")
    before = node_state(mem, "A_broccoli_gift")
    r = mem.db.wakeup()
    assert before == node_state(mem, "A_broccoli_gift")
    mem.db.record_injection([m["memory_id"] for m in r["pinned"]], path="wakeup", caller="local")
    assert "A_broccoli_gift" in mem.db.recently_injected(["A_broccoli_gift"]), "pinned 應在注入帳"


@test("Q1-T6 migration：污染期快照（legacy_usage_count / legacy_weight / pollution_cutoff）只做一次，之後新記憶 legacy=NULL")
def t6():
    mem, d = fresh()
    seed(mem)
    from anchor_db import AnchorDB
    dbp = os.path.join(d, "memories.db")
    # 新 DB 上 migration 先於任何記憶 → 之後寫入的記憶沒有污染期，legacy 欄必須是 NULL（不是 0）
    row = sql(mem, "SELECT usage_count, legacy_usage_count FROM memories WHERE memory_id='A_broccoli_gift'")[0]
    assert row["legacy_usage_count"] is None, f"污染期後建立的記憶 legacy 應為 NULL：{row}"
    # 模擬「舊 DB 第一次跑 migration」：抹掉 schema_meta、把 usage_count 灌成污染值
    with mem.db._conn() as conn:
        conn.execute("DELETE FROM schema_meta")
        conn.execute("UPDATE memories SET usage_count = 7, legacy_usage_count = NULL WHERE memory_id='A_broccoli_gift'")
        conn.execute("UPDATE edges SET legacy_weight = NULL")
        conn.commit()
    AnchorDB(dbp)  # 第一次 → 快照
    assert mem.db.get_meta("pollution_cutoff") == "2026-09-20"
    snap1 = mem.db.get_meta("pollution_snapshot_at")
    row = sql(mem, "SELECT usage_count, legacy_usage_count FROM memories WHERE memory_id='A_broccoli_gift'")[0]
    assert row["legacy_usage_count"] == 7, f"快照沒抓到污染值：{row}"
    # 污染期後又有變動，再重開 → 快照不得被覆蓋
    with mem.db._conn() as conn:
        conn.execute("UPDATE memories SET usage_count = 99 WHERE memory_id='A_broccoli_gift'")
        conn.commit()
    AnchorDB(dbp)
    assert mem.db.get_meta("pollution_snapshot_at") == snap1, "快照被重做了"
    row = sql(mem, "SELECT usage_count, legacy_usage_count FROM memories WHERE memory_id='A_broccoli_gift'")[0]
    assert row["usage_count"] == 99 and row["legacy_usage_count"] == 7, f"legacy 快照被覆蓋：{row}"


# ═══════════════ Q2 ═══════════════

@test("Q2-T1 memory_tasks 狀態機：open→resolved 合法；無 reason 拒；終態不可再轉；沒有刪除路徑")
def q2():
    mem, _ = fresh()
    t = mem.db.task_create("msg_123", "等等要記：糯糯說想吃瑞士捲")
    assert t["status"] == "open" and t["id"].startswith("task_")
    try:
        mem.db.task_resolve(t["id"], "resolved", resolved_by="cn", reason="")
        raise AssertionError("沒 reason 竟然過了")
    except ValueError:
        pass
    try:
        mem.db.task_resolve(t["id"], "resolved", resolved_by="", reason="寫了")
        raise AssertionError("沒 resolved_by 竟然過了")
    except ValueError:
        pass
    try:
        mem.db.task_resolve(t["id"], "open", resolved_by="cn", reason="x")
        raise AssertionError("open→open 竟然過了")
    except ValueError:
        pass
    r = mem.db.task_resolve(t["id"], "resolved", resolved_by="cn", reason="已寫成記憶", result_ref="2026_09_21_swissroll")
    assert r["status"] == "resolved" and r["resolved_at"] and r["resolved_by"] == "cn" and r["result_ref"] == "2026_09_21_swissroll"
    try:
        mem.db.task_resolve(t["id"], "dismissed", resolved_by="cn", reason="再轉")
        raise AssertionError("終態竟然能再轉")
    except ValueError:
        pass
    t2 = mem.db.task_create("msg_124", "另一筆")
    r2 = mem.db.task_resolve(t2["id"], "dismissed", resolved_by="owner", reason="不需要記")
    assert r2["status"] == "dismissed"
    assert len(mem.db.task_list(status=None)) == 2, "resolved/dismissed 不得消失"
    assert not any(n.startswith("task_delete") or n == "delete_task" for n in dir(mem.db)), "不得有 task 刪除方法"


# ═══════════════ Q3 ═══════════════

@test("Q3-T1 非 owner 建卡拒；owner 建卡成；fact 更新 → 舊列 valid_until + superseded_by；affected_by 查得到")
def q3():
    mem, _ = fresh()
    seed(mem)
    for bad in (None, "", "wrong-token"):
        try:
            mem.db.card_create("花椰菜", "禮物玩偶", "第一次約會", "2026/03", owner_token=bad)
            raise AssertionError(f"非 owner（{bad!r}）竟然建卡成功")
        except PermissionError:
            pass
    c = mem.db.card_create("花椰菜", "禮物玩偶", "第一次約會老公挑的", "2026/03 第一次約會", owner_token="test-owner-token-123")
    assert c["id"].startswith("card_") and c["status"] == "candidate" and len(c["facts"]) == 3
    # 非 owner 不能改狀態；owner 可以
    try:
        mem.db.card_set_status(c["id"], "active", owner_token="nope")
        raise AssertionError("非 owner 改狀態竟然成功")
    except PermissionError:
        pass
    assert mem.db.card_set_status(c["id"], "active", owner_token="test-owner-token-123")["status"] == "active"
    # 系統路徑（無 token）更新 fact
    r1 = mem.db.card_fact_update(c["id"], "nickname", "小花", provenance="A_broccoli_gift")
    r2 = mem.db.card_fact_update(c["id"], "nickname", "花花", provenance="B_broccoli_welcome")
    assert r2["superseded"] == [r1["fact_id"]]
    old = sql(mem, "SELECT * FROM card_facts WHERE id=?", r1["fact_id"])[0]
    assert old["valid_until"] is not None and old["superseded_by"] == r2["fact_id"], f"舊列沒補：{old}"
    cur = mem.db.card_get(card_id=c["id"])
    nick = [f for f in cur["facts"] if f["field"] == "nickname"]
    assert len(nick) == 1 and nick[0]["value"] == "花花", f"current projection 錯：{nick}"
    hist = mem.db.card_get(card_id=c["id"], include_history=True)
    assert len([f for f in hist["facts"] if f["field"] == "nickname"]) == 2
    aff = mem.db.cards_affected_by("A_broccoli_gift")
    assert [f["id"] for f in aff] == [r1["fact_id"]], f"affected_by 錯：{aff}"
    # provenance 必填
    try:
        mem.db.card_fact_update(c["id"], "x", "y", provenance="")
        raise AssertionError("無 provenance 竟然過了")
    except ValueError:
        pass
    # 沒有 cap：建第 21 張不會被 schema 擋
    for i in range(21):
        mem.db.card_create(f"card{i}", "w", "y", "t", owner_token="test-owner-token-123")
    assert len(mem.db.card_list()) == 22


# ═══════════════ Q4 ═══════════════

@test("Q4-T1 digest 無 derived_from 拒；有則寫入；lineage 雙向；刪 source 後仍查得到受影響 digest")
def q4():
    mem, _ = fresh()
    seed(mem)
    try:
        mem.store("digest_20260921", "今天的日報", kind="daily_digest")
        raise AssertionError("無 provenance 的 digest 竟然存成功")
    except ValueError:
        pass
    assert mem.db.get("digest_20260921") is None, "被拒的 digest 不該落庫"
    assert mem.count() == 4, "被拒的 digest 不該進 chroma"
    try:
        mem.store("digest_bad_kind", "x", kind="whatever")
        raise AssertionError("不合法 kind 竟然過了")
    except ValueError:
        pass
    mem.store("digest_20260921", "今天：花椰菜、StackChan", kind="daily_digest",
              derived_from=["A_broccoli_gift", "C_stackchan", "gmail:msg-abc"])
    row = mem.db.get("digest_20260921")
    assert row["kind"] == "daily_digest" and json.loads(row["derived_from"]) == ["A_broccoli_gift", "C_stackchan", "gmail:msg-abc"]
    lin = mem.db.lineage_of("digest_20260921")
    assert lin["sources"] == ["A_broccoli_gift", "C_stackchan", "gmail:msg-abc"], lin
    back = mem.db.lineage_of("A_broccoli_gift")
    assert [d["memory_id"] for d in back["derivatives"]] == ["digest_20260921"], back
    assert mem.db.lineage_of("gmail:msg-abc")["derivatives"][0]["memory_id"] == "digest_20260921"
    # invariant ④：source 刪掉，還找得到受影響的 digest
    aff_before = mem.db.affected_by("A_broccoli_gift")
    assert mem.delete("A_broccoli_gift")
    aff_after = mem.db.affected_by("A_broccoli_gift")
    assert [d["memory_id"] for d in aff_after["digests"]] == ["digest_20260921"], aff_after
    assert aff_before["digests"] == aff_after["digests"]


@test("Q-extra 同 id 覆蓋（跨窗近況卡）不再清空 pinned / reinforcement / edges / comments")
def upsert():
    mem, _ = fresh()
    seed(mem)
    mem.db.pin("A_broccoli_gift")
    mem.db.cite("A_broccoli_gift")
    mem.db.connect("A_broccoli_gift", "C_stackchan", 2.0)
    mem.db.insert_comment("A_broccoli_gift", "留言")
    mem.store("A_broccoli_gift", "第一次約會的花椰菜玩偶（改寫）", tag="milestone", tier="core", emotion_score=0.9)
    row = mem.db.get("A_broccoli_gift")
    assert row["text"].endswith("（改寫）") and row["pinned"] == 1, row
    assert node_state(mem, "A_broccoli_gift")["reinforcement"] == 1.0
    assert edge_w(mem, "A_broccoli_gift", "C_stackchan") == 2.0
    assert len(mem.db.get_comments("A_broccoli_gift")) == 1


if __name__ == "__main__":
    print(f"ANCHOR_SRC={SRC}")
    for fn in (t1, t2, t3, t3b, t4, t5, t6, q2, q3, q4, upsert):
        fn()
    n_pass = sum(1 for _, s, _ in RESULTS if s == "PASS")
    n_fail = len(RESULTS) - n_pass
    print(f"\n== {n_pass} PASS / {n_fail} FAIL+ERROR / {len(RESULTS)} total ==")
    sys.exit(n_fail)
