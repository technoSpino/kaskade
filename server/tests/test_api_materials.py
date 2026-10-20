"""#16: exact assignments per block, Material für heute und morgen, notices, stock, Materialcheck."""
import json
from datetime import date, datetime, timezone

import pytest

from kaskade import config, db, materials, plan, srs, stock

SUNDAY = datetime(2026, 10, 11, 17, 0, tzinfo=timezone.utc)   # Sun 19:00 Berlin, day before the start
MONDAY = datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)    # Mon 09:00 Berlin, week 1


@pytest.fixture()
def b2(client, monkeypatch):
    """Matt's setup: phase 2B, plan starts Mon 12 Oct; offline (no news, no link checks)."""
    monkeypatch.setenv("KASKADE_OFFLINE", "1")
    db.set_setting("phase", "2B")
    db.set_setting("planStart", "2026-10-12")
    return client


def at(monkeypatch, when):
    monkeypatch.setattr(srs, "now_utc", lambda: when)


def add_clip(key, seconds=5361.0, status="ready", file=True):
    name = f"stock-{key}.mp4"
    if file:
        config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        (config.MEDIA_DIR / name).write_bytes(b"x")
    cues = [{"start": 1.0, "end": seconds, "text": "Wo waren Sie gestern Abend?"}]
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO media(created_at, kind, title, media_file, cues, key, tag, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (db.now_iso(), "mediathek", key, name, json.dumps(cues), key, "krimi", status))
        return cur.lastrowid


def by_block(group):
    return {it["block"]: it for it in group["items"]}


def test_sunday_shows_monday_with_tatort_ready(b2, monkeypatch):
    at(monkeypatch, SUNDAY)
    mid = add_clip("tatort-schweigen")
    m = b2.get("/api/materials").json()
    assert m["today"]["date"] == "2026-10-11" and not m["today"]["planDay"] and m["today"]["items"] == []
    assert m["next"]["date"] == "2026-10-12" and m["next"]["kind"] == "tomorrow" and m["next"]["planDay"]
    items = by_block(m["next"])
    assert list(items) == ["karten", "input", "lesen"]  # #27: no Prüfungsteil
    tatort = items["input"]
    # #21: 89:21 of film at ≈ 25 min a block → four even days from the start
    assert tatort["title"] == "Tatort: Schweigen" and tatort["part"] == "0:00–22:20" and tatort["minutes"] == 22
    assert tatort["status"] == "ready" and tatort["source"] == "ARD Mediathek · NDR" and tatort["origin"] == "real"
    assert tatort["start"] == {"to": f"/schauen/{mid}?von=0&bis=1340"}
    # the podcast isn't in this library yet → a real gap, said plainly
    assert items["lesen"]["status"] == "todo" and "Bibliothek" in items["lesen"]["detail"]
    # #27: then nachrichtenleicht for the rest of the 60-min block
    then = items["lesen"]["then"]
    assert [x["kind"] for x in then] == ["news"] and then[0]["feed"] == "leicht" and then[0]["minutes"] == 30
    assert m["httpsUrl"] == config.HTTPS_URL


def test_monday_today_and_tuesday_with_microphone(b2, monkeypatch):
    at(monkeypatch, MONDAY)
    add_clip("tatort-schweigen")
    m = b2.get("/api/materials").json()
    assert m["today"]["date"] == "2026-10-12" and m["next"]["date"] == "2026-10-13" and m["next"]["kind"] == "tomorrow"
    tue = by_block(m["next"])
    assert "pruefung" not in tue and not any(it.get("check") == "secure" for it in m["next"]["items"])  # #27: no mic line
    assert tue["input"]["part"] == "22:20–44:40"   # #21: from where today's part ends
    # tomorrow's news: the links appear on the morning itself
    assert tue["lesen"]["kind"] == "news" and tue["lesen"]["links"] == [] and "am Morgen" in tue["lesen"]["detail"]


def test_friday_next_plan_day_is_monday(b2, monkeypatch):
    at(monkeypatch, datetime(2026, 10, 16, 7, 0, tzinfo=timezone.utc))
    m = b2.get("/api/materials").json()
    assert m["today"]["date"] == "2026-10-16" and m["today"]["planDay"]
    assert m["next"]["date"] == "2026-10-19" and m["next"]["kind"] == "next"
    # #21: nothing of week 1 watched → nothing skipped, the Tatort comes first
    assert by_block(m["next"])["input"]["title"] == "Tatort: Schweigen"
    for key in ("tatort-schweigen", "soko-leipzig-das-auge"):
        b2.put(f"/api/media/{add_clip(key)}/progress", json={"position": 5361})
    m = b2.get("/api/materials", params={"today": "2026-10-16"}).json()
    # … once week 1 is watched, week 2 follows; today's range was fixed this morning and stays
    assert by_block(m["today"])["input"]["title"] == "Tatort: Schweigen"
    assert by_block(m["next"])["input"]["title"].startswith("Merz gegen Merz, Folge 1")


