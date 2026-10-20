"""Exact assignments for every block of a plan day, their status, and the daily Materialcheck (#16).

A plan day lists one material per block (data/plan/*.json → day["materials"]); this module
turns it into what Heute shows and what "Starten" opens: a library clip with a time range, a
YouTube/Netflix link for Language Reactor, that day's nachrichtenleicht articles, a library text,
a book part (read in the mode its latest rating set, #24), the Lesetest, an exam task. Status is
"ready" or "todo" — "todo" only for real gaps.
"""
import html
import json
import logging
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime

from . import config, db, plan, ratings, rolling, srs, stock, texts, themes

log = logging.getLogger(__name__)

NEWS_FEEDS = {
    # #22: Deutschlandfunk's news in Einfacher Sprache — it has no news RSS, its homepage lists the articles
    "leicht": ("nachrichtenleicht.de", "https://www.nachrichtenleicht.de/"),
    # tagesschau.de: only the day Matt already read (W1 Di, 20 % understood) still points here
    "top": ("tagesschau.de", "https://www.tagesschau.de/index~rss2.xml"),
    "inland": ("tagesschau.de · Inland", "https://www.tagesschau.de/inland/index~rss2.xml"),
    "wirtschaft": ("tagesschau.de · Wirtschaft", "https://www.tagesschau.de/wirtschaft/index~rss2.xml"),
    "wissen": ("tagesschau.de · Wissen", "https://www.tagesschau.de/wissen/index~rss2.xml"),
    "gesundheit": ("tagesschau.de · Gesundheit", "https://www.tagesschau.de/wissen/gesundheit/index~rss2.xml"),
}
NOT_ARTICLES = ("/multimedia/", "liveblog", "livestream", "/video/", "/audio/", "/podcast", "/sendung/")
CHECK_FILE = "materialcheck.json"
LR_NOTE = "in Chrome mit Language Reactor"


# ── Small helpers ────────────────────────────────────────────────────────────

seconds, clock = rolling.seconds, rolling.clock  # "30:14" ↔ 1814


def _minutes(a: float, b: float) -> int:
    return max(1, round((b - a) / 60))


# ── News: that day's articles, links only ────────────────────────────────────

NUMBER = {3: "drei", 4: "vier", 5: "fünf", 6: "sechs", 7: "sieben"}
LEICHT_TEXT = ("nachrichtenleicht.de (Deutschlandfunk, Nachrichten in Einfacher Sprache): die {n} neuesten Artikel. "
               "{links} Lesen, ohne nachzuschlagen — eine Lücke ist kein Grund zu stoppen.")


def _iso(value: str | None) -> str | None:
    try:
        return datetime.fromisoformat(value).isoformat() if value else None
    except ValueError:
        return None


def pick_leicht(page: bytes, count: int | None = 5) -> list[dict]:
    """The newest articles on nachrichtenleicht.de, from the teaser data in its homepage."""
    s = page.decode("utf-8", "replace")
    out, seen = [], set()
    for raw in re.findall(r'class="js-client-queries" data-json="([^"]*)"', s):
        try:
            v = json.loads(html.unescape(raw)).get("value")
        except ValueError:
            continue
        if not isinstance(v, dict) or v.get("__typename") != "Teaser" or v.get("contentType") != "article":
            continue
        url, title = (v.get("path") or "").strip(), (v.get("title") or "").strip()
        if not url.startswith("https://www.nachrichtenleicht.de/") or not title or url in seen:
            continue
        seen.add(url)
        out.append({"title": title, "url": url, "published": _iso(v.get("date") or v.get("firstPublicationDate"))})
    if not out:  # no teaser data: the article links in page order (newest first)
        for url, title in re.findall(r'<article[^>]*>\s*<a href="(https://www\.nachrichtenleicht\.de/[^"]+)" title="([^"]+)"', s):
            if url not in seen:
                seen.add(url)
                out.append({"title": html.unescape(title), "url": url, "published": None})
        return out[:count]
    out.sort(key=lambda a: a["published"] or "", reverse=True)
    return out[:count]


