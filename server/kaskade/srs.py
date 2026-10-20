"""Core-deck spaced repetition with FSRS. All scheduling lives here; state in SQLite."""
import json
import os
import statistics
import time
from datetime import datetime, time as dtime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from fsrs import Card, Rating, Scheduler, State

from . import config, db, origin, texts

TZ = ZoneInfo("Europe/Berlin")
NEW_PER_DAY = 20
LEECH_AGAIN = 4          # "Nochmal" this often → card is suspended
LEARN_AHEAD = timedelta(minutes=20)
# #25: how fast he reveals a sentence he knows → Leicht / Gut / Schwer
BASE_MS, PER_WORD_MS = 1500, 450      # typical = (1.5 s + 0.45 s × words) × pace
EASY, HARD = 0.7, 1.6                 # Leicht if t ≤ 0.7 × typical, Gut if ≤ 1.6 × typical, else Schwer
PACE_MIN_REVIEWS, PACE_WINDOW = 30, 200
REVEAL_CAP_MS = 60_000
STEPPED = (int(State.Learning), int(State.Relearning))

scheduler = Scheduler(desired_retention=0.9)


@lru_cache(maxsize=1)
def deck() -> list[dict]:
    cards = []
    for f in sorted((config.CONTENT_DIR / "core-deck").glob("[0-9][0-9][0-9][0-9].json")):
        cards.extend(json.loads(f.read_text(encoding="utf-8")))
    return cards


@lru_cache(maxsize=1)
def deck_index() -> dict[str, dict]:
    return {c["id"]: c for c in deck()}


def mined_cards() -> list[dict]:
    """Sentences mined in the reader — cards like the core deck, id 'mine:N'."""
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT mined.*, media.title AS media_title FROM mined"
            " LEFT JOIN media ON media.id = mined.media_id ORDER BY mined.id").fetchall()
    library = {t["title"]: t for t in texts.library()}
    out = []
    for r in rows:
        o = origin.of_mined(r["source"], r["media_title"], library)
        out.append({
            "id": f"mine:{r['id']}", "n": None, "lemma": r["lemma"], "display": r["display"], "gloss": r["gloss"],
            "sentence": r["sentence"], "target": r["target"], "en": r["en"] or "", "note": r["note"],
            "case": r["kasus"], "source": r["source"], "pos": None,
            "audio": r["audio"], "mediaId": r["media_id"], "clipStart": r["clip_start"], "clipEnd": r["clip_end"],
            # #19: fields a KI filled in ("lemma", "gloss", "case") and more target words of the same line
            "aiFields": json.loads(r["ai_fields"] or "[]"), "words": json.loads(r["words"] or "[]"),
            # "source" above is where it was mined (shown as "Gemined · …"); origin says whose German it is
            "origin": o["origin"], "originSource": o["source"],
            # #29: the sentence is from the Whisper track — a word may be misheard
            "transcript": r["track"] == "spoken",
        })
    return out


def card_content(card_id: str) -> dict | None:
    if card_id.startswith("mine:"):
        return next((c for c in mined_cards() if c["id"] == card_id), None)
    card = deck_index().get(card_id)
    if card is None:
        return None
    o = origin.tag(card)  # same fields as mined cards: origin + originSource
    return {**card, "origin": o["origin"], "originSource": o["source"]}


_BOOT = time.monotonic()


def now_utc() -> datetime:
    # KASKADE_NOW pins the clock for the E2E test instance (never set in production).
    # With KASKADE_CLOCK_SPEED the pinned time runs on from there (e.g. 30 = a minute every 2 s),
    # for walk-throughs where block timers should log minutes.
    fixed = os.environ.get("KASKADE_NOW")
    if not fixed:
        return datetime.now(timezone.utc)
    start = datetime.fromisoformat(fixed)
    speed = float(os.environ.get("KASKADE_CLOCK_SPEED", "0") or 0)
    return start + timedelta(seconds=(time.monotonic() - _BOOT) * speed) if speed > 0 else start


def local_date(at: datetime) -> str:
    return at.astimezone(TZ).date().isoformat()