def test_next_plan_day_rules():
    data = plan.plan("2B")
    start = date(2026, 10, 12)
    assert materials.next_plan_day(start, date(2026, 10, 10), data) == (date(2026, 10, 12), "next")      # Sat before
    assert materials.next_plan_day(start, date(2026, 10, 11), data) == (date(2026, 10, 12), "tomorrow")  # Sun
    assert materials.next_plan_day(start, date(2026, 10, 14), data) == (date(2026, 10, 15), "tomorrow")
    assert materials.next_plan_day(start, date(2026, 10, 17), data) == (date(2026, 10, 19), "next")      # Sat
    assert materials.next_plan_day(start, date(2026, 10, 7), data) == (date(2026, 10, 12), "next")       # before start


def test_preview_query_for_another_day_and_phase(b2, monkeypatch):
    at(monkeypatch, MONDAY)
    m = b2.get("/api/materials", params={"today": "2026-10-16", "phase": "2A"}).json()
    assert m["next"]["date"] == "2026-10-19"
    assert [it["kind"] for it in [by_block(m["today"])["lesen"], *by_block(m["today"])["lesen"]["then"]]] == ["text", "clip", "news"]
    assert b2.get("/api/materials", params={"phase": "9Z"}).status_code == 422


def test_clip_status_follows_the_library_and_his_position(b2, monkeypatch):
    at(monkeypatch, MONDAY)
    mid = add_clip("tatort-schweigen", status="converting")
    item = lambda: by_block(b2.get("/api/materials").json()["today"])["input"]  # Monday, fixed at 0:00–22:20
    assert item()["status"] == "todo" and "umgewandelt" in item()["detail"]
    with db.tx() as conn:
        conn.execute("UPDATE media SET status = 'ready' WHERE id = ?", (mid,))
    assert item()["status"] == "ready" and item()["detail"] == "in deiner Bibliothek"
    b2.put(f"/api/media/{mid}/progress", json={"position": 600})
    assert item()["detail"].endswith("weiter ab 10:00") and item()["part"] == "0:00–22:20"  # today's range stays
    b2.put(f"/api/media/{mid}/progress", json={"position": 1340})
    assert item()["detail"].endswith("Ziel schon erreicht ✓")


def test_missing_file_is_a_gap(b2, monkeypatch):
    at(monkeypatch, MONDAY)
    add_clip("tatort-schweigen", file=False)
    it = by_block(b2.get("/api/materials").json()["today"])["input"]
    assert it["status"] == "todo"


FEED = b"""<?xml version="1.0"?><rss><channel>
<item><title>Liveblog: Alles zum Gipfel</title><link>https://www.tagesschau.de/ausland/liveblog-gipfel-100.html</link><pubDate>Mon, 12 Oct 2026 06:50:00 +0200</pubDate></item>
<item><title>Bahn erh\xc3\xb6ht Preise</title><link>https://www.tagesschau.de/wirtschaft/bahn-preise-100.html</link><pubDate>Mon, 12 Oct 2026 06:40:00 +0200</pubDate></item>
<item><title>Neue Regeln f\xc3\xbcr Mieter</title><link>https://www.tagesschau.de/inland/mieter-100.html</link><pubDate>Mon, 12 Oct 2026 06:10:00 +0200</pubDate></item>
<item><title>Video: Sturm im Norden</title><link>https://www.tagesschau.de/multimedia/video/sturm-100.html</link><pubDate>Mon, 12 Oct 2026 05:00:00 +0200</pubDate></item>
<item><title>Streik an Flugh\xc3\xa4fen</title><link>https://www.tagesschau.de/inland/streik-100.html</link><pubDate>Mon, 12 Oct 2026 05:30:00 +0200</pubDate></item>
<item><title>Herbstferien beginnen</title><link>https://www.tagesschau.de/inland/ferien-100.html</link><pubDate>Sun, 11 Oct 2026 20:00:00 +0200</pubDate></item>
</channel></rss>"""


