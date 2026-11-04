"""The book queue (#38): one book at a time as the first item of the lesen block, on every plan day
from a plan slot on (data["books"] in phase-2b.json: {"from": {"week", "day"}, "queue": [...]}).

The queue says which book comes next; stock.json says how a book is split into days: a read-along
book (paper + audiobook, `readAlong`) by whole chapters — `perDay` of them, or as many as fit into
`maxMinutes` of audio — and the others by their `parts`. A queue entry may start the book later
(`fromPart`) and with a Lesetest (#24). Like the rolling clips (#21), his real days move it on: a day
he rated (any %, also skipped) or ticked off counts, a day with neither brings the same part again.
Today and later days are taken as done; a rating given today changes the days after it, never today.

Ratings set the mode for the book's next days (#23/#24):
- read-along, 60 % or more: `perDay` chapters a day. 20–40 %: "Kapitel zweimal hören" — that day's
  chapters again, one a day, first only listening, then reading along — and one chapter a day like
  that until a rating of 60 % or more. Two ratings of 20–40 % in a row while repeating park the book.
- the others: 80–100 % frei, 60 % up to three words a page looked up, 20–40 % parked; a Lesetest
  that was done but not rated counts as 60 %.
A parked book moves behind the others in the queue with its place kept, and starts fresh there.
"""
import logging
from datetime import date, timedelta

from . import db, plan, stock

log = logging.getLogger(__name__)

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr"]
HARD = 60          # a rating under this (20 or 40 %) means too hard for the book
REPEATS_TO_PARK = 2
HORIZON = 3 * 365  # days the queue is laid out ahead (it's done long before)


def config(data: dict) -> dict | None:
    return data.get("books")


def start_day(data: dict, start: date, pauses=()) -> date | None:
    """The first plan day of the queue: its plan slot, after the weeks off (#36)."""
    q = config(data)
    if not q:
        return None
    return plan.slot_date(start, q["from"]["week"] - 1, WEEKDAYS.index(q["from"]["day"]), pauses)


def ids(data: dict) -> list[str]:
    return [e["book"] for e in (config(data) or {}).get("queue", [])]


def _dm(d: date) -> str:
    return f"{d.day}.{d.month}."


def _wd(d: date) -> str:
    return WEEKDAYS[d.weekday()] if d.weekday() < 5 else ["Sa", "So"][d.weekday() - 5]


def name(b: dict) -> str:
    return b.get("short") or (b.get("author") or b["title"]).split()[-1]


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " und " + names[-1]


# ── One book in the queue ────────────────────────────────────────────────────