def pick_articles(feed_xml: bytes, count: int | None = 3) -> list[dict]:
    """The newest real articles from a tagesschau RSS feed (no live blogs, videos, podcasts)."""
    channel = ET.fromstring(feed_xml).find("channel")
    out = []
    for entry in channel.findall("item") if channel is not None else []:
        url = (entry.findtext("link") or "").strip()
        title = (entry.findtext("title") or "").strip()
        if not url.startswith("https://www.tagesschau.de/") or any(x in url for x in NOT_ARTICLES) or not title:
            continue
        try:
            published = parsedate_to_datetime(entry.findtext("pubDate") or "")
        except (TypeError, ValueError):
            published = None
        out.append({"title": title, "url": url, "published": published.isoformat() if published else None})
    out.sort(key=lambda a: a["published"] or "", reverse=True)
    return out[:count]


def offline() -> bool:
    """KASKADE_OFFLINE=1 (E2E): no news fetching, no link checks."""
    return os.environ.get("KASKADE_OFFLINE") == "1"


def fetch_feed(url: str) -> bytes:
    if offline():
        raise OSError("offline")
    with urllib.request.urlopen(urllib.request.Request(url, headers=stock.UA), timeout=10) as r:
        return r.read()


def parse_feed(feed: str, body: bytes) -> list[dict]:
    """Every article of a feed, newest first."""
    return pick_leicht(body, None) if feed == "leicht" else pick_articles(body, None)


def news_for(day: date, feed: str, today: date | None, count: int = 3) -> list[dict] | None:
    """The articles picked for `day` (fixed once picked). Picked on the day itself; None before
    (and in a preview, `today` None: only what was picked already).
    The newest ones he hasn't had on an earlier day."""
    with db.tx() as conn:
        row = conn.execute("SELECT items FROM news_picks WHERE local_date = ? AND feed = ?",
                           (day.isoformat(), feed)).fetchone()
        had = {a["url"] for r in conn.execute("SELECT items FROM news_picks WHERE feed = ? AND local_date < ?",
                                              (feed, day.isoformat())) for a in json.loads(r["items"])}
    if row:
        return json.loads(row["items"])
    if day != today:
        return None
    try:
        items = [a for a in parse_feed(feed, fetch_feed(NEWS_FEEDS[feed][1])) if a["url"] not in had][:count]
    except Exception as e:  # offline: Heute says so, the Materialcheck reports it
        log.warning("news %s: %s", feed, e)
        return []
    if items:
        with db.tx() as conn:
            conn.execute("INSERT OR REPLACE INTO news_picks(local_date, feed, items) VALUES (?, ?, ?)",
                         (day.isoformat(), feed, json.dumps(items, ensure_ascii=False)))
    return items


# ── Context ──────────────────────────────────────────────────────────────────

class Ctx:
    """Everything the item builders need, gathered once per request."""

    def __init__(self, today: date, now: datetime | None = None):
        self.today = today
        self.now = now or srs.now_utc()
        self.real_today = self.now.astimezone(srs.TZ).date()  # `today` may be a preview day
        self.live = True  # False for previews (?today=, ?phase=): they never fix a day's range
        stock.link_existing()  # a clip uploaded under a catalog title counts as that item
        self.lib = stock.by_key()
        with db.tx() as conn:
            self.positions = {r["media_id"]: r["position"] for r in conn.execute("SELECT media_id, position FROM media_progress")}
            self.unseen = len(srs.deck()) + conn.execute("SELECT COUNT(*) FROM mined").fetchone()[0] - \
                conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        self.ai = config.anthropic_key() is not None
        self.bought = set(db.get_setting("booksBought", []))
        self.setup_done = set(db.get_setting("setupDone", []))
        self.links = read_check().get("links", {})
        self.pauses = plan.pauses()  # #36: the weeks he took off
        self._rolling: dict = {}

    def rolling(self, block: str, data: dict, start: date) -> dict[date, dict]:
        """#21: the block's rolling clip ranges from `today` on (computed once per request)."""
        key = (block, id(data), start)
        if key not in self._rolling:
            self._rolling[key] = rolling.plan_block(block, data, start, self)
        return self._rolling[key]

    def due_cards(self, day: date) -> int:
        end = datetime.combine(day + timedelta(days=1), time(0), srs.TZ).astimezone(timezone.utc)
        with db.tx() as conn:
            return conn.execute("SELECT COUNT(*) FROM cards WHERE status = 'learning' AND due < ?",
                                (end.isoformat(),)).fetchone()[0]

    def new_cards(self, day: date) -> int:
        if day == self.today:
            with db.tx() as conn:
                return srs.counts(conn, self.now)["new"]
        caught = db.get_setting("cardsCaughtUp", [])
        if srs.backlog_pause(self.pauses, caught, day.isoformat(), self.due_cards(day)):
            return 0  # #36: after a week off the backlog comes first
        return min(srs.new_per_day(), max(0, self.unseen))


