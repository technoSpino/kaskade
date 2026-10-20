"""#22 nachrichtenleicht, #23 "Wie viel hast du verstanden?" + Schauen's "zu schwer", #24 book modes."""
import html
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from kaskade import db, materials, ratings, srs

from .test_api_materials import add_clip, at, b2, by_block  # noqa: F401  (fixture)

TUESDAY_LATE = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)      # Tue 12:00 Berlin, after the block
FRIDAY_TEST = datetime(2026, 10, 16, 9, 40, tzinfo=timezone.utc)       # Fri 11:40 Berlin, after the Lesetest
MONDAY_19 = datetime(2026, 10, 19, 7, 30, tzinfo=timezone.utc)         # Mo 19.10. 09:30 Berlin, week 2
LESETEST = "https://www.bic-media.com/books/content/shortened/9783442770663.pdf#page=9"


def teaser(path, title, when, kind="article"):
    """One teaser as nachrichtenleicht.de embeds it in its homepage (original test data)."""
    value = {"__typename": "Teaser", "contentType": kind, "path": path, "title": title, "date": when}
    return f'<script class="js-client-queries" data-json="{html.escape(json.dumps({"key": "k", "value": value}))}"></script>'


LEICHT = ("<html><body>"
          + teaser("https://www.nachrichtenleicht.de/", "Nachrichten in Einfacher Sprache", None, kind=None)
          + "".join(teaser(f"https://www.nachrichtenleicht.de/meldung-{i}-100.html", f"Meldung {i}",
                           f"2026-10-{10 + i // 3:02d}T{8 + i % 3:02d}:00:00.000+02:00") for i in range(9))
          + teaser("https://www.nachrichtenleicht.de/impressum-102.html", "Impressum", "2020-02-11T11:52:00.000+01:00", kind="text")
          + "</body></html>").encode()


def seed_tagesschau():
    """Tuesday's three tagesschau Inland links, as Kaskade picked them that morning."""
    items = [{"title": f"Inland {i}", "url": f"https://www.tagesschau.de/inland/a-{i}.html", "published": None} for i in range(3)]
    with db.tx() as conn:
        conn.execute("INSERT INTO news_picks(local_date, feed, items) VALUES (?, ?, ?)", ("2026-10-13", "inland", json.dumps(items)))


# ── #22 nachrichtenleicht ────────────────────────────────────────────────────

def test_leicht_articles_from_the_homepage_newest_first_never_twice(b2, monkeypatch):
    picked = materials.pick_leicht(LEICHT)
    assert [a["title"] for a in picked] == ["Meldung 8", "Meldung 7", "Meldung 6", "Meldung 5", "Meldung 4"]
    assert all(a["url"].startswith("https://www.nachrichtenleicht.de/meldung-") for a in picked)
    monkeypatch.setattr(materials, "fetch_feed", lambda url: LEICHT)
    monkeypatch.delenv("KASKADE_OFFLINE")
    mon, tue = date(2026, 10, 19), date(2026, 10, 20)
    first = materials.news_for(mon, "leicht", mon, 5)
    second = materials.news_for(tue, "leicht", tue, 5)
    assert [a["title"] for a in second] == ["Meldung 3", "Meldung 2", "Meldung 1", "Meldung 0"]  # no repeats
    assert not {a["url"] for a in first} & {a["url"] for a in second}


def test_leicht_item_text_and_count_follow_his_ratings(b2, monkeypatch):
    at(monkeypatch, datetime(2026, 11, 3, 7, 0, tzinfo=timezone.utc))      # W4 Di: nachrichtenleicht
    lesen = b2.get("/api/today").json()["assignments"]["lesen"]
    assert lesen["kind"] == "news" and lesen["feed"] == "leicht" and lesen["source"] == "nachrichtenleicht.de"
    # 30 of the 60 minutes (#27): 4 articles at 5 per 35 min; then a podcast
    assert lesen["title"] == "nachrichtenleicht.de: die 4 neuesten Artikel" and lesen["minutes"] == 30
    assert lesen["text"].startswith("nachrichtenleicht.de (Deutschlandfunk, Nachrichten in Einfacher Sprache): die vier neuesten")
    assert lesen["then"][0]["kind"] == "clip" and lesen["then"][0]["audio"]  # rolls: the first podcast not yet heard
    ratings.save(date(2026, 11, 2), "lesen", {"item": "news:leicht:2026-11-02", "kind": "news", "label": "x", "book": None}, 100)
    assert ratings.leicht_count() == 7 and ratings.leicht_count(30) == 6
    ratings.save(date(2026, 11, 2), "lesen", {"item": "news:leicht:2026-11-02", "kind": "news", "label": "x", "book": None}, 40)
    assert ratings.leicht_count() == 4 and ratings.leicht_count(30) == 3
    assert b2.get("/api/today").json()["assignments"]["lesen"]["title"] == "nachrichtenleicht.de: die 3 neuesten Artikel"