class _Book:
    def __init__(self, entry: dict):
        self.entry = entry
        self.b = stock.book(entry["book"]) or {"id": entry["book"], "title": entry["book"], "author": ""}
        self.id = self.b["id"]
        self.name = name(self.b)
        self.along = bool(self.b.get("readAlong"))
        parts = self.b.get("parts", [])
        self.ptr = next((i for i, p in enumerate(parts) if p["part"] == entry.get("fromPart")), 0)
        self.fresh()

    def fresh(self):
        """Mode state as at the book's start (also when a parked book comes back)."""
        self.test = bool(self.entry.get("lesetest")) and self.ptr == next(
            (i for i, p in enumerate(self.b.get("parts", [])) if p["part"] == self.entry.get("fromPart")), 0)
        self.pct, self.rated, self.assumed, self.source = None, None, False, None
        self.repeat, self.pending, self.bad = False, [], []

    def finished(self) -> bool:
        if self.along:
            return self.ptr >= len(self.b["chapters"]) and not self.pending
        return self.ptr >= len(self.b.get("parts", []))

    # ── what a day gets ──
    def part(self, first: bool) -> dict:
        if self.test:
            t = self.entry["lesetest"]
            return {"book": self.id, "kind": "lesetest", "part": t["part"], "story": t.get("story"),
                    "minutes": t.get("minutes", 25), "first": first}
        if self.along:
            return self._chapters(first)
        p = self.b["parts"][self.ptr]
        return {"book": self.id, "kind": "book", "part": p["part"], "minutes": p["minutes"], "desc": p["desc"],
                "first": first, "index": self.ptr}

    def _chapters(self, first: bool) -> dict:
        chs = self.b["chapters"]
        repeat = bool(self.pending) or self.repeat
        again = bool(self.pending)  # a chapter he has heard once already
        if repeat:
            idx = [self.pending[0] if self.pending else self.ptr]
        elif self.b.get("perDay"):
            idx = list(range(self.ptr, min(self.ptr + self.b["perDay"], len(chs))))
        else:  # as many whole chapters as fit into maxMinutes of audio, at least one
            idx, total = [], 0.0
            for i in range(self.ptr, len(chs)):
                if idx and total + chs[i]["audioMin"] > self.b["maxMinutes"]:
                    break
                idx.append(i)
                total += chs[i]["audioMin"]
        audio = sum(self.minutes_of(i) for i in idx)
        part = {"book": self.id, "kind": "book", "chapters": idx, "repeat": repeat, "again": again, "first": first,
                "minutes": round(2 * audio if repeat else audio), "fromStart": idx[0] == 0 and not repeat,
                "after": idx[0] - 1 if idx[0] > 0 else None, "last": idx[-1] == len(chs) - 1 and not repeat}
        t = along(self.b, part)
        return {**part, "part": t["label"], "desc": t["text"], "detail": t["detail"]}

    def minutes_of(self, i: int) -> float:
        c = self.b["chapters"][i]
        if "audioMin" in c:
            return c["audioMin"]
        return self.b["audiobook"]["minutes"] / len(self.b["chapters"])  # no chapter marks: the average

    # ── what a done day changes ──
    def done(self, part: dict, day: date, pct: int | None, kind: str | None) -> str | None:
        """Move on after a day he did; returns "park" when the book has to wait."""
        if part["kind"] == "lesetest":
            self.test = False
            self.pct, self.rated, self.source = (60 if pct is None else pct), day, "lesetest"
            self.assumed = pct is None
            return "park" if self.pct < HARD else None
        if self.along:
            if part["repeat"]:
                if self.pending:
                    self.pending.pop(0)
                else:
                    self.ptr += 1
                if pct is not None and pct < HARD:
                    self.bad.append((day, pct))
                    if len(self.bad) >= REPEATS_TO_PARK:
                        return "park"
                elif pct is not None:
                    self.repeat, self.bad = False, []
            else:
                self.ptr = part["chapters"][-1] + 1
                if pct is not None and pct < HARD:
                    self.repeat, self.pending, self.bad = True, list(part["chapters"]), []
            if pct is not None:
                self.pct, self.rated, self.source = pct, day, kind
            return None
        self.ptr += 1
        if pct is not None:
            self.pct, self.rated, self.source, self.assumed = pct, day, kind, False
            if pct < HARD:
                return "park"
        return None

    # ── how it's read now ──
    def mode(self) -> dict:
        out = {"book": self.id, "name": self.name, "pct": self.pct, "assumed": self.assumed,
               "date": self.rated.isoformat() if self.rated else None, "source": self.source, "show": self.rated is not None}
        when = "im Lesetest" if self.source == "lesetest" else f"am {_wd(self.rated)} {_dm(self.rated)}" if self.rated else ""
        if self.along:
            per = self.b.get("perDay")
            normal = f"{'zwei Kapitel' if per == 2 else f'{per} Kapitel' if per else 'ein bis zwei Kapitel'} am Tag"
            if self.repeat:
                return {**out, "mode": "zweimal", "show": True,
                        "why": f"{self.name}: {self.pct} % {when} → Kapitel zweimal hören: erst nur hören, dann mitlesen (ein Kapitel am Tag)"}
            if self.pending:  # better again, one heard-once chapter still gets its second go
                n = chapter_name(self.b["chapters"][self.pending[0]])
                return {**out, "mode": "zweimal", "show": True,
                        "why": f"{self.name}: {self.pct} % {when} → noch {n} zweimal, danach wieder mitlesen, {normal}"}
            reason = f"{self.name}: {self.pct} % {when} → " if self.rated else f"{self.name}: "
            return {**out, "mode": "mitlesen", "why": f"{reason}{'weiter ' if self.rated else ''}mitlesen, {normal}"}
        if self.test:
            return {**out, "mode": "frei", "show": True, "why": f"{self.name}: der Lesetest entscheidet, wie du danach liest"}
        if self.pct is None:
            return {**out, "mode": "frei", "why": f"{self.name}: frei lesen, kein Wörterbuch"}
        reason = (f"{self.name}: kein Ergebnis im Lesetest → wie 60 %" if self.assumed else f"{self.name}: {self.pct} % {when}")
        if self.pct >= 80:
            return {**out, "mode": "frei", "why": f"{reason} → frei lesen, kein Wörterbuch"}
        return {**out, "mode": "nachschlagen", "why": f"{reason} → bis zu 3 Wörter pro Seite nachschlagen"}