def test_news_picks_three_articles_once_per_day(b2, monkeypatch):
    picked = materials.pick_articles(FEED)
    assert [a["title"] for a in picked] == ["Bahn erhöht Preise", "Neue Regeln für Mieter", "Streik an Flughäfen"]
    calls = []
    monkeypatch.setattr(materials, "fetch_feed", lambda url: calls.append(url) or FEED)
    day = date(2026, 10, 13)
    assert materials.news_for(date(2026, 10, 14), "inland", day) is None           # tomorrow: not yet
    first = materials.news_for(day, "inland", day)
    assert len(first) == 3 and materials.news_for(day, "inland", day) == first     # fixed for the day
    assert len(calls) == 1


def test_assignments_on_heute_open_exactly_that(b2, monkeypatch):
    at(monkeypatch, MONDAY)
    mid = add_clip("tatort-schweigen")
    t = b2.get("/api/today").json()
    assert t["assignments"]["input"]["start"]["to"] == f"/schauen/{mid}?von=0&bis=1340"
    assert "pruefung" not in t["assignments"]
    assert t["assignments"]["karten"]["start"]["to"] == "/karten"
    assert t["httpsUrl"] == config.HTTPS_URL
    # weekend: the preview day's assignments (Tatort not finished → it continues on Monday, #21)
    at(monkeypatch, datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc))
    assert b2.get("/api/today").json()["assignments"]["input"]["title"] == "Tatort: Schweigen"


def test_youtube_opens_in_language_reactor(b2, monkeypatch):
    at(monkeypatch, MONDAY)
    fri = by_block(b2.get("/api/materials", params={"today": "2026-10-23"}).json()["today"])   # week 2 Fri
    yt = fri["input"]
    assert yt["kind"] == "youtube" and yt["part"] == "0:00–14:30"
    assert yt["start"] == {"href": "https://www.youtube.com/watch?v=ERHUpp091Kw&t=0s", "note": "in Chrome mit Language Reactor"}


def test_netflix_opens_the_title_page(b2, monkeypatch):
    at(monkeypatch, MONDAY)
    wed = by_block(b2.get("/api/materials", params={"today": "2026-10-21"}).json()["today"])
    nf = wed["input"]
    assert nf["kind"] == "netflix" and nf["part"] == "Staffel 1, Folge 1 „It's the Economy, Stupid“, 0:00–24:00"
    assert nf["start"]["href"] == "https://www.netflix.com/de/title/81389612"


def test_notices_language_reactor_until_ticked(b2, monkeypatch):
    at(monkeypatch, SUNDAY)
    n = b2.get("/api/materials").json()["notices"]
    lr = next(x for x in n if x["id"] == "language-reactor")
    assert lr["firstDay"] == "2026-10-21" and lr["by"] == "2026-10-19"   # Netflix on Wed of week 2
    assert b2.post("/api/setup/language-reactor", json={"done": True}).status_code == 200
    assert not any(x["id"] == "language-reactor" for x in b2.get("/api/materials").json()["notices"])
    assert b2.post("/api/setup/nope", json={}).status_code == 404
    assert any(x["id"] == "language-reactor" for x in b2.get("/api/fahrplan").json()["notices"]) is False


def test_book_notice_a_week_ahead(b2, monkeypatch):
    book = {"id": "verbrechen", "author": "Ferdinand von Schirach", "title": "Verbrechen", "format": "paper",
            "isbn": "978-3-442-74222-3", "shops": [{"name": "Thalia", "url": "https://www.thalia.de/"}]}
    cat = {**stock.catalog(), "books": [book]}
    monkeypatch.setattr(stock, "catalog", lambda: cat)
    data = json.loads(json.dumps(plan.plan("2B")))
    data["weeks"][1]["days"][0]["materials"][1] = {"block": "lesen", "kind": "book", "book": "verbrechen", "part": "S. 7–40: Fähner"}
    ctx = materials.Ctx(date(2026, 10, 11))
    n = materials.notices(date(2026, 10, 12), date(2026, 10, 11), data, ctx)
    v = next(x for x in n if x["id"] == "verbrechen")
    assert v["firstDay"] == "2026-10-19" and v["by"] == "2026-10-12"            # paper: a week ahead
    assert stock.notice(date(2026, 10, 19), "ebook") == date(2026, 10, 17)        # ebook: two days
    book_day = (date(2026, 10, 19), "", data, date(2026, 10, 12))
    item = materials._book(data["weeks"][1]["days"][0]["materials"][1], ctx, date(2026, 10, 19), *book_day)
    assert item["status"] == "todo" and item["detail"] == "Kaufen bis 12.10."
    assert b2.post("/api/books/verbrechen/bought", json={"done": True}).json()["bought"]
    assert materials._book(data["weeks"][1]["days"][0]["materials"][1], materials.Ctx(date(2026, 10, 11)), None, *book_day)["status"] == "ready"


