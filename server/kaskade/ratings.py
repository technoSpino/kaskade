"""How much Matt understood (#23), the lines he marked "zu schwer", and what the plan does with it (#24).

After every Schauen and Frei-lesen/hören block (and the Lesetest) one question: "Wie viel hast
du verstanden?" — 20 · 40 · 60 · 80 · 100 %, or skipped. A rating belongs to a date, a block and
the exact item it was about (clip + range, text, article set, book + pages).

Books: the latest rating sets how the book's next days are read — 80–100 % frei, 60 % up to
three words per page looked up, 20–40 % the book waits for the next pass through the plan (it's
re-tested there) and its days get nachrichtenleicht instead. A book with a Lesetest that wasn't
rated by its first day 09:00 is read as at 60 %. Each pass through the 4 weeks starts fresh.
"""
import json
from datetime import date, datetime, time, timedelta, timezone

from . import db, plan, srs, stock

PCTS = (20, 40, 60, 80, 100)
TOO_HARD = 70               # under this, Heute says "Zu schwer"
LEICHT_COUNT = 5            # nachrichtenleicht articles per block before any rating (#22)
CUTOFF = time(9, 0)         # a rating counts for a day if given before that day's block


# ── Which item a block was about ─────────────────────────────────────────────

def rate_info(it: dict, day: date) -> dict | None:
    """Key, kind and label of a Heute item for its rating; None for blocks that aren't rated."""
    kind = it["kind"]
    label = " · ".join(x for x in (it.get("title"), it.get("part")) if x)
    if kind in ("clip", "satzcheck") and it.get("clip"):
        a, b = it.get("range") or [0, 0]
        return {"item": f"clip:{it['clip']}:{int(a)}-{int(b or 0)}", "kind": "audio" if it.get("audio") else "clip",
                "label": label, "book": None, "detail": {"mediaId": it.get("mediaId"), "from": a, "to": b}}
    if kind in ("youtube", "netflix"):
        return {"item": f"{kind}:{it['clip']}", "kind": kind, "label": label, "book": None, "detail": None}
    if kind == "text":
        return {"item": f"text:{it['textId']}", "kind": "text", "label": it["title"], "book": None, "detail": None}
    if kind == "news":
        links = it.get("links") or []
        n = len(links) or it.get("count")
        return {"item": f"news:{it['feed']}:{day.isoformat()}", "kind": "news", "label": f"{it['source']}: {n} Artikel",
                "book": None, "detail": {"links": [x["url"] for x in links]}}
    if kind == "book":
        return {"item": f"book:{it['bookId']}:{it['part']}", "kind": "book", "label": label, "book": it["bookId"],
                "detail": {"part": it["part"]}}
    if kind == "lesetest":
        return {"item": f"lesetest:{it['bookId']}", "kind": "lesetest", "label": label, "book": it["bookId"],
                "detail": {"part": it["part"]}}
    return None


# ── Stored ratings ───────────────────────────────────────────────────────────

def _row(r) -> dict:
    return {"id": r["id"], "date": r["local_date"], "block": r["block"], "item": r["item"], "kind": r["kind"],
            "label": r["label"], "book": r["book"], "pct": r["pct"], "skipped": r["pct"] is None,
            "hard": r["hard"], "lines": r["lines"], "createdAt": r["created_at"],
            "detail": json.loads(r["detail"]) if r["detail"] else None}


def save(day: date, block: str, info: dict, pct: int | None, hard: int | None = None, lines: int | None = None) -> dict:
    """Store (or replace) the rating of one block's item on `day`; pct None = skipped."""
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO ratings(created_at, local_date, block, item, kind, label, book, pct, hard, lines, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(local_date, block, item) DO UPDATE SET"
            " created_at = excluded.created_at, pct = excluded.pct, hard = excluded.hard, lines = excluded.lines,"
            " label = excluded.label, detail = excluded.detail",
            (srs.now_utc().isoformat(), day.isoformat(), block, info["item"], info["kind"], info["label"], info["book"],
             pct, hard, lines, json.dumps(info["detail"], ensure_ascii=False) if info.get("detail") else None))
        r = conn.execute("SELECT * FROM ratings WHERE local_date = ? AND block = ? AND item = ?",
                         (day.isoformat(), block, info["item"])).fetchone()
    return _row(r)


def on_day(day: date) -> dict[tuple[str, str], dict]:
    """(block, item) → rating for one date."""
    with db.tx() as conn:
        rows = conn.execute("SELECT * FROM ratings WHERE local_date = ?", (day.isoformat(),)).fetchall()
    return {(r["block"], r["item"]): _row(r) for r in rows}