# ── What a read-along day says ───────────────────────────────────────────────

NOT_CHAPTERS = "die Tracks in Spotify sind keine Buchkapitel"


def chapter_name(c: dict) -> str:
    return f"Kapitel {c['n']}" if c.get("n") else c["title"]


def _span(chs: list[dict]) -> str:
    if len(chs) == 1:
        return chapter_name(chs[0])
    if chs[0].get("n") and chs[-1].get("n"):
        return f"Kapitel {chs[0]['n']}–{chs[-1]['n']}"
    return f"{chapter_name(chs[0])} bis {chapter_name(chs[-1])}"


def along(b: dict, part: dict) -> dict:
    """label (the item's `part`), text and detail of a read-along day."""
    chs = [b["chapters"][i] for i in part["chapters"]]
    ab = b["audiobook"]
    book = f"{b['author']}: {b['title']}"
    spotify = f"Spotify: Hörbuch „{ab['title']}“"
    after = chapter_name(b["chapters"][part["after"]]) if part.get("after") is not None else None
    if part["repeat"]:
        c = chs[0]
        n = chapter_name(c)
        where = (f"{spotify} zurück an den Anfang von {n}" if part.get("again") else
                 f"{spotify} weiter, wo du aufgehört hast (nach {after}), nach dem ersten Hören zurück an den Anfang von {n}")
        return {"label": f"{n} zweimal — erst nur hören, dann mitlesen",
                "text": f"{book} — {n} „{c['title']}“ zweimal: erst nur hören (Buch zu), dann noch einmal von vorn und im "
                        f"Papierbuch mitlesen. Nicht für einzelne Wörter anhalten. {where} — {NOT_CHAPTERS}.",
                "detail": f"Spotify: zurück an den Anfang von {n}" if part.get("again") else "Spotify: weiter, wo du aufgehört hast"}
    bits, prev = [], None
    for c in chs:
        intro = ""
        if c.get("part") and c["part"] != prev:
            head, _, title = c["part"].partition(": ")
            intro = f"{head} „{title}“: "
        prev = c.get("part")
        bits.append(f"{intro}{chapter_name(c)} „{c['title']}“" if c.get("n") else f"„{c['title']}“")
    end = part["last"] and b.get("afterword")
    what = " und ".join(bits) + (f" und „{b['afterword']}“" if end else "")
    where = f"{spotify} von Anfang an (Track 1)" if part["fromStart"] else f"{spotify} weiter, wo du aufgehört hast (nach {after})"
    stop = "Danach ist das Buch zu Ende" if part["last"] else f"Stopp am Ende von {chapter_name(chs[-1])} im Buch — {NOT_CHAPTERS}"
    return {"label": f"{_span(chs)}{' und Nachwort' if end else ''} — Papierbuch mitlesen, Hörbuch auf Spotify",
            "text": f"{book} — {what}. Im Papierbuch mitlesen, das Hörbuch ({ab['reader']}, ungekürzt) läuft dazu in normalem "
                    f"Tempo: nicht für einzelne Wörter anhalten, bis zu 3 Wörter pro Seite nachschlagen ist in Ordnung. "
                    f"{where}. {stop}.",
            "detail": "Spotify: von Anfang an (Track 1)" if part["fromStart"] else "Spotify: weiter, wo du aufgehört hast"}


# ── The days ─────────────────────────────────────────────────────────────────

def _history(frm: date, upto: date) -> tuple[dict, set]:
    """Ratings of book items in the lesen block ((date, book) → (pct, kind), the newest) and the days
    the lesen block was ticked off, from `frm` to `upto`."""
    with db.tx() as conn:
        rated = conn.execute(
            "SELECT local_date, book, pct, kind FROM ratings WHERE block = 'lesen' AND book IS NOT NULL"
            " AND local_date >= ? AND local_date <= ? ORDER BY created_at, id", (frm.isoformat(), upto.isoformat())).fetchall()
        done = {r[0] for r in conn.execute("SELECT local_date FROM plan_done WHERE block = 'lesen' AND local_date >= ?"
                                           " AND local_date <= ?", (frm.isoformat(), upto.isoformat()))}
    return {(r["local_date"], r["book"]): (r["pct"], r["kind"]) for r in rated}, done


def _plan_days(data: dict, start: date, pauses, frm: date):
    lesen = any(b["id"] == "lesen" for b in data["block"])
    d = frm
    for _ in range(HORIZON):
        if lesen and plan.plan_day(start, d, data, pauses)["day"]:
            yield d
        d += timedelta(days=1)