def test_materialcheck_covers_nachrichtenleicht(b2, monkeypatch):
    monkeypatch.delenv("KASKADE_OFFLINE")
    monkeypatch.setattr(materials, "link_ok", lambda url: True)
    monkeypatch.setattr(materials, "fetch_feed", lambda url: b"<html>neu gebaut, keine Teaser</html>")
    from kaskade import plan
    gaps = materials.check(date(2026, 10, 13), date(2026, 10, 12), plan.plan("2B"), days=1)["gaps"]
    assert any(g["title"] == "nachrichtenleicht.de" for g in gaps)
    monkeypatch.setattr(materials, "fetch_feed", lambda url: LEICHT)
    gaps = materials.check(date(2026, 10, 13), date(2026, 10, 12), plan.plan("2B"), days=1)["gaps"]
    assert not any(g["title"] == "nachrichtenleicht.de" for g in gaps)


# ── #23 ratings ──────────────────────────────────────────────────────────────

def test_seed_tuesday_tagesschau_20_percent_and_read_it_back(b2, monkeypatch):
    """The first data point: Di 13.10., lesen, tagesschau Inland × 3 → 20 %."""
    at(monkeypatch, TUESDAY_LATE)
    seed_tagesschau()
    r = b2.post("/api/ratings", json={"date": "2026-10-13", "block": "lesen", "pct": 20}).json()
    assert (r["date"], r["block"], r["item"], r["kind"], r["pct"]) == ("2026-10-13", "lesen", "news:inland:2026-10-13", "news", 20)
    assert r["label"] == "tagesschau.de · Inland: 3 Artikel" and len(r["detail"]["links"]) == 3
    got = b2.get("/api/ratings").json()
    assert [x["label"] for x in got["ratings"]] == ["tagesschau.de · Inland: 3 Artikel"]
    hard = got["tooHard"][0]
    assert hard["pct"] == 20 and hard["action"].startswith("tagesschau.de ist aus dem Plan")
    t = b2.get("/api/today").json()
    assert t["tooHard"][0]["label"] == "tagesschau.de · Inland: 3 Artikel"
    assert t["assignments"]["lesen"]["rating"]["pct"] == 20 and not t["assignments"]["lesen"]["ask"]
    # rating again replaces, never duplicates
    b2.post("/api/ratings", json={"date": "2026-10-13", "block": "lesen", "pct": 40})
    assert [x["pct"] for x in b2.get("/api/ratings").json()["ratings"]] == [40]


def test_heute_asks_after_the_block_once(b2, monkeypatch):
    at(monkeypatch, datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc))  # Wed 10:00
    add_clip("egp-698", seconds=1915.0)
    t = b2.get("/api/today").json()["assignments"]
    assert t["lesen"]["rating"] is None and not t["lesen"]["ask"] and "ask" not in t["karten"]
    b2.post("/api/activity/start", json={"block": "lesen"})
    assert not b2.get("/api/today").json()["assignments"]["lesen"]["ask"]   # in the middle of it: not yet
    b2.post("/api/activity/stop")
    lesen = b2.get("/api/today").json()["assignments"]["lesen"]
    assert lesen["ask"] and lesen["rateLabel"].startswith("Easy German Podcast 698")
    r = b2.post("/api/ratings", json={"block": "lesen", "pct": None}).json()  # skipped: stored, not asked again
    assert r["skipped"] and not b2.get("/api/today").json()["assignments"]["lesen"]["ask"]
    assert b2.post("/api/ratings", json={"block": "lesen", "pct": 55}).status_code == 422
    assert b2.post("/api/ratings", json={"block": "karten", "pct": 60}).status_code == 422
    assert b2.post("/api/ratings", json={"block": "lesen", "pct": 60, "date": "2026-10-15"}).status_code == 422