# ── Item builders, one per kind ──────────────────────────────────────────────

def _base(block: str, kind: str, **kw) -> dict:
    return {"block": block, "kind": kind, "title": "", "part": None, "minutes": None, "source": None,
            "origin": "real", "detail": None, "status": "ready", "start": None, "links": [], "check": None, **kw}


def _clip(m: dict, ctx: Ctx, day: date) -> dict:
    it = stock.item(m["clip"]) or {"title": m["clip"], "source": None}
    row = ctx.lib.get(m["clip"])
    end = seconds(m.get("to")) or (row and row["duration"]) or it.get("duration") or 0
    start = seconds(m.get("from")) or 0
    out = _base(m["block"], "clip", title=it["title"], source=it.get("source"), audio=it.get("kind") in ("podcast", "audio"), clip=m["clip"],
                range=[start, end], part=f"{clock(start)}–{clock(end)}" if end else None,
                minutes=_minutes(start, end) if end else None)
    if not row or not row["media_file"]:
        fetch_on = it.get("fetchOn")
        out.update(status="todo", detail=f"wird am {fetch_on} geholt" if fetch_on and date.fromisoformat(fetch_on) > ctx.today
                   else "fehlt noch in der Bibliothek — Kaskade holt es beim nächsten Abgleich")
        return out
    if not stock.playable(row):
        out.update(status="todo", detail="wird gerade für alle Browser umgewandelt")
        return out
    pos = ctx.positions.get(row["id"], 0) or 0
    out["mediaId"] = row["id"]
    out["position"] = pos
    if end and pos > start and pos >= end - 5:
        out["detail"] = "in deiner Bibliothek · Ziel schon erreicht ✓"
    elif 2 < pos < start - 5:
        out["detail"] = f"in deiner Bibliothek · du bist bei {clock(pos)}: ab deiner Position bis {clock(end)}"
    elif start + 5 < pos:
        out["detail"] = f"in deiner Bibliothek · weiter ab {clock(pos)}"
    else:
        out["detail"] = "in deiner Bibliothek"
    out["start"] = {"to": f"/schauen/{row['id']}?von={int(start)}&bis={int(end)}"}
    return out


def _rolled(m: dict, ctx: Ctx, day: date, data: dict, start: date) -> dict:
    """A clip whose range follows his real position (#21). Past days keep the range they had."""
    if day < ctx.today:
        r = rolling.frozen(day, m["block"])
        return _clip({**m, **({"clip": r["clip"], "from": r["from"], "to": r["to"]} if r else {})}, ctx, day)
    r = ctx.rolling(m["block"], data, start).get(day)
    if not r:
        return _clip(m, ctx, day)  # everything before it is watched: as planned
    item = _clip({**m, "clip": r["clip"], "from": r["from"], "to": r["to"]}, ctx, day)
    item.update(text=r["text"], rolling=True)
    return item