def recent(since: date) -> list[dict]:
    with db.tx() as conn:
        rows = conn.execute("SELECT * FROM ratings WHERE local_date >= ? ORDER BY local_date DESC, id DESC",
                            (since.isoformat(),)).fetchall()
    return [_row(r) for r in rows]


def leicht_count(minutes: int = 35) -> int:
    """nachrichtenleicht articles for `minutes`: 5 per 35 min to start with; more when he understood
    a lot last time, fewer when not."""
    base = max(2, round(minutes * LEICHT_COUNT / 35))
    with db.tx() as conn:
        r = conn.execute("SELECT pct FROM ratings WHERE item LIKE 'news:leicht:%' AND pct IS NOT NULL"
                         " ORDER BY local_date DESC, id DESC LIMIT 1").fetchone()
    if not r:
        return base
    return max(2, base + {100: 2, 80: 1, 60: 0}.get(r["pct"], -1))


# ── Lines marked "zu schwer" in Schauen ──────────────────────────────────────

def mark_hard(day: date, media_id: int, start: float, end: float | None, text: str, track: str | None = None) -> None:
    """`track`: "spoken" when the line was on the Whisper track (#29), else ARD's subtitles."""
    with db.tx() as conn:
        conn.execute("INSERT INTO hard_lines(created_at, local_date, media_id, start, end, text, track) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (srs.now_utc().isoformat(), day.isoformat(), media_id, start, end, text, track))


def hard_marks(day: date, media_id: int) -> list[dict]:
    with db.tx() as conn:
        rows = conn.execute("SELECT start, end, text, track FROM hard_lines WHERE local_date = ? AND media_id = ? ORDER BY id",
                            (day.isoformat(), media_id)).fetchall()
    return [dict(r) for r in rows]


def hard_share(cues: list[dict], frm: float, to: float, marks: list[float]) -> dict:
    """Lines marked too hard of the lines heard from `frm` to `to` (as lib/ratings.js hardShare)."""
    heard = sum(1 for c in cues if frm - 0.5 <= c["start"] < to)
    marked = len({round(m, 1) for m in marks})
    lines = max(heard, marked)
    return {"marked": marked, "lines": lines, "pct": round(100 * marked / lines) if lines else 0}


# ── Books: the latest rating sets the mode (#24) ─────────────────────────────

def short_author(book: dict) -> str:
    return (book.get("author") or book["title"]).split()[-1]


def _days(start: date, data: dict, pred, n: int = 0, pauses=()) -> list[date]:
    """The dates of pass `n` through the plan's weeks with a material matching `pred` (weeks off skipped, #36)."""
    first = n * len(data["weeks"])
    return [plan.slot_date(start, first + wi, di, pauses) for wi, w in enumerate(data["weeks"])
            for di, d in enumerate(w["days"]) if any(pred(m) for m in d.get("materials", []))]


def _pass(start: date, data: dict, day: date, pauses=()) -> int:
    """Which pass through the plan's weeks `day` lies in (a week off belongs to the plan week after it)."""
    return max(0, plan.plan_index(start, day, pauses)[0] // len(data["weeks"]))


def book_mode(book_id: str, day: date, start: date, data: dict, pauses=None) -> dict:
    """How `book_id` is read on `day`: {mode: frei | nachschlagen | spaeter, pct, why, …}.
    `pauses`: the weeks off (#36), by default the stored ones."""
    b = stock.book(book_id) or {"id": book_id, "title": book_id, "author": ""}
    name = short_author(b)
    pauses = plan.pauses() if pauses is None else pauses
    n = _pass(start, data, day, pauses)
    weeks = len(data["weeks"])
    lo, hi = plan.slot_date(start, n * weeks, 0, pauses), plan.slot_date(start, (n + 1) * weeks, 0, pauses)
    is_test = lambda m: m["kind"] == "lesetest" and m.get("book") == book_id  # noqa: E731
    is_book = lambda m: m["kind"] == "book" and m.get("book") == book_id  # noqa: E731
    tested = _days(start, data, is_test, n, pauses)
    reading = _days(start, data, is_book, n, pauses)
    cutoff = cutoff_of(day)
    real_today = srs.now_utc().astimezone(srs.TZ).date()
    with db.tx() as conn:
        r = conn.execute(
            "SELECT local_date, kind, pct FROM ratings WHERE book = ? AND pct IS NOT NULL AND local_date >= ?"
            " AND local_date <= ? AND created_at < ? ORDER BY created_at DESC LIMIT 1",
            (book_id, lo.isoformat(), day.isoformat(), cutoff)).fetchone()
    out = {"book": book_id, "name": name, "pct": None, "assumed": False, "date": None, "source": None, "show": True}
    test = next(iter(tested), None)
    if r:
        pct = r["pct"]
        out.update(pct=pct, date=r["local_date"], source=r["kind"])
        when = "im Lesetest" if r["kind"] == "lesetest" else f"am {_dm(date.fromisoformat(r['local_date']))}"
        reason = f"{name}: {pct} % {when}"
    elif test and reading and day >= reading[0] and srs.now_utc().isoformat() >= cutoff_of(reading[0]):
        pct = 60
        out.update(pct=60, assumed=True)
        reason = f"{name}: kein Lesetest bis {_wd(reading[0])} {_dm(reading[0])} 09:00 → wie 60 %"
    elif test and reading and test < real_today:
        # the test day is over without a rating (Heute only asks on the day) — e.g. a week off before
        # the first reading day (#36): it's decided, not "still ahead"
        pct = 60
        out.update(pct=60, assumed=True)
        reason = f"{name}: kein Lesetest am {_wd(test)} {_dm(test)} → wie 60 %"
    elif test:  # the test is still ahead: it decides
        first = _wd(reading[0]) + " " + _dm(reading[0]) if reading else "danach"
        out.update(mode="frei", why=f"{name}: der Lesetest am {_wd(test)} {_dm(test)} entscheidet, wie du ab {first} liest")
        return out
    else:
        out.update(mode="frei", why=f"{name}: frei lesen, kein Wörterbuch", show=False)
        return out
    if pct >= 80:
        out.update(mode="frei", why=f"{reason} → frei lesen, kein Wörterbuch")
    elif pct >= 60:
        out.update(mode="nachschlagen", why=f"{reason} → bis zu 3 Wörter pro Seite nachschlagen")
    else:
        back = next(iter(_days(start, data, is_book, n + 1, pauses)), hi)  # the same days of the next pass
        retest = next(iter(_days(start, data, is_test, n + 1, pauses)), None)
        out.update(mode="spaeter", back=back.isoformat(), retest=retest.isoformat() if retest else None,
                   why=f"{reason} → kommt nach Woche {(n + 1) * weeks} wieder"
                       f"{f' (neuer Lesetest {_wd(retest)} {_dm(retest)})' if retest else ''}, bis dahin nachrichtenleicht")
    return out


def cutoff_of(day: date) -> str:
    """09:00 Berlin on `day`, as stored timestamps are written (UTC ISO)."""
    return datetime.combine(day, CUTOFF, srs.TZ).astimezone(timezone.utc).isoformat()


LOOKUP_TEXT = "Bis zu 3 Wörter pro Seite nachschlagen — nur Wörter, die immer wieder vorkommen."
WEEKDAY = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _dm(d: date) -> str:
    return f"{d.day}.{d.month}."


def _wd(d: date) -> str:
    return WEEKDAY[d.weekday()]


def book_text(text: str, mode: str) -> str:
    """The day text for a book day in its mode: "Frei lesen: …" becomes the lookup rule at 60 %."""
    if mode != "nachschlagen":
        return text
    i = text.find("Frei lesen:")
    return (text[:i] if i >= 0 else text.rstrip() + " ") + LOOKUP_TEXT


def action(r: dict, start: date, data: dict, today: date) -> str:
    """What the plan does about a rating under 70 % (Heute's "Zu schwer" line)."""
    if r["book"]:
        nxt = today + timedelta(days=1)
        return book_mode(r["book"], nxt, start, data)["why"] + "."
    if r["item"].startswith("news:leicht:"):
        return (f"Nächstes Mal {leicht_count()} statt 5 Artikel pro 35 Minuten. Bleibt nachrichtenleicht unter 70 %, "
                "wird der Plan von Hand angepasst.")
    if r["kind"] == "news":
        return "tagesschau.de ist aus dem Plan: Frei lesen kommt jetzt von nachrichtenleicht.de (Einfache Sprache)."
    return "Nur markiert — Clips, Podcasts und Texte passt Kaskade nicht von selbst an; der Plan wird von Hand angepasst."


def too_hard(today: date, start: date, data: dict, days: int = 7) -> list[dict]:
    """Ratings under 70 % from the last week, newest first, each with what the plan does about it."""
    rows = [r for r in recent(today - timedelta(days=days)) if r["pct"] is not None and r["pct"] < TOO_HARD]
    return [{**r, "action": action(r, start, data, today)} for r in rows[:4]]
