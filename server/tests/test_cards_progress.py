"""#25: Karten counts cards (not presses) over the whole day; rating from the time to reveal."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fsrs import Card, Scheduler, State

from kaskade import db, srs

SCHED = Scheduler(desired_retention=0.9, enable_fuzzing=False)
T0 = datetime(2026, 10, 14, 7, 0, tzinfo=timezone.utc)  # Wed 09:00 Berlin


@pytest.fixture()
def isolated(client):
    db.set_setting("newPerDay", 2)
    return client


def put_card(card_id: str, state: State, due: datetime, step: int | None = None):
    c = Card(state=state, step=step, stability=5.0, difficulty=5.0, due=due, last_review=due - timedelta(days=3))
    with db.tx() as conn:
        conn.execute("INSERT INTO cards(id, status, fsrs, due, introduced_on, lapses, updated_at) VALUES (?, 'learning', ?, ?, ?, 0, ?)",
                     (card_id, json.dumps(c.to_dict()), c.due.isoformat(), "2026-10-10", T0.isoformat()))


def counts(at=T0):
    with db.tx() as conn:
        return srs.counts(conn, at)


# ── thresholds ──

@pytest.mark.parametrize("sentence, easy, hard", [
    ("Ich bin da.", 1995, 4560),                                               # 3 words: typical 2.85 s
    ("Ich habe gestern den ganzen Abend mit meiner Schwester telefoniert.", 4200, 9600),  # 10 words: 6 s
])
def test_thresholds_follow_the_sentence_length(sentence, easy, hard):
    t = srs.timing(sentence)
    assert (t["easyMs"], t["hardMs"]) == (easy, hard) and t["pace"] == 1.0 and t["capMs"] == 60_000


def test_pace_only_after_30_timed_gewusst_reviews(isolated):
    def log(n, ms, rating=3):
        with db.tx() as conn:
            for _ in range(n):
                conn.execute("INSERT INTO review_log(card_id, rating, reviewed_at, local_date, reveal_ms, auto, words)"
                             " VALUES ('core:0001', ?, ?, '2026-10-13', ?, 1, 4)", (rating, T0.isoformat(), ms))
    typical4 = 1500 + 450 * 4
    log(29, 2 * typical4)
    log(10, 300, rating=1)  # "nicht gewusst" never counts for his pace
    with db.tx() as conn:
        assert srs.pace(conn) == 1.0
    log(1, 2 * typical4)
    with db.tx() as conn:
        assert srs.pace(conn) == 2.0
    nxt = srs.next_card(T0, SCHED)
    assert nxt["timing"]["pace"] == 2.0 and nxt["timing"]["typicalMs"] == 2 * (1500 + 450 * nxt["timing"]["words"])


# ── API: reveal time and auto are stored, capped at 60 s ──

def test_reveal_ms_and_auto_are_stored_and_undo_still_works(isolated):
    card = isolated.get("/api/cards/next").json()
    assert set(card["timing"]) >= {"easyMs", "hardMs"}
    cid = card["card"]["id"]
    assert isolated.post(f"/api/cards/{cid}/review", json={"rating": 3, "revealMs": 2400, "auto": True}).status_code == 200
    second = isolated.get("/api/cards/next").json()["card"]["id"]
    isolated.post(f"/api/cards/{second}/review", json={"rating": 1, "revealMs": 95_000, "auto": False})
    with db.tx() as conn:
        rows = [tuple(r) for r in conn.execute("SELECT card_id, rating, reveal_ms, auto, words FROM review_log ORDER BY id")]
    assert rows[0][:4] == (cid, 3, 2400, 1) and rows[0][4] > 0
    assert rows[1][1:4] == (1, 60_000, 0)  # capped
    assert isolated.post("/api/cards/undo").json() == {"id": second}
    isolated.post(f"/api/cards/{cid}/review", json={"rating": 3})  # the old way still works
    with db.tx() as conn:
        assert conn.execute("SELECT reveal_ms, auto FROM review_log ORDER BY id DESC").fetchone()[:] == (None, None)


def test_autoplay_flag_is_stored_and_changes_nothing_else(isolated):
    """#28: with autoplay the time starts after the clip; the flag is logged to tune per mode later."""
    seen = []
    for autoplay in (True, False, None):
        card = isolated.get("/api/cards/next").json()
        seen.append(card["timing"])
        body = {"rating": 3, "revealMs": 2000, "auto": True} | ({} if autoplay is None else {"autoplay": autoplay})
        assert isolated.post(f"/api/cards/{card['card']['id']}/review", json=body).status_code == 200
    with db.tx() as conn:
        rows = [tuple(r) for r in conn.execute("SELECT autoplay, reveal_ms, auto FROM review_log ORDER BY id")]
        assert srs.pace(conn) == 1.0  # thresholds and pace as before
    assert rows == [(1, 2000, 1), (0, 2000, 1), (None, 2000, 1)]
    assert all(t["pace"] == 1.0 for t in seen)
    assert isolated.post(f"/api/cards/{card['card']['id']}/review", json={"rating": 3, "autoplay": "ja"}).status_code == 422