def _satzcheck(m: dict, ctx: Ctx, day: date) -> dict:
    out = _clip({**m, "kind": "clip"}, ctx, day)
    start = seconds(m.get("from")) or 0
    out.update(kind="satzcheck", part=f"Satz-Check {clock(start)}–{clock(start + 180)}, danach Schauen bis {clock(out['range'][1])}")
    if out.get("mediaId"):
        out["start"] = {"to": f"/satz-check?clip={out['mediaId']}&ab={int(start)}"}
    return out


def _external(m: dict, ctx: Ctx, kind: str) -> dict:
    it = stock.item(m["clip"]) or {}
    start, end = seconds(m.get("from")) or 0, seconds(m.get("to")) or it.get("duration") or 0
    href = f"https://www.youtube.com/watch?v={it['video']}&t={int(start)}s" if kind == "youtube" else it.get("url")
    part = f"{clock(start)}–{clock(end)}" if end else None
    if kind == "netflix" and m.get("episode"):
        part = f"{m['episode']}" + (f", {clock(start)}–{clock(end)}" if end else "")
    out = _base(m["block"], kind, title=it.get("title", m["clip"]), source=it.get("source"), part=part, clip=m["clip"],
                minutes=_minutes(start, end) if end else None, start={"href": href, "note": LR_NOTE},
                detail=f"öffnet {'YouTube' if kind == 'youtube' else 'Netflix'} in einem neuen Tab — {LR_NOTE}")
    if ctx.links.get(href) is False:
        out.update(status="todo", detail="Link antwortet gerade nicht — Kaskade sucht Ersatz")
    return out


def _news(m: dict, ctx: Ctx, day: date) -> dict:
    name = NEWS_FEEDS[m["feed"]][0]
    # nachrichtenleicht: 5 articles, adjusted to how much he understood last time (#22/#23)
    count = ratings.leicht_count(m.get("minutes") or 35) if m["feed"] == "leicht" else m.get("count", 3)
    # picked only on the real day, never by a preview (?today=, #36's check): it would fix a later day's articles early
    items = news_for(day, m["feed"], ctx.real_today if ctx.live else None, count)
    n = len(items) if items else count
    out = _base(m["block"], "news", title=f"{name}: die {n} neuesten Artikel", source=name, minutes=m.get("minutes"),
                feed=m["feed"], count=n)
    if m["feed"] == "leicht":
        out["text"] = LEICHT_TEXT.format(n=NUMBER.get(n, n), links=f"Heute stehen hier die {NUMBER.get(n, n)} Links.")
    if items:
        out.update(links=items, detail=f"ausgewählt für {day.day}.{day.month}.{day.year}")
    elif items is None:
        out["detail"] = f"Die {NUMBER.get(n, n)} Links stehen am Morgen hier (neueste Meldungen des Tages)."
    else:
        out.update(status="todo", detail=f"{name} antwortet gerade nicht — später neu laden")
    return out


def _text(m: dict, ctx: Ctx) -> dict:
    t = texts.get(m["text"])
    words = len(t["text"].split()) if t else 0
    free = m["block"] == "lesen"  # the free-reading block: no help; the input block reads interactively
    return _base(m["block"], "text", title=t["title"] if t else m["text"], origin=(t or {}).get("origin", "ai"), textId=m["text"],
                 source="Kaskade-Bibliothek", part=f"{t['level']} · {words} Wörter" if t else None,
                 minutes=max(5, round(words / 110)) if t else None,
                 start={"to": f"/lesen/{m['text']}" + ("?modus=frei" if free else "")},
                 detail="frei lesen: ohne Wörterbuch, ohne Hilfen" if free else "interaktiv: Wörter antippen, Sätze minen")