def test_ratings_today_lists_the_clip_for_schauen(b2, monkeypatch):
    at(monkeypatch, datetime(2026, 10, 14, 7, 0, tzinfo=timezone.utc))
    mid = add_clip("tatort-schweigen")
    rows = {r["block"]: r for r in b2.get("/api/ratings/today").json()}
    assert rows["input"]["mediaId"] == mid and rows["input"]["kind"] == "clip" and rows["input"]["rating"] is None
    assert rows["input"]["item"].startswith("clip:tatort-schweigen:")


def test_zu_schwer_lines_and_the_measured_share(b2, monkeypatch):
    at(monkeypatch, datetime(2026, 10, 14, 7, 0, tzinfo=timezone.utc))
    mid = add_clip("tatort-schweigen")
    b2.get("/api/today")  # today's range is fixed: from 0:00
    cues = [{"start": 10.0 * i, "end": 10.0 * i + 3, "text": f"Zeile {i}"} for i in range(1, 11)] + [{"start": 111, "end": 112, "text": "(Musik)"}]
    with db.tx() as conn:
        conn.execute("UPDATE media SET cues = ? WHERE id = ?", (json.dumps(cues), mid))
    for i in (2, 5, 5):  # the same line twice counts once
        r = b2.post(f"/api/media/{mid}/hard", json={"start": 10.0 * i, "end": 10.0 * i + 3, "text": f"Zeile {i}"})
    assert [m["text"] for m in r.json()["marks"]] == ["Zeile 2", "Zeile 5", "Zeile 5"]
    assert b2.post("/api/media/999/hard", json={"start": 1, "text": "x"}).status_code == 404
    assert ratings.hard_share(cues[:10], 0, 80, [20, 50, 50]) == {"marked": 2, "lines": 7, "pct": 29}
    b2.put(f"/api/media/{mid}/progress", json={"position": 80})
    b2.post("/api/plan/done", json={"block": "input", "done": True})
    inp = b2.get("/api/today").json()["assignments"]["input"]
    assert inp["ask"] and inp["share"] == {"marked": 2, "lines": 7, "pct": 29}
    r = b2.post("/api/ratings", json={"block": "input", "pct": 60}).json()
    assert (r["hard"], r["lines"], r["kind"]) == (2, 7, "clip")


# ── #24 Schirach: the Lesetest decides how the book is read ──────────────────

def lesetest(b2, monkeypatch, pct):
    """Friday's lesen block: Radio Tatort, then the Lesetest (#27) — rated on its own."""
    at(monkeypatch, FRIDAY_TEST)
    t = b2.get("/api/today").json()["assignments"]["lesen"]["then"][0]
    assert t["kind"] == "lesetest" and t["start"]["href"] == LESETEST and t["rateItem"] == "lesetest:schirach-verbrechen"
    if pct is not None:
        r = b2.post("/api/ratings", json={"block": "lesen", "item": t["rateItem"], "pct": pct}).json()
        assert (r["item"], r["book"], r["kind"]) == ("lesetest:schirach-verbrechen", "schirach-verbrechen", "lesetest")
    at(monkeypatch, MONDAY_19)
    return b2.get("/api/today").json()


def test_lesetest_100_reads_freely(b2, monkeypatch):
    t = lesetest(b2, monkeypatch, 100)
    lesen = t["assignments"]["lesen"]
    assert lesen["kind"] == "book" and lesen["part"] == "S. 7–42: „Fähner“ und „Tanatas Teeschale“"
    assert lesen["then"][0]["kind"] == "clip"  # #27: audio after the book, the pages stay as they are
    assert lesen["text"].endswith("Frei lesen: kein Wörterbuch, nicht zurückblättern — wenn du den Fall grob verstehst, ist alles gut.")
    assert lesen["mode"]["why"] == "Schirach: 100 % im Lesetest → frei lesen, kein Wörterbuch"
    assert t["bookModes"][0]["mode"] == "frei"