def test_clip_tags_guessed_and_editable(b2):
    assert stock.guess_tag("Tatort: Schweigen") == "krimi"
    assert stock.guess_tag("Merz gegen Merz, Folge 1") == "comedy"
    assert stock.guess_tag("Urlaubsvideo") is None
    mid = add_clip("x-clip")
    assert b2.patch(f"/api/media/{mid}", json={"tag": "doku"}).json()["tag"] == "doku"
    assert b2.patch(f"/api/media/{mid}", json={"tag": "quatsch"}).status_code == 422
    assert {t["id"] for t in b2.get("/api/media/tags").json()} >= {"krimi", "comedy", "doku"}


def test_stock_links_existing_uploads_and_fetches_due_items(b2, monkeypatch):
    with db.tx() as conn:
        conn.execute("INSERT INTO media(created_at, kind, title, cues) VALUES (?, 'upload', ?, '[]')",
                     (db.now_iso(), "Tatort: Schweigen (NDR, ARD Mediathek)"))
    assert "tatort-schweigen" in stock.link_existing()
    fetched = []
    monkeypatch.setattr(stock, "FETCHERS", {"mediathek": lambda it: fetched.append(it["key"]),
                                            "podcast": lambda it: fetched.append(it["key"])})
    report = stock.run(date(2026, 10, 11), only={"soko-leipzig-das-auge", "egp-698", "tatort-schweigen"})
    assert sorted(fetched) == ["egp-698", "soko-leipzig-das-auge"] and not report["failed"]


def test_podcast_episode_by_number():
    xml = b"""<rss><channel><item><title>701: Aktivismus</title><enclosure url="https://cdn/701.mp3"/></item>
    <item><title>698: Wie Lara Deutsch gelernt hat</title><enclosure url="https://cdn/698.mp3"/></item></channel></rss>"""
    assert stock.podcast_episode(xml, "698")["url"] == "https://cdn/698.mp3"
    assert stock.podcast_episode(xml, "69") is None


def test_materialcheck_lists_real_gaps_only(b2, monkeypatch):
    at(monkeypatch, SUNDAY)
    add_clip("tatort-schweigen")
    result = materials.check(date(2026, 10, 11), date(2026, 10, 12), plan.plan("2B"), days=3, links=False)
    gaps = {(g["date"], g["block"]) for g in result["gaps"]}
    assert ("2026-10-12", "input") not in gaps          # Tatort is there
    assert ("2026-10-12", "lesen") in gaps              # the podcast isn't (in this test library)
    written = materials.write_check(date(2026, 10, 11))
    assert (config.DATA_DIR / "materialcheck.json").exists() and "gaps" in written
    # #29: the Tatort has no transcript yet — listed for the operator, not as a gap on Heute
    missing = written["transcripts"]["missing"]
    assert [(m["title"][:6], m["hint"]) for m in missing][:1] == [
        ("Tatort", "Transkript fehlt — der Mac mini holt es um 01:30 (transcripts/stock-tatort-schweigen.whisper.json)")]
    assert not any("Transkript" in (g["problem"] or "") for g in written["gaps"])
    assert "transcripts" not in b2.get("/api/materials").json()["check"]
    mid = missing[0]["mediaId"]
    (config.DATA_DIR / "transcripts").mkdir(exist_ok=True)
    (config.DATA_DIR / "transcripts" / "stock-tatort-schweigen.whisper.json").write_text(
        json.dumps({"segments": [{"start": 1.0, "end": 2.0, "text": "Wo waren Sie?", "words": [
            {"w": "Wo", "s": 1.0, "e": 1.2, "p": 0.9}, {"w": "waren", "s": 1.3, "e": 1.6, "p": 0.9},
            {"w": "Sie?", "s": 1.7, "e": 2.0, "p": 0.9}]}]}), encoding="utf-8")
    again = materials.write_check(date(2026, 10, 11))["transcripts"]
    assert mid in again["changed"] and mid not in [m["mediaId"] for m in again["missing"]]


