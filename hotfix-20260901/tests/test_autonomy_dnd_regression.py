"""迴歸:高頻自主時段不得被通用勿擾窗結構性壓死。

事故(2026-09-01 逛寶雅):`DND_MINUTES = 8` 是全域寫死的,和 slot 自己的
`interval_minutes` 無關。糯糯設 5 分鐘間隔,而她逛街時會一直傳照片,
每傳一則就把 8 分鐘勿擾窗往後推 ⇒ ticks_done 永遠是 0。
她愈想互動,系統愈判定「屋主在忙,別打擾」。

修復:`dnd_minutes = min(DND_MINUTES, slot["interval_minutes"])`。
語意:屋主親手設的喚醒間隔就是她期望的出聲頻率,勿擾窗不得寬於它。
"""
from __future__ import annotations

from datetime import datetime, timedelta


def at(hh: int, mm: int, tz) -> datetime:
    return datetime(2026, 9, 1, hh, mm, tzinfo=tz)


def test_dnd_never_wider_than_the_owner_s_own_interval(autonomy):
    """事故的數學核心:5 分鐘間隔配 8 分鐘勿擾窗 = 永遠不會響。"""
    assert autonomy.mod.DND_MINUTES == 8
    assert min(autonomy.mod.DND_MINUTES, 5) == 5, "高頻 slot 的勿擾窗必須收斂到 interval"
    assert min(autonomy.mod.DND_MINUTES, 30) == 8, "一般 slot 仍維持 8 分鐘通用勿擾窗"


def test_high_frequency_slot_fires_while_owner_is_active(autonomy):
    """屋主 6 分鐘前才講過話,5 分鐘間隔的 slot 仍要出聲(修復前會被壓下)。"""
    tz = autonomy.tz
    autonomy.put_slot(interval_minutes=5)
    autonomy.owner_says(at(17, 29, tz))
    autonomy.set_now(at(17, 35, tz))

    idle_minutes = 6
    assert idle_minutes < autonomy.mod.DND_MINUTES, "這正是修復前會被 8 分鐘窗吃掉的區間"

    autonomy.check()

    assert len(autonomy.fired) == 1
    slot = autonomy.slot()
    assert slot["ticks_done"] == 1
    assert slot.get("skips", 0) == 0


def test_high_frequency_slot_still_respects_its_own_interval(autonomy):
    """勿擾窗沒有被取消,只是收斂:屋主 2 分鐘前剛講話仍然壓下。"""
    tz = autonomy.tz
    autonomy.put_slot(interval_minutes=5)
    autonomy.owner_says(at(17, 33, tz))
    autonomy.set_now(at(17, 35, tz))

    autonomy.check()

    assert autonomy.fired == []
    slot = autonomy.slot()
    assert slot["ticks_done"] == 0
    assert slot["skips"] == 1
    assert slot["extended_minutes"] == 5, "壓下後窗口順延一個 interval"
    assert autonomy.mod.NOTE_FILE.exists(), "壓下要留貼條"


def test_normal_slot_keeps_the_eight_minute_quiet_window(autonomy):
    """一般間隔的 slot 不受本次修改影響:min(8, 30) 仍是 8。"""
    tz = autonomy.tz
    autonomy.put_slot(interval_minutes=30, ticks_total=4)
    autonomy.owner_says(at(17, 29, tz))

    autonomy.set_now(at(17, 35, tz))  # idle 6 分鐘 < 8
    autonomy.check()
    assert autonomy.fired == []
    assert autonomy.slot()["skips"] == 1

    autonomy.set_now(at(18, 5, tz))  # 距上次 tick 30 分鐘、idle 36 分鐘
    autonomy.check()
    assert len(autonomy.fired) == 1


def test_shopping_trip_replay_high_frequency_slot_is_not_starved(autonomy):
    """重演逛寶雅現場:屋主每 7 分鐘傳一則訊息,5 分鐘間隔的時段跑 40 分鐘。

    修復前:每次 tick 的 owner_idle 都 < 8 ⇒ 全數壓下 ⇒ ticks_done=0(事故現象)。
    修復後:至少要有幾次出聲,而且那幾次正是舊邏輯會殺掉的區間。
    """
    tz = autonomy.tz
    autonomy.put_slot(interval_minutes=5, ticks_total=12,
                      start_iso="2026-09-01T17:00:00+08:00",
                      end_iso="2026-09-01T17:45:00+08:00")

    owner_messages = [at(17, m, tz) for m in (0, 7, 14, 21, 28, 35)]
    sent: list[datetime] = []

    for minute in range(0, 41):
        now = at(17, 0, tz) + timedelta(minutes=minute)
        while owner_messages and owner_messages[0] <= now:
            message_at = owner_messages.pop(0)
            autonomy.owner_says(message_at)
            sent.append(message_at)
        autonomy.set_now(now)
        autonomy.check()

    assert autonomy.fired, "高頻時段整段被壓死 = 事故重現"

    would_die_pre_fix = 0
    for event in autonomy.fired:
        last_owner = max(m for m in sent if m <= event["at"])
        idle = (event["at"] - last_owner).total_seconds() / 60
        assert idle >= 5, "不得早於屋主自己設的間隔就出聲"
        if idle < autonomy.mod.DND_MINUTES:
            would_die_pre_fix += 1

    assert would_die_pre_fix >= 2, (
        "這些 tick 的 owner_idle 落在 5~8 分鐘之間,舊的全域勿擾窗會全部吃掉;"
        "它們有出聲才代表修復真的生效"
    )