def human_interval(delta: timedelta) -> str:
    s = max(0, delta.total_seconds())
    if s < 3600:
        return f"{max(1, round(s / 60))} Min"
    if s < 86400:
        return f"{round(s / 3600)} Std"
    days = round(s / 86400)
    if days < 60:
        return "1 Tag" if days == 1 else f"{days} Tage"
    months = round(days / 30)
    return f"{months} Mon."


def new_per_day() -> int:
    return int(db.get_setting("newPerDay", NEW_PER_DAY))


def _row(conn, card_id):
    return conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()


def _fsrs(row) -> Card:
    return Card.from_dict(json.loads(row["fsrs"])) if row and row["fsrs"] else Card()


def previews(card: Card, at: datetime, sched: Scheduler = scheduler) -> dict[int, str]:
    out = {}
    for r in Rating:
        nxt, _ = sched.review_card(Card.from_dict(card.to_dict()), r, at)
        out[int(r)] = human_interval(nxt.due - at)
    return out


def end_of_day(at: datetime) -> datetime:
    """Berlin midnight after `at` (the day boundary for reviews, like Anki's)."""
    d = at.astimezone(TZ).date() + timedelta(days=1)
    return datetime.combine(d, dtime(0), TZ).astimezone(timezone.utc)


def _state(row) -> int | None:
    return json.loads(row["fsrs"]).get("state") if row["fsrs"] else None


BACKLOG = 20  # #36: after a week off, no new cards while this many are due