def test_bald_faellig_schirach_first_no_kaenguru(b2, monkeypatch):
    """Update 5/6: the week-2 book is Schirach (paper by Mon 12.10., ebook by Sat 17.10.); Känguru has no card."""
    at(monkeypatch, SUNDAY)
    n = b2.get("/api/materials").json()["notices"]
    assert [x["by"] for x in n] == sorted(x["by"] for x in n)
    v = next(x for x in n if x["id"] == "schirach-verbrechen")
    assert (v["by"], v["byEbook"], v["firstDay"], v["week"]) == ("2026-10-12", "2026-10-17", "2026-10-19", 2)
    assert v["book"]["isbn"] == "978-3-442-77066-3" and v["book"]["price"] == "12,00 €"
    assert not any("kaenguru" in x["id"] for x in n)
    # #32: week 4 is QualityLand as a Kindle ebook — due two days ahead, one shop, no paper option
    q = next(x for x in n if x["id"] == "kling-qualityland")
    assert (q["week"], q["by"], q["firstDay"]) == (4, "2026-10-31", "2026-11-02") and "byEbook" not in q
    assert q["book"]["format"] == "ebook" and q["book"]["asin"] == "B071436DMF" and q["book"]["price"] == "9,99 €"
    assert q["book"]["shops"] == [{"name": "Amazon.de (Kindle)", "url": "https://www.amazon.de/dp/B071436DMF"}]
    assert not any("nordwind" in x["id"] for x in n)
    f = b2.get("/api/fahrplan").json()
    assert f["today"] == "2026-10-11" and any(x["id"] == "schirach-verbrechen" for x in f["notices"])
    # Monday of week 2: whole stories
    mon = by_block(b2.get("/api/materials", params={"today": "2026-10-19"}).json()["today"])
    assert mon["lesen"]["kind"] == "book" and mon["lesen"]["part"] == "S. 7–42: „Fähner“ und „Tanatas Teeschale“"


def test_qualityland_days_name_chapters_and_the_kindle_due_date(b2, monkeypatch):
    """#32: W4 Mo/Mi/Do/Fr read QualityLand by chapter; not bought yet → "Kaufen bis 31.10.", then "gekauft ✓"."""
    at(monkeypatch, datetime(2026, 10, 26, 7, 0, tzinfo=timezone.utc))
    mon = by_block(b2.get("/api/materials", params={"today": "2026-11-02"}).json()["today"])["lesen"]
    assert mon["kind"] == "book" and mon["title"] == "Marc-Uwe Kling: QualityLand" and mon["minutes"] == 35
    assert mon["part"] == "Vom Anfang bis „QualityLand Reiseführer: Ohrwürmer“" and mon["detail"] == "Kaufen bis 31.10."
    assert "Frei lesen: kein Wörterbuch" in mon["text"] and "Inhaltsverzeichnis" in mon["text"]
    b2.post("/api/books/kling-qualityland/bought", json={"done": True})
    wed = by_block(b2.get("/api/materials", params={"today": "2026-11-04"}).json()["today"])["lesen"]
    assert wed["part"] == "„Ado & Eva“ („Peter Arbeitsloser hat einmal …“) bis „PartnerCare“" and wed["detail"] == "gekauft ✓"
    assert not any(x["id"] == "kling-qualityland" for x in b2.get("/api/materials").json()["notices"])


def test_today_shows_another_day_and_every_block_has_a_target(client, monkeypatch):
    """#20/#27: /api/today?today=…&phase=… (drives the E2E); every block opens its item, no Prüfungsteil."""
    from kaskade import db
    # #21: later days roll on from where he is now — seen, like the E2E, from Tue 13.10. 09:30 with nothing heard yet
    at(monkeypatch, datetime(2026, 10, 13, 7, 30, tzinfo=timezone.utc))
    db.set_setting("planStart", "2026-10-12")
    for iso in ("2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"):
        r = client.get(f"/api/today?today={iso}&phase=2B").json()
        assert r["date"] == iso and list(r["assignments"]) == ["karten", "input", "lesen"]
        assert r["assignments"]["karten"]["start"] == {"to": "/karten"}
    # #24/#27: Friday's lesen block ends with the Schirach Lesetest — the publisher's Leseprobe, opened at S. 7
    fr = client.get("/api/today?today=2026-10-16&phase=2B").json()["assignments"]["lesen"]
    test = fr["then"][0]
    assert fr["kind"] == "clip" and fr["title"].startswith("ARD Radio Tatort")
    assert test["kind"] == "lesetest" and test["start"]["href"] == "https://www.bic-media.com/books/content/shortened/9783442770663.pdf#page=9"
    assert test["title"] == "Lesetest: Schirach, Verbrechen — die ersten zwei Seiten von „Fähner“" and test["part"] == "S. 7–8"
    assert test["minutes"] == 25 and "ohne Wörterbuch lesen, dann einschätzen" in test["detail"] and test["block"] == "lesen"
    assert client.get("/api/today?phase=3").status_code == 422