def _book(m: dict, ctx: Ctx, first_day: date | None, day: date, text: str, data: dict, start: date) -> dict:
    """A book part, read the way the book's latest rating says (#24) — or, at 20–40 %, nachrichtenleicht."""
    b = stock.book(m["book"]) or {"id": m["book"], "author": "", "title": m["book"], "format": "paper"}
    mode = ratings.book_mode(b["id"], day, start, data, ctx.pauses)
    if mode["mode"] == "spaeter":
        out = _news({"block": m["block"], "kind": "news", "feed": "leicht", "minutes": m.get("minutes", 35)}, ctx, day)
        out.update(mode=mode, text=f"Statt {mode['name']}: {out['text']}")
        return out
    out = _base(m["block"], "book", title=f"{b['author']}: {b['title']}".strip(": "), part=m.get("part"),
                minutes=m.get("minutes", 35), source=f"{b['author']} · {b['title']}".strip(" ·"), bookId=b["id"],
                text=ratings.book_text(text, mode["mode"]), mode=mode if mode["show"] else None)
    if b["id"] not in ctx.bought:
        buy_by = stock.notice(first_day, b.get("format", "paper")) if first_day else None
        out.update(status="todo", detail=f"Kaufen bis {buy_by.day}.{buy_by.month}." if buy_by else "noch nicht gekauft")
    else:
        out["detail"] = "gekauft ✓"
    if mode["mode"] == "nachschlagen":
        out["detail"] += " · bis zu 3 Wörter pro Seite nachschlagen"
    return out


def leseprobe(b: dict, part: str) -> str | None:
    """The publisher's free Leseprobe, opened at the first page of `part` ("S. 7–8")."""
    lp = b.get("leseprobe")
    first = re.match(r"S\. (\d+)", part or "")
    if not lp:
        return None
    return lp["url"] + (f"#page={int(first.group(1)) + lp.get('pdfOffset', 0)}" if first else "")


def _lesetest(m: dict, ctx: Ctx) -> dict:
    """#24: the first two pages of a book without a dictionary, then "Wie viel hast du verstanden?"."""
    b = stock.book(m["book"]) or {"id": m["book"], "author": "", "title": m["book"]}
    name = ratings.short_author(b)
    story = "„Fähner“" if b["id"] == "schirach-verbrechen" else None
    title = f"Lesetest: {name}, {b['title']} — die ersten zwei Seiten" + (f" von {story}" if story else "")
    out = _base("pruefung", "lesetest", title=title, part=m["part"], minutes=m.get("minutes", 25), bookId=b["id"],
                source=f"{b['author']} · {b['title']}".strip(" ·"),
                text=f"{m['part']} ohne Wörterbuch lesen, nicht zurückblättern — dann hier einschätzen: "
                     f"Wie viel hast du verstanden? Das Ergebnis bestimmt, wie du {name} in den nächsten Wochen liest.")
    href = leseprobe(b, m["part"])
    if href and ctx.links.get(href) is not False:
        out.update(start={"href": href, "note": "Leseprobe des Verlags"},
                   detail=f"Leseprobe des Verlags ({b.get('publisher', 'Verlag')}), öffnet bei {m['part'].split('–')[0]} · ohne Wörterbuch lesen, dann einschätzen")
    elif b["id"] in ctx.bought:
        out["detail"] = f"im Buch, {m['part']} · ohne Wörterbuch lesen, dann einschätzen"
    else:
        out.update(status="todo", detail="Leseprobe antwortet gerade nicht — und das Buch ist noch nicht als gekauft abgehakt")
    return out


def _exam(prompt: dict, ctx: Ctx) -> dict:
    out = _base("pruefung", "exam", title=prompt["title"], part=prompt["type"], minutes=prompt.get("minutes"),
                origin=prompt.get("origin", "ai"), source="Kaskade", skill=prompt["skill"],
                start={"to": f"/aufgabe/{prompt['id']}"})
    if prompt["skill"] == "sprechen":
        out.update(detail="Mikrofon / Headset", check="secure")
    else:
        out["detail"] = f"≈ {prompt.get('minutes', 20)} min, Tastatur" + ("" if ctx.ai else " · nur Selbstcheck, keine KI-Bewertung")
    return out