def _setting(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def backlog_pause(pauses: list[dict], caught_up: list[str], day: str, due: int) -> dict | None:
    """#36: the week off whose backlog holds new cards back on `day` (ISO), else None. From its first
    day until, after it, fewer than BACKLOG cards are due once (`caught_up` lists those pauses)."""
    started = [p for p in pauses or () if p["from"] <= day]
    p = max(started, key=lambda x: x["from"], default=None)
    if not p or p["from"] in caught_up or due < BACKLOG:
        return None
    return p


def _new_held(conn, today: str, due: int) -> bool:
    pauses, caught = _setting(conn, "pauses", []), _setting(conn, "cardsCaughtUp", [])
    if backlog_pause(pauses, caught, today, due):
        return True
    p = max((x for x in pauses if x["to"] < today), key=lambda x: x["from"], default=None)
    if p and p["from"] not in caught and due < BACKLOG:  # caught up after the week off: new cards again
        conn.execute("INSERT INTO settings(key, value) VALUES ('cardsCaughtUp', ?) ON CONFLICT(key) DO UPDATE"
                     " SET value = excluded.value", (json.dumps(sorted({*caught, p["from"]})),))
    return False


def counts(conn, at: datetime) -> dict:
    """Distinct cards for today (#25). left = reviews due by Berlin midnight + every card in a
    short-term step (they come back today) + new cards left; doneToday = cards reviewed today
    that won't come back today, plus today's "Kenne ich schon"."""
    today, eod = local_date(at), end_of_day(at)
    rows = conn.execute("SELECT id, fsrs, due FROM cards WHERE status = 'learning'").fetchall()
    stepped = [r for r in rows if _state(r) in STEPPED]
    reviews = [r for r in rows if _state(r) not in STEPPED and r["due"] and r["due"] < eod.isoformat()]
    waiting = [r for r in stepped if r["due"] > at.isoformat()]
    introduced = conn.execute("SELECT COUNT(*) FROM cards WHERE introduced_on = ?", (today,)).fetchone()[0]
    seen = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    total = len(deck()) + conn.execute("SELECT COUNT(*) FROM mined").fetchone()[0]
    new_left = min(max(0, new_per_day() - introduced), max(0, total - seen))
    held = _new_held(conn, today, len(stepped) + len(reviews))
    if held:
        new_left = 0  # #36: the backlog after a week off first
    coming_back = {r["id"] for r in stepped} | {r["id"] for r in reviews}
    reviewed = {r[0] for r in conn.execute("SELECT DISTINCT card_id FROM review_log WHERE local_date = ?", (today,))}
    done = len(reviewed - coming_back)
    left = len(stepped) + len(reviews) + new_left
    return {"left": left, "doneToday": done, "new": new_left, "due": len(stepped) + len(reviews), "newHeld": held,
            "waiting": len(waiting), "nextAt": min((r["due"] for r in waiting), default=None)}


def pace(conn) -> float:
    """His reveal speed against the typical one: 1.0 until 30 timed "gewusst" reviews, then the
    median over the last 200 — so Leicht/Gut/Schwer follow his own speed."""
    rows = conn.execute(
        "SELECT reveal_ms, words FROM review_log WHERE reveal_ms IS NOT NULL AND words IS NOT NULL AND rating >= 2"
        " ORDER BY id DESC LIMIT ?", (PACE_WINDOW,)).fetchall()
    if len(rows) < PACE_MIN_REVIEWS:
        return 1.0
    return statistics.median(min(r["reveal_ms"], REVEAL_CAP_MS) / (BASE_MS + PER_WORD_MS * r["words"]) for r in rows)


def words_in(sentence: str) -> int:
    return len((sentence or "").split())


def timing(sentence: str, p: float = 1.0) -> dict:
    """Reveal-time thresholds for a sentence: Leicht ≤ easyMs < Gut ≤ hardMs < Schwer."""
    typical = (BASE_MS + PER_WORD_MS * words_in(sentence)) * p
    return {"easyMs": round(EASY * typical), "hardMs": round(HARD * typical), "typicalMs": round(typical),
            "words": words_in(sentence), "pace": round(p, 3), "capMs": REVEAL_CAP_MS}


def next_card(at: datetime | None = None, sched: Scheduler = scheduler) -> dict:
    """Next card (#25): cards in a step that are due, then every review due by Berlin midnight
    (served right away, like Anki), then new cards, then steps due within the learn-ahead.
    Nothing comes up that `counts` didn't count."""
    at = at or now_utc()
    eod = end_of_day(at).isoformat()
    with db.tx() as conn:
        c = counts(conn, at)
        p = pace(conn)
        learning = conn.execute("SELECT id, fsrs, due FROM cards WHERE status = 'learning' ORDER BY due").fetchall()
        step_due = next((r["id"] for r in learning if _state(r) in STEPPED and r["due"] <= at.isoformat()), None)
        review_due = next((r["id"] for r in learning if _state(r) not in STEPPED and r["due"] and r["due"] < eod), None)
        card_id = step_due or review_due
        if card_id is None and c["new"] > 0:
            seen = {r[0] for r in conn.execute("SELECT id FROM cards")}
            # mined sentences first (you chose them from real input), then the core deck in order
            pool = [*(f"mine:{r[0]}" for r in conn.execute("SELECT id FROM mined ORDER BY id")), *(d["id"] for d in deck())]
            card_id = next((cid for cid in pool if cid not in seen), None)
        if card_id is None:
            ahead = (at + LEARN_AHEAD).isoformat()
            card_id = next((r["id"] for r in learning if _state(r) in STEPPED and r["due"] <= ahead), None)
        if card_id is None:
            out = {"card": None, "counts": c}
            if c["nextAt"]:  # only cards waiting in a step: they come back by themselves
                out["wait"] = {"cards": c["waiting"], "at": (datetime.fromisoformat(c["nextAt"]) - LEARN_AHEAD).isoformat()}
            return out
        row = _row(conn, card_id)
    content = card_content(card_id)
    return {
        "card": {**content, "isNew": row is None},
        "intervals": previews(_fsrs(row), at, sched),
        "timing": timing(content["sentence"], p),
        "counts": c,
    }


def _snapshot(row) -> str | None:
    return json.dumps(dict(row)) if row else None


def review(card_id: str, rating: int, at: datetime | None = None, sched: Scheduler = scheduler,
           reveal_ms: int | None = None, auto: bool | None = None, autoplay: bool | None = None) -> dict:
    """Rate a card. #25: `reveal_ms` (time to reveal, capped at 60 s) and `auto` (rating derived
    from that time, not chosen) are logged — they tune his pace and the thresholds later.
    #28: `autoplay` — the card's audio played by itself first (the time starts after it)."""
    content = card_content(card_id)
    if content is None:
        raise KeyError(card_id)
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating must be 1–4")
    at = at or now_utc()
    with db.tx() as conn:
        row = _row(conn, card_id)
        if row and row["status"] in ("known", "suspended"):
            raise ValueError("card is not active")
        card, _ = sched.review_card(_fsrs(row), Rating(rating), at)
        lapses = (row["lapses"] if row else 0) + (rating == 1)
        status = "suspended" if lapses >= LEECH_AGAIN else "learning"
        introduced = row["introduced_on"] if row else local_date(at)
        conn.execute(
            "INSERT INTO cards(id, status, fsrs, due, introduced_on, lapses, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET status = excluded.status, fsrs = excluded.fsrs, due = excluded.due,"
            " lapses = excluded.lapses, updated_at = excluded.updated_at",
            (card_id, status, json.dumps(card.to_dict()), card.due.isoformat(), introduced, lapses, at.isoformat()),
        )
        conn.execute(
            "INSERT INTO review_log(card_id, rating, reviewed_at, local_date, prev, reveal_ms, auto, words, autoplay)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (card_id, rating, at.isoformat(), local_date(at), _snapshot(row),
             min(reveal_ms, REVEAL_CAP_MS) if reveal_ms is not None else None,
             None if auto is None else int(auto), words_in(content["sentence"]) if reveal_ms is not None else None,
             None if autoplay is None else int(autoplay)),
        )
    return {"id": card_id, "status": status, "due": card.due.isoformat(), "interval": human_interval(card.due - at)}


