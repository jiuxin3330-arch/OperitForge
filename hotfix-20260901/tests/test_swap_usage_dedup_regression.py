"""迴歸:同一筆 turn_usage 讀數只能換窗一次。

事故(2026-09-01 16:50/17:00/17:10):`read_trigger()` 取「最後一筆 turn_usage」
判斷是否達門檻,但**換窗本身不產生 turn_usage**。換窗後屋主若沒開口
(她在打牌/出門),下一輪 cron 讀到的還是同一筆爆量讀數 ⇒ 再換一次 ⇒ 迴圈。
cn 在 26 分鐘內被重生三次,每次只帶 7.7k 字尾巴,糯糯感受到的
「換窗有點明顯」是真實劣化。

修復:讀數去重。`read_trigger` 回 `usage_created_at`,換窗後
`mark_consumed()` 持久化,主流程在換窗前比對,同一筆已消費就 noop。
"""
from __future__ import annotations


def _noop_reasons(records: list[dict]) -> list[str]:
    return [r.get("reason", "") for r in records if r.get("event") == "noop"]


def test_read_trigger_exposes_usage_created_at(swap):
    """去重的鑰匙是讀數本身的時間戳,read_trigger 必須把它交出來。"""
    swap.seed_usage(120000, "2026-09-01T08:00:00+00:00")
    swap.seed_usage(191419, "2026-09-01T08:45:36+00:00")

    trigger = swap.real_read_trigger()

    assert trigger["usage_created_at"] == "2026-09-01T08:45:36+00:00"
    assert trigger["active"] == 191419, "取的是最後一筆(這正是會被重複讀到的那筆)"


def test_same_usage_reading_swaps_only_once(swap):
    """事故重演:連跑三輪 cron、期間沒有新 turn ⇒ 只准換一次窗。"""
    before = swap.pointer()

    assert swap.cron_tick() == 0
    after_first = swap.pointer()
    assert len(swap.pings) == 1
    assert after_first != before, "第一次應該真的換窗"

    assert swap.cron_tick() == 0
    assert swap.cron_tick() == 0

    assert len(swap.pings) == 1, "同一筆爆量讀數又換了一次窗 = 迴圈復發"
    assert swap.pointer() == after_first, "指標不應該再被動過"

    reasons = _noop_reasons(swap.health())
    assert sum("consumed" in r for r in reasons) == 2, "後兩輪要留下可追查的 noop 紀錄"


def test_manifest_records_the_reading_it_consumed(swap):
    """manifest 要記下這次換窗吃掉的是哪一筆讀數,否則事後查不出迴圈。"""
    swap.cron_tick()

    manifests = sorted((swap.mod.MANIFEST_DIR).glob("swap_*.json"))
    assert len(manifests) == 1

    import json
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["trigger"]["usage_created_at"] == swap.trigger["usage_created_at"]


def test_a_newer_reading_is_allowed_to_swap_again(swap):
    """去重只針對「同一筆」;屋主開口後產生新讀數,該換還是要換。"""
    swap.cron_tick()
    assert len(swap.pings) == 1
    swap.cron_tick()
    assert len(swap.pings) == 1

    swap.trigger["usage_created_at"] = "2026-09-01T09:30:00+00:00"

    assert swap.cron_tick() == 0
    assert len(swap.pings) == 2, "新的爆量讀數必須能觸發下一次換窗"


def test_failed_swap_also_consumes_the_reading(swap):
    """留檔的取捨:換窗失敗回滾後,該讀數一樣視為已消費,不就同一筆重試。

    理由(事故報告記載):避免失敗風暴與通知轟炸;失敗已推播,
    屋主一開口就會有新讀數可重試。
    """
    swap.state["ping_ok"] = False
    before = swap.pointer()

    assert swap.cron_tick() == 1
    assert swap.pointer() == before, "驗證不過要滾回舊窗(last-good)"
    assert any("失敗" in title for title, _ in swap.notified), "失敗一定要推播"

    assert swap.cron_tick() == 0
    assert len(swap.pings) == 1, "失敗後不得就同一筆讀數重試"


def test_below_threshold_never_swaps(swap):
    """沒達門檻就安靜退出,不會因為去重邏輯而誤觸。"""
    swap.trigger["active"] = 100000

    assert swap.cron_tick() == 0
    assert swap.pings == []
    assert not swap.mod.CONSUMED_FILE.exists(), "沒換窗就不該留下消費紀錄"