def _practice(m: dict, ctx: Ctx) -> dict:
    from . import practice
    module = "hoeren" if m["practice"].startswith("h") else "lesen"
    item = practice.get(module, m["practice"])
    label = {"lesen": "Prüfungstraining Lesen", "hoeren": "Prüfungstraining Hören"}.get(module, "Prüfungstraining")
    return _base("pruefung", "practice", title=item["title"] if item else m["practice"], part=label,
                 minutes=(item or {}).get("minutes"), origin=(item or {}).get("origin", "ai"), source="Kaskade",
                 start={"to": f"/pruefung/{module}/{m['practice']}"} if item else None,
                 detail="mit Zeit, wie in der Prüfung" + (" · Kopfhörer" if module == "hoeren" else ""))


def _mock(info: dict) -> dict:
    return _base("pruefung", "mock", title=info["mockExam"]["title"], detail="Mikrofon / Headset und Tastatur",
                 origin="ai", source="Kaskade", check="secure")


def _cards(ctx: Ctx, day: date) -> dict:
    if day == ctx.real_today:  # #25: the same "offen" as Karten — cards, over the whole day
        with db.tx() as conn:
            c = srs.counts(conn, ctx.now)
        part = f"{c['left']} offen" + (f" (davon {c['new']} neu)" if c["new"] else "")
    else:
        part = f"{ctx.due_cards(day)} fällig + {ctx.new_cards(day)} neu"
    return _base("karten", "cards", title="Fällige Karten und geminte Sätze", part=part,
                 origin=None, start={"to": "/karten"}, detail="in Kaskade" if day == ctx.today else "Stand heute")


BUILDERS = {"clip": _clip, "satzcheck": _satzcheck}


def first_days(start: date, data: dict, pauses=()) -> dict[str, date]:
    """The first plan date each book is read on (for "Kaufen bis"), after the weeks off (#36)."""
    out: dict[str, date] = {}
    for wi, w in enumerate(data["weeks"]):
        for di, d in enumerate(w["days"]):
            for m in d.get("materials", []):
                if m["kind"] == "book":
                    when = plan.slot_date(start, wi, di, pauses)
                    out[m["book"]] = min(out.get(m["book"], when), when)
    return out


def _item(m: dict, b: dict, ctx: Ctx, day: date, d: dict, data: dict, start: date, books: dict) -> dict:
    """One exact item for one material of a block."""
    if rolling.rolls(m) and b["id"] in rolling.FILM:
        item = _rolled(m, ctx, day, data, start)
    elif m["kind"] in BUILDERS:
        item = BUILDERS[m["kind"]](m, ctx, day)
    elif m["kind"] in ("youtube", "netflix"):
        item = _external(m, ctx, m["kind"])
    elif m["kind"] == "news":
        item = _news(m, ctx, day)
    elif m["kind"] == "text":
        item = _text(m, ctx)
    elif m["kind"] == "book":
        item = _book(m, ctx, books.get(m["book"]), day, m.get("desc") or d.get(b["id"], ""), data, start)
    elif m["kind"] == "lesetest":
        item = _lesetest(m, ctx)
    elif m["kind"] == "practice":
        item = _practice(m, ctx)
    else:
        item = _base(b["id"], m["kind"], title=m.get("title", ""), origin=None)
    if m.get("desc") and not item.get("text"):
        item["text"] = m["desc"]
    item["block"] = b["id"]
    return item


def _leicht(m: dict) -> bool:
    return m["kind"] == "news" and m.get("feed") == "leicht"


def block_items(mats: list[dict], b: dict, build) -> list[dict]:
    """The block's items in order. In the lesen block nachrichtenleicht takes up what the other
    items leave of the block (#27) — e.g. when a podcast's last part is only a few minutes."""
    items: dict[int, dict] = {i: build(m) for i, m in enumerate(mats) if not (b["kind"] == "lesen" and _leicht(m))}
    if b["kind"] == "lesen":
        rest = b["minutes"] - sum(it.get("minutes") or mats[i].get("minutes") or 0 for i, it in items.items())
        news = [i for i, m in enumerate(mats) if _leicht(m)]
        planned = sum(mats[i].get("minutes", 0) for i in news)
        for i in news:
            items[i] = build({**mats[i], "minutes": max(mats[i].get("minutes", 0), round(mats[i].get("minutes", 0) * rest / planned) if planned else 0)})
        if not news and rest > 5 and items:  # a short audio day: fill up with nachrichtenleicht
            items[len(mats)] = build({"block": b["id"], "kind": "news", "feed": "leicht", "minutes": rest})
    return [items[i] for i in sorted(items)]