def test_lesetest_60_looks_up_three_words_a_page(b2, monkeypatch):
    t = lesetest(b2, monkeypatch, 60)
    lesen = t["assignments"]["lesen"]
    assert lesen["kind"] == "book" and lesen["part"].startswith("S. 7–42")
    assert lesen["text"].endswith("Bis zu 3 Wörter pro Seite nachschlagen — nur Wörter, die immer wieder vorkommen.")
    assert "Frei lesen" not in lesen["text"] and "3 Wörter pro Seite" in lesen["detail"]
    assert lesen["mode"]["why"] == "Schirach: 60 % im Lesetest → bis zu 3 Wörter pro Seite nachschlagen"
    # his rating of Monday's reading sets Tuesday
    b2.post("/api/ratings", json={"block": "lesen", "pct": 80})
    at(monkeypatch, MONDAY_19 + timedelta(days=1))
    tue = b2.get("/api/today").json()["assignments"]["lesen"]
    assert tue["mode"]["why"] == "Schirach: 80 % am 19.10. → frei lesen, kein Wörterbuch" and "Frei lesen:" in tue["text"]


def test_lesetest_40_moves_the_book_and_reads_nachrichtenleicht(b2, monkeypatch):
    t = lesetest(b2, monkeypatch, 40)
    lesen = t["assignments"]["lesen"]
    assert lesen["kind"] == "news" and lesen["feed"] == "leicht"
    assert lesen["text"].startswith("Statt Schirach: nachrichtenleicht.de")
    assert lesen["mode"]["why"] == ("Schirach: 40 % im Lesetest → kommt nach Woche 4 wieder (neuer Lesetest Fr 13.11.), "
                                    "bis dahin nachrichtenleicht")
    # every Schirach day of weeks 2–3 is nachrichtenleicht now
    for iso in ("2026-10-21", "2026-10-27", "2026-10-28"):
        it = by_block(b2.get("/api/materials", params={"today": iso}).json()["today"])["lesen"]
        assert it["kind"] == "news" and it["feed"] == "leicht", iso
    # "Bald fällig" moves with the book: first day in the next pass (week 6), buy a week ahead
    v = next(n for n in b2.get("/api/materials").json()["notices"] if n["id"] == "schirach-verbrechen")
    assert (v["firstDay"], v["by"], v["week"]) == ("2026-11-16", "2026-11-09", 6) and v["mode"]["mode"] == "spaeter"
    assert t["tooHard"][0]["action"].startswith("Schirach: 40 % im Lesetest → kommt nach Woche 4 wieder")


def test_no_lesetest_by_monday_9_reads_as_60(b2, monkeypatch):
    t = lesetest(b2, monkeypatch, None)
    lesen = t["assignments"]["lesen"]
    assert lesen["kind"] == "book" and lesen["text"].endswith("nur Wörter, die immer wieder vorkommen.")
    assert lesen["mode"]["assumed"] and lesen["mode"]["why"] == (
        "Schirach: kein Lesetest bis Mo 19.10. 09:00 → wie 60 % → bis zu 3 Wörter pro Seite nachschlagen")


def test_before_the_lesetest_it_decides(b2, monkeypatch):
    at(monkeypatch, TUESDAY_LATE)
    mon = by_block(b2.get("/api/materials", params={"today": "2026-10-19"}).json()["today"])["lesen"]
    assert mon["kind"] == "book" and "Frei lesen:" in mon["text"]
    assert mon["mode"]["why"] == "Schirach: der Lesetest am Fr 16.10. entscheidet, wie du ab Mo 19.10. liest"
    assert b2.get("/api/ratings").json()["books"][0]["why"].startswith("Schirach: der Lesetest am Fr 16.10.")


def test_a_rating_after_9_counts_from_the_next_day(b2, monkeypatch):
    lesetest(b2, monkeypatch, 60)
    at(monkeypatch, MONDAY_19 + timedelta(hours=2))  # 11:30, after Monday's reading
    b2.post("/api/ratings", json={"block": "lesen", "pct": 40})
    assert b2.get("/api/today").json()["assignments"]["lesen"]["kind"] == "book"  # today stays as it was
    tue = by_block(b2.get("/api/materials").json()["next"])["lesen"]
    assert tue["kind"] == "news" and tue["mode"]["why"].startswith("Schirach: 40 % am 19.10. → kommt nach Woche 4 wieder")


@pytest.mark.parametrize("pct,mode", [(100, "frei"), (80, "frei"), (60, "nachschlagen"), (40, "spaeter"), (20, "spaeter")])
def test_mode_rule(b2, monkeypatch, pct, mode):
    lesetest(b2, monkeypatch, pct)
    from kaskade import plan
    assert ratings.book_mode("schirach-verbrechen", date(2026, 10, 19), date(2026, 10, 12), plan.plan("2B"))["mode"] == mode
