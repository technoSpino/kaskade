from datetime import datetime, timedelta, timezone

import pytest
from fsrs import Card, Scheduler

from kaskade import db, srs

SCHED = Scheduler(desired_retention=0.9, enable_fuzzing=False)
T0 = datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)  # Monday 09:00 in Berlin


@pytest.fixture()
def isolated(client):
    """Use the client fixture only for its temp database."""
    return client


def interval_days(text: str) -> float:
    n, unit = text.split(" ")
    return float(n) * {"Min": 1 / 1440, "Std": 1 / 24, "Tag": 1, "Tage": 1, "Mon.": 30}[unit]


@pytest.mark.parametrize("delta, text", [
    (timedelta(seconds=20), "1 Min"), (timedelta(minutes=10), "10 Min"), (timedelta(hours=5), "5 Std"),
    (timedelta(days=1), "1 Tag"), (timedelta(days=9), "9 Tage"), (timedelta(days=120), "4 Mon."),
])
def test_human_interval(delta, text):
    assert srs.human_interval(delta) == text


def test_preview_intervals_are_monotonic_for_new_and_reviewed_cards():
    card = Card()
    for _ in range(4):
        p = srs.previews(card, T0, SCHED)
        days = [interval_days(p[r]) for r in (1, 2, 3, 4)]
        assert days == sorted(days), p
        card, _ = SCHED.review_card(card, 3, T0)


def test_good_reviews_grow_the_interval():
    card, at, gaps = Card(), T0, []
    for _ in range(5):
        card, _ = SCHED.review_card(card, 3, at)
        gaps.append(card.due - at)
        at = card.due
    assert gaps[-1] > gaps[-2] > gaps[-3]


def test_local_date_uses_berlin_time():
    late = datetime(2026, 10, 12, 22, 30, tzinfo=timezone.utc)  # 00:30 next day in Berlin
    assert srs.local_date(late) == "2026-10-13"


def test_new_cards_come_in_deck_order_and_respect_daily_quota(isolated):
    db.set_setting("newPerDay", 3)
    ids = []
    for _ in range(3):
        nxt = srs.next_card(T0, SCHED)
        assert nxt["card"]["isNew"]
        ids.append(nxt["card"]["id"])
        srs.review(nxt["card"]["id"], 4, T0, SCHED)  # easy → not due again today
    assert ids == [c["id"] for c in srs.deck()[:3]]
    assert srs.next_card(T0, SCHED)["card"] is None
    # next day: new quota again
    assert srs.next_card(T0 + timedelta(days=1), SCHED)["card"]["id"] == srs.deck()[3]["id"]


def test_kenne_ich_buries_card_and_keeps_quota(isolated):
    db.set_setting("newPerDay", 2)
    first = srs.next_card(T0, SCHED)["card"]["id"]
    srs.mark_known(first, T0)
    nxt = srs.next_card(T0, SCHED)
    assert nxt["card"]["id"] == srs.deck()[1]["id"]
    assert nxt["counts"]["new"] == 2  # triage did not use up the quota
    # a known card never comes back, not even much later
    for days in (1, 30, 400):
        assert srs.next_card(T0 + timedelta(days=days), SCHED)["card"]["id"] != first
    with pytest.raises(ValueError):
        srs.review(first, 3, T0, SCHED)


def test_again_brings_card_back_soon_and_due_reviews_come_first(isolated):
    a = srs.next_card(T0, SCHED)["card"]["id"]
    srs.review(a, 1, T0, SCHED)
    # straight after: new card b (a is in learning, due in a minute)
    b = srs.next_card(T0, SCHED)["card"]["id"]
    assert b != a
    # two minutes later a is due and comes before new cards
    assert srs.next_card(T0 + timedelta(minutes=2), SCHED)["card"]["id"] == a


def test_learn_ahead_when_nothing_else_left(isolated):
    db.set_setting("newPerDay", 1)
    a = srs.next_card(T0, SCHED)["card"]["id"]
    srs.review(a, 3, T0, SCHED)  # due in 10 min
    assert srs.next_card(T0, SCHED)["card"]["id"] == a


def test_leech_is_suspended_after_four_agains(isolated):
    a = srs.next_card(T0, SCHED)["card"]["id"]
    at = T0
    for i in range(4):
        r = srs.review(a, 1, at, SCHED)
        at += timedelta(minutes=15)
    assert r["status"] == "suspended"
    assert srs.stats(at)["suspended"] == 1


def test_undo_restores_previous_state(isolated):
    a = srs.next_card(T0, SCHED)["card"]["id"]
    srs.review(a, 3, T0, SCHED)
    srs.review(a, 3, T0 + timedelta(minutes=11), SCHED)
    assert srs.undo() == {"id": a}
    with db.tx() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (a,)).fetchone()
    assert row["status"] == "learning"
    srs.undo()  # undo first review → card is new again
    assert srs.next_card(T0, SCHED)["card"]["id"] == a
    assert srs.undo() is None


def test_unknown_card_and_bad_rating(isolated):
    with pytest.raises(KeyError):
        srs.review("core:9999", 3, T0)
    with pytest.raises(ValueError):
        srs.review(srs.deck()[0]["id"], 5, T0)


def test_stats(isolated):
    c = srs.deck()
    srs.mark_known(c[0]["id"], T0)
    srs.review(c[1]["id"], 3, T0, SCHED)
    s = srs.stats(T0)
    assert s["known"] == 1 and s["learning"] == 1 and s["unseen"] == len(c) - 2
    assert s["doneToday"] == 1


def test_pinned_clock_can_run_faster(monkeypatch):
    import time as _time
    from kaskade import srs
    monkeypatch.setenv("KASKADE_NOW", "2026-10-12T07:00:00+00:00")
    assert srs.now_utc().isoformat() == "2026-10-12T07:00:00+00:00"
    monkeypatch.setenv("KASKADE_CLOCK_SPEED", "60")
    monkeypatch.setattr(srs, "_BOOT", _time.monotonic() - 10)  # 10 s since start → 10 min later
    assert 599 <= (srs.now_utc() - srs.datetime.fromisoformat("2026-10-12T07:00:00+00:00")).total_seconds() <= 610