# ── counts: cards, not presses, over the whole day ──

def test_gut_on_a_new_card_keeps_it_open_until_it_graduates(isolated):
    assert (counts()["left"], counts()["doneToday"]) == (2, 0)
    a = srs.next_card(T0, SCHED)["card"]["id"]
    srs.review(a, 3, T0, SCHED)                       # Gut → a 10-min step
    assert (counts()["left"], counts()["doneToday"]) == (2, 0)
    srs.review(a, 3, T0 + timedelta(minutes=10), SCHED)   # graduates: next due in days
    c = counts(T0 + timedelta(minutes=10))
    assert (c["left"], c["doneToday"]) == (1, 1)


def test_nochmal_three_times_counts_the_card_once(isolated):
    a = srs.next_card(T0, SCHED)["card"]["id"]
    for i in range(3):
        srs.review(a, 1, T0 + timedelta(minutes=2 * i), SCHED)
        c = counts(T0 + timedelta(minutes=2 * i))
        assert (c["left"], c["doneToday"]) == (2, 0)


def test_a_review_due_at_9_20_is_counted_and_served_at_9_00(isolated):
    put_card("core:r00500", State.Review, T0 + timedelta(minutes=20))
    put_card("core:r00501", State.Review, T0 + timedelta(days=1))    # tomorrow: not today
    c = counts()
    assert c["left"] == 1 + 2 and c["due"] == 1
    assert srs.next_card(T0, SCHED)["card"]["id"] == "core:r00500"   # before the new cards
    srs.review("core:r00500", 3, T0, SCHED)
    assert counts()["doneToday"] == 1


def test_only_stepped_cards_waiting(isolated):
    db.set_setting("newPerDay", 0)
    put_card("core:r00600", State.Relearning, T0 + timedelta(minutes=50), step=0)
    nxt = srs.next_card(T0, SCHED)
    assert nxt["card"] is None and nxt["counts"]["left"] == 1 and nxt["counts"]["waiting"] == 1
    assert nxt["wait"] == {"cards": 1, "at": (T0 + timedelta(minutes=30)).isoformat()}  # 20-min learn-ahead
    assert srs.next_card(T0 + timedelta(minutes=31), SCHED)["card"]["id"] == "core:r00600"


def test_heute_karten_line_uses_the_same_left(isolated, monkeypatch):
    monkeypatch.setattr(srs, "now_utc", lambda: T0)
    put_card("core:r00500", State.Review, T0 + timedelta(minutes=20))
    t = isolated.get("/api/today").json()
    assert t["assignments"]["karten"]["part"] == "3 offen (davon 2 neu)" and t["cards"]["left"] == 3
    assert isolated.get("/api/cards/next").json()["counts"]["left"] == 3