def schedule(data: dict, start: date, pauses, real_today: date) -> dict:
    """{"days": date → the day's book item, "books": book id → {first, last, parked, line…}} for the
    whole queue. Days before `real_today` go as he really did them; from today on each day is taken
    as done with no new rating."""
    frm = start_day(data, start, pauses)
    out = {"days": {}, "books": {}, "from": frm}
    if not frm:
        return out
    order = [_Book(e) for e in config(data)["queue"]]
    rated, done = _history(frm, real_today)
    info = {bk.id: {"book": bk.id, "name": bk.name, "first": None, "last": None, "parked": [], "resume": bk.entry.get("resume")}
            for bk in order}
    for d in _plan_days(data, start, pauses, frm):
        while order and order[0].finished():
            order.pop(0)
        if not order:
            break
        bk = order[0]
        first = info[bk.id]["first"] is None
        part = bk.part(first)
        part["mode"] = bk.mode()
        out["days"][d] = part
        info[bk.id]["first"] = info[bk.id]["first"] or d
        info[bk.id]["last"] = d
        iso = d.isoformat()
        if d < real_today or d == real_today and ((iso, bk.id) in rated or iso in done):
            if (iso, bk.id) not in rated and iso not in done:
                continue  # not done: the same part again on the next plan day
            pct, kind = rated.get((iso, bk.id), (None, None))
        else:
            pct, kind = None, None  # today (not done yet) and later: as planned
        if bk.done(part, d, pct, kind) == "park":
            info[bk.id]["parked"].append({"date": iso, "ratings": [(x.isoformat(), p) for x, p in bk.bad] or [(iso, bk.pct)]})
            if d < real_today:
                log.warning("#38: %s parked after %s — it waits behind the other books", bk.id, info[bk.id]["parked"][-1]["ratings"])
            order.append(order.pop(0))
            bk.fresh()
    out["books"] = info
    return out


def first_days(sched: dict) -> dict[str, date]:
    return {k: v["first"] for k, v in sched["books"].items() if v["first"]}


def lines(sched: dict, data: dict, day: date) -> list[dict]:
    """Fahrplan's "Bücher im Plan" (and Heute's book modes): each book of the queue as it stands on
    `day` — the one read then (or next) with its mode, the others "nach …" in the order they come."""
    days = sched["days"]
    nxt: dict[str, date] = {}
    for d in sorted(days):
        if d >= day:
            nxt.setdefault(days[d]["book"], d)
    ahead = sorted(nxt, key=nxt.get)
    out = []
    for book_id in ahead:
        b = stock.book(book_id) or {"id": book_id, "title": book_id}
        i, n = sched["books"][book_id], name(b)
        if book_id == ahead[0]:
            m = days[nxt[book_id]]["mode"]
            start = f" — ab {_wd(i['first'])} {_dm(i['first'])}" if not m["show"] and i["first"] >= day else ""
            out.append({**m, "show": True, "current": True, "why": m["why"] + start})
            continue
        before = [name(stock.book(x) or {"id": x, "title": x}) for x in ahead[:ahead.index(book_id)]]
        parked = [p for p in i["parked"] if date.fromisoformat(p["date"]) < nxt[book_id]]
        if parked:
            pcts = " und ".join(f"{p} % am {_wd(date.fromisoformat(x))} {_dm(date.fromisoformat(x))}" for x, p in parked[-1]["ratings"])
            why = f"{n}: {pcts} → pausiert, kommt nach {_and(before)} wieder"
        else:
            why = f"{n}: nach {_and(before)}"
            if i.get("resume") and i["first"] == nxt[book_id]:
                why += f", weiter mit {i['resume']}"
            elif len(out) == 1:  # the next one in line: when it starts
                why += f", ab {_wd(nxt[book_id])} {_dm(nxt[book_id])}"
        out.append({"book": book_id, "name": n, "show": True, "mode": "pausiert" if parked else "spaeter",
                    "first": nxt[book_id].isoformat(), "why": why if why.endswith(".") else why + "."})
    for book_id, i in sched["books"].items():  # read to the end before `day`
        if book_id not in nxt and i["last"]:
            out.append({"book": book_id, "name": i["name"], "show": True, "mode": "fertig", "why": f"{i['name']}: zu Ende gelesen."})
    return out


def line(sched: dict, data: dict, book_id: str, day: date) -> str | None:
    """One book's line (for Heute's "Zu schwer" and an old plan day's mode)."""
    return next((x["why"] for x in lines(sched, data, day) if x["book"] == book_id), None)