def mark_known(card_id: str, at: datetime | None = None) -> dict:
    """'Kenne ich schon': bury permanently. Does not use up the daily new-card quota."""
    if card_content(card_id) is None:
        raise KeyError(card_id)
    at = at or now_utc()
    with db.tx() as conn:
        row = _row(conn, card_id)
        conn.execute(
            "INSERT INTO cards(id, status, fsrs, due, introduced_on, lapses, updated_at) VALUES (?, 'known', NULL, NULL, NULL, 0, ?)"
            " ON CONFLICT(id) DO UPDATE SET status = 'known', updated_at = excluded.updated_at",
            (card_id, at.isoformat()),
        )
        conn.execute(
            "INSERT INTO review_log(card_id, rating, reviewed_at, local_date, prev) VALUES (?, 0, ?, ?, ?)",
            (card_id, at.isoformat(), local_date(at), _snapshot(row)),
        )
    return {"id": card_id, "status": "known"}


def undo() -> dict | None:
    """Revert the most recent review or 'kenne ich'."""
    with db.tx() as conn:
        log = conn.execute("SELECT * FROM review_log ORDER BY id DESC LIMIT 1").fetchone()
        if not log:
            return None
        if log["prev"]:
            p = json.loads(log["prev"])
            conn.execute(
                "UPDATE cards SET status = ?, fsrs = ?, due = ?, introduced_on = ?, lapses = ?, updated_at = ? WHERE id = ?",
                (p["status"], p["fsrs"], p["due"], p["introduced_on"], p["lapses"], p["updated_at"], log["card_id"]),
            )
        else:
            conn.execute("DELETE FROM cards WHERE id = ?", (log["card_id"],))
        conn.execute("DELETE FROM review_log WHERE id = ?", (log["id"],))
    return {"id": log["card_id"]}


def stats(at: datetime | None = None) -> dict:
    at = at or now_utc()
    with db.tx() as conn:
        by_status = dict(conn.execute("SELECT status, COUNT(*) FROM cards GROUP BY status").fetchall())
        mature = 0
        for (f,) in conn.execute("SELECT fsrs FROM cards WHERE status = 'learning' AND fsrs IS NOT NULL"):
            st = json.loads(f).get("stability") or 0
            mature += st >= 21
        since = (at - timedelta(days=30)).isoformat()
        rows = conn.execute(
            "SELECT rating FROM review_log l WHERE rating > 0 AND reviewed_at >= ? AND prev IS NOT NULL", (since,)
        ).fetchall()
        c = counts(conn, at)
    recall = sum(r[0] > 1 for r in rows) / len(rows) if rows else None
    return {
        "deckSize": len(deck()),
        "known": by_status.get("known", 0),
        "learning": by_status.get("learning", 0),
        "suspended": by_status.get("suspended", 0),
        "mature": mature,
        "unseen": len(deck()) + len(mined_cards()) - sum(by_status.values()),
        "mined": len(mined_cards()),
        "retention30": round(recall, 3) if recall is not None else None,
        **c,
    }