def day_items(info: dict, ctx: Ctx, data: dict, start: date) -> list[dict]:
    """The exact items of each block of the plan day in `info` (empty on days without a block):
    one item per block; a second (or third) one of the lesen block hangs on the first as "then"."""
    d = info.get("day")
    if not d:
        return []
    day = date.fromisoformat(info["date"])
    books = first_days(start, data, ctx.pauses)
    out = []
    for b in data["block"]:
        if b["kind"] == "pause":
            continue
        mats = [m for m in d.get("materials", []) if m["block"] == b["id"]]
        if b["kind"] == "karten":
            items = [_cards(ctx, day)]
        elif b["kind"] == "pruefung":  # older plans only (#27: no exam block in the daily plan)
            m = mats[0] if mats else None
            items = [_mock(info) if info.get("mockExam") else _exam(info["exam"], ctx) if info.get("exam") else
                     _lesetest(m, ctx) if m and m["kind"] == "lesetest" else
                     _practice(m, ctx) if m else _base("pruefung", "none", title="Kein Prüfungsteil", origin=None)]
        elif not mats:
            items = [_base(b["id"], "none", title="Noch nichts eingeplant", status="todo", origin=None)]
        else:
            items = block_items(mats, b, lambda m: _item(m, b, ctx, day, d, data, start, books))
        for it in items:
            it["block"] = b["id"]
        first = items[0]
        first["then"] = items[1:]
        out.append(first)
    return out


def flat(items: list[dict]) -> list[dict]:
    """Every item of a day, the "then" ones included."""
    return [x for it in items for x in [it, *it.get("then", [])]]


def next_plan_day(start: date, today: date, data: dict, pauses=()) -> tuple[date, str]:
    """Tomorrow if it has a block, else the next day that does ("next") — after a week off, too."""
    d = today + timedelta(days=1)
    for _ in range(400):
        if plan.plan_day(start, d, data, pauses)["day"]:
            return d, "tomorrow" if d == today + timedelta(days=1) else "next"
        d += timedelta(days=1)
    return d, "next"


def notices(start: date, today: date, data: dict, ctx: Ctx) -> list[dict]:
    """Dated to-dos ahead of the plan ("Bald fällig"): buy a book, install Language Reactor.
    `by` is the due date (paper a week ahead; `byEbook` two days ahead), sorted by it."""
    week = lambda d: plan.plan_index(start, d, ctx.pauses)[0] + 1  # noqa: E731
    out = []
    for book_id, first in sorted(first_days(start, data, ctx.pauses).items(), key=lambda kv: kv[1]):
        b = stock.book(book_id)
        if not b or book_id in ctx.bought or first < today and ratings.book_mode(book_id, today, start, data, ctx.pauses)["mode"] != "spaeter":
            continue
        # #24: at 20–40 % the book waits for the next pass through the plan — and so does buying it
        mode = ratings.book_mode(book_id, max(first, today + timedelta(days=1)), start, data, ctx.pauses)
        if mode["mode"] == "spaeter":
            first = date.fromisoformat(mode["back"])
        item = {"type": "book", "id": book_id, "by": stock.notice(first, b.get("format", "paper")).isoformat(),
                "firstDay": first.isoformat(), "week": week(first), "title": f"{b['author']}: {b['title']}", "book": b,
                "mode": mode if mode["mode"] == "spaeter" else None}
        if b.get("ebook") and b.get("format", "paper") == "paper":  # a paper book whose ebook would do too
            item["byEbook"] = stock.notice(first, "ebook").isoformat()
        out.append(item)
    kinds_used: dict[str, date] = {}
    for wi, w in enumerate(data["weeks"]):
        for di, d in enumerate(w["days"]):
            for m in d.get("materials", []):
                when = plan.slot_date(start, wi, di, ctx.pauses)
                if when >= today:
                    kinds_used[m["kind"]] = min(kinds_used.get(m["kind"], when), when)
    for s in stock.catalog().get("setup", []):
        kinds = [k for k in ([s["forKind"]] if isinstance(s["forKind"], str) else s["forKind"]) if k in kinds_used]
        if s["id"] in ctx.setup_done or not kinds:
            continue
        first = min(kinds_used[k] for k in kinds)
        out.append({"type": "setup", "id": s["id"], "by": (first - timedelta(days=s.get("noticeDays", 2))).isoformat(),
                    "firstDay": first.isoformat(), "week": week(first), "title": s["title"], "text": s.get("text"), "url": s.get("url")})
    return sorted(out, key=lambda n: n["by"])