def test_rolling_ranges_follow_where_he_really_is(b2, monkeypatch):
    """#21, Matt's Monday: he reached 7:10 and ticked the block off → Tuesday is 7:10 + a day, not 30:14–60:40."""
    at(monkeypatch, MONDAY)
    mid = add_clip("tatort-schweigen")
    assert by_block(b2.get("/api/materials").json()["today"])["input"]["part"] == "0:00–22:20"  # fixed this morning
    b2.put(f"/api/media/{mid}/progress", json={"position": 430})
    b2.post("/api/plan/done", json={"block": "input", "done": True})
    tue = by_block(b2.get("/api/materials").json()["next"])["input"]
    assert tue["part"] == "7:10–34:34" and tue["start"]["to"] == f"/schauen/{mid}?von=430&bis=2074"
    assert tue["text"].startswith("Tatort: Schweigen (ARD Mediathek · NDR), 7:10–34:34")
    # Tuesday morning: the range is fixed, Monday's reach is noted; watching doesn't move today's target
    at(monkeypatch, datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc))
    t = b2.get("/api/today").json()
    assert t["assignments"]["input"]["part"] == "7:10–34:34" and t["assignments"]["input"]["rolling"] is True
    b2.put(f"/api/media/{mid}/progress", json={"position": 1500})
    assert b2.get("/api/today").json()["assignments"]["input"]["part"] == "7:10–34:34"
    with db.tx() as conn:
        rows = {r["local_date"]: dict(r) for r in conn.execute("SELECT * FROM watch_ranges WHERE block = 'input'")}
    assert rows["2026-10-12"]["reached"] == 430 and rows["2026-10-12"]["clean"] == 1
    assert (rows["2026-10-13"]["start"], rows["2026-10-13"]["end"]) == (430, 2074)
    # the following days and clips shift: Tatort ends Thursday, SOKO starts Friday instead of Thursday
    m = b2.get("/api/materials", params={"today": "2026-10-15"}).json()
    assert by_block(m["today"])["input"]["part"].endswith("–89:21") and by_block(m["next"])["input"]["title"].startswith("SOKO")


def test_previews_never_fix_a_range(b2, monkeypatch):
    at(monkeypatch, MONDAY)
    add_clip("tatort-schweigen")
    b2.get("/api/materials", params={"today": "2026-10-12", "phase": "2B"})
    b2.get("/api/today", params={"today": "2026-10-12"})
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM watch_ranges").fetchone()[0] == 0
    b2.get("/api/today")
    with db.tx() as conn:
        assert {r[0] for r in conn.execute("SELECT block FROM watch_ranges")} == {"input", "lesen"}


def test_audio_heard_on_the_phone_and_rated_moves_on_the_next_day(b2, monkeypatch):
    """#31: Tuesday's EGP 684 heard on the phone (Kaskade has no position) and rated → Wednesday is EGP 700."""
    at(monkeypatch, datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc))  # Tue 09:00
    ids = {k: add_clip(k, s) for k, s in [("egp-698", 1914.0), ("egp-684", 1648.0), ("egp-700", 2029.0)]}
    b2.put(f"/api/media/{ids['egp-698']}/progress", json={"position": 1914})  # Monday's, played in Kaskade
    lesen = b2.get("/api/today").json()["assignments"]["lesen"]
    audio = next(x for x in [lesen, *lesen["then"]] if x["kind"] == "clip")  # after Tuesday's tagesschau
    assert (audio["clip"], audio["rateItem"]) == ("egp-684", "clip:egp-684:0-1648")
    assert b2.post("/api/ratings", json={"block": "lesen", "item": "clip:egp-684:0-1648", "pct": 80}).status_code == 200
    at(monkeypatch, datetime(2026, 10, 14, 4, 30, tzinfo=timezone.utc))  # Wed 06:30, the Materialcheck
    wed = by_block(b2.get("/api/materials").json()["today"])["lesen"]
    assert (wed["clip"], wed["part"]) == ("egp-700", "0:00–33:49") and wed["text"].startswith("Easy German Podcast 700")
    with db.tx() as conn:
        assert conn.execute("SELECT reached FROM watch_ranges WHERE local_date = '2026-10-13' AND block = 'lesen'").fetchone()[0] == 1648