# ── Materialcheck ────────────────────────────────────────────────────────────

def read_check() -> dict:
    p = config.DATA_DIR / CHECK_FILE
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def link_ok(url: str) -> bool:
    if offline():
        return True
    try:
        req = urllib.request.Request(url, headers={**stock.UA, "User-Agent": "Mozilla/5.0 Firefox/131.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status < 400
    except Exception:
        return False


def feed_ok(feed: str) -> bool:
    """The feed answers and still lists articles (nachrichtenleicht is read from its homepage)."""
    if offline():
        return True
    try:
        return bool(parse_feed(feed, fetch_feed(NEWS_FEEDS[feed][1])))
    except Exception:
        return False


def check(today: date, start: date, data: dict, days: int = 7, links: bool = True) -> dict:
    """Every item of the next `days` plan days: in the library and playable, links answering."""
    ctx = Ctx(today)
    if links:
        ctx.links = {}
    gaps, urls = [], {}
    for i in range(days):
        day = today + timedelta(days=i)
        info = plan.plan_day(start, day, data, ctx.pauses)
        for it in flat(day_items(info, ctx, data, start)):
            href = (it.get("start") or {}).get("href")
            if links and href and href not in urls:
                urls[href] = link_ok(href)
                if not urls[href]:
                    it.update(status="todo", detail="Link antwortet nicht")
            if it["status"] == "todo" and it["kind"] != "book":
                gaps.append({"date": day.isoformat(), "block": it["block"], "title": it["title"], "problem": it["detail"]})
    feeds = {m["feed"] for w in data["weeks"] for d in w["days"] for m in d.get("materials", []) if m["kind"] == "news"}
    for feed in sorted(feeds | {"leicht"}):  # nachrichtenleicht also stands in for a book at 20–40 % (#24)
        url = NEWS_FEEDS[feed][1]
        if links and url not in urls:
            urls[url] = feed_ok(feed)
            if not urls[url]:
                gaps.append({"date": today.isoformat(), "block": "lesen", "title": NEWS_FEEDS[feed][0],
                             "problem": "Feed antwortet nicht — oder keine Artikel darin gefunden"})
    return {"checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "days": days, "gaps": gaps, "links": urls}


def write_check(today: date) -> dict:
    from .routes.today import plan_start
    from . import transcripts
    data = plan.plan(db.get_setting("phase"))
    start = plan_start(today)
    imported = transcripts.import_all()  # #29: new transcripts from the Mac become "gesprochen" tracks
    result = check(today, start, data)
    # planned clips without a transcript: for PROGRESS.md (the Mac makes them), not a gap on Heute
    result["transcripts"] = {**imported, "missing": transcripts.missing(today, start, data)}
    result["themes"] = themes.scan()  # #33: also for the operator — a crime clip that needs a look before it's planned
    (config.DATA_DIR / CHECK_FILE).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"gaps": result["gaps"], "checkedAt": result["checkedAt"], "transcripts": result["transcripts"],
            "themes": result["themes"]}
