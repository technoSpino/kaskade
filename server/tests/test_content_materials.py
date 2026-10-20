"""#16: every block of every plan day names exactly one real thing — no choosing, no searching."""
import json
import re

import pytest

from kaskade import config, materials, practice, texts, themes

PLANS = ["plan/weeks-1-4.json", "plan/phase-2b.json"]
STOCK = json.loads((config.CONTENT_DIR / "plan/stock.json").read_text(encoding="utf-8"))
KEYS = {i["key"]: i for i in STOCK["items"]}
BOOKS = {b["id"]: b for b in STOCK.get("books", [])}
VAGUE = re.compile(r"z\. ?B\.|\boder\b|deiner Wahl|frei wählen|\bein(en)? Podcast\b|\bein Buch\b|\beine Serie\b", re.I)


def load(name):
    return json.loads((config.CONTENT_DIR / name).read_text(encoding="utf-8"))


def days(name):
    for w in load(name)["weeks"]:
        for d in w["days"]:
            yield w["week"], d


@pytest.mark.parametrize("name", PLANS)
def test_no_vague_assignments(name):
    for week, d in days(name):
        for field in ("focus", "karten", "input", "lesen"):
            assert not VAGUE.search(d[field]), f"{name} W{week} {d['day']} {field}: {d[field]}"


@pytest.mark.parametrize("name", PLANS)
def test_one_exact_item_per_block(name):
    for week, d in days(name):
        blocks = [m["block"] for m in d["materials"]]
        # #27: the lesen block may hold a second (and third) exact item that fills it
        assert blocks.count("input") == 1 and 1 <= blocks.count("lesen") <= 3, f"W{week} {d['day']}"
        assert "pruefung" not in blocks, f"W{week} {d['day']}"


def material_minutes(m):
    if m["kind"] == "clip" and not m.get("minutes"):
        return (materials.seconds(m["to"]) - materials.seconds(m.get("from", 0))) / 60
    return m["minutes"]


@pytest.mark.parametrize("name", PLANS)
def test_lesen_items_fill_the_block(name):
    """#27: the longer lesen block (2B 60 min, 2A 55 min) is filled with exact items, within ±5 min."""
    block = next(b for b in load(name)["block"] if b["id"] == "lesen")["minutes"]
    for week, d in days(name):
        mats = [m for m in d["materials"] if m["block"] == "lesen"]
        total = sum(material_minutes(m) for m in mats)
        assert abs(total - block) <= 5, f"{name} W{week} {d['day']}: {total} of {block} min"
        assert all(m.get("desc") for m in mats) and d["lesen"] == " Danach: ".join(m["desc"] for m in mats)
        kinds = ["audio" if m["kind"] == "clip" else "text" for m in mats]
        assert all(a != b for a, b in zip(kinds, kinds[1:])), f"{name} W{week} {d['day']}: {kinds}"  # the other kind after


@pytest.mark.parametrize("name", PLANS)
def test_materials_point_at_real_things(name):
    for week, d in days(name):
        for m in d["materials"]:
            where = f"{name} W{week} {d['day']} {m}"
            if m["kind"] in ("clip", "satzcheck"):
                assert KEYS[m["clip"]]["kind"] in ("mediathek", "podcast", "audio"), where
                if "to" in m:
                    assert materials.seconds(m["to"]) > materials.seconds(m.get("from", 0)), where
            elif m["kind"] in ("youtube", "netflix"):
                assert KEYS[m["clip"]]["kind"] == m["kind"], where
            elif m["kind"] == "text":
                assert texts.get(m["text"]), where
            elif m["kind"] == "news":
                assert m["feed"] in materials.NEWS_FEEDS, where
            elif m["kind"] == "book":
                assert m["book"] in BOOKS and m.get("part"), where
            elif m["kind"] == "lesetest":  # #24: a book's first pages, from the publisher's Leseprobe
                assert m["book"] in BOOKS and BOOKS[m["book"]]["leseprobe"]["url"].startswith("https://"), where
                assert re.match(r"S\. \d+–\d+$", m["part"]) and m["block"] == "lesen", where
            elif m["kind"] == "practice":
                module = "hoeren" if m["practice"].startswith("h") else "lesen"
                assert practice.get(module, m["practice"]), where
            else:
                pytest.fail(f"unknown kind: {where}")


@pytest.mark.parametrize("name", PLANS)
def test_clip_ranges_are_named_in_the_day_text(name):
    """The day text and the data say the same: a range in the materials appears in the text."""
    for week, d in days(name):
        m = next(m for m in d["materials"] if m["block"] == "input")
        if m["kind"] == "clip" and "to" in m:
            assert f"{m.get('from', '0:00')}–{m['to']}" in d["input"], f"W{week} {d['day']}"


def test_stock_is_real_and_sourced():
    for it in STOCK["items"]:
        assert it["kind"] in ("mediathek", "podcast", "audio", "youtube", "netflix"), it["key"]
        assert it["title"] and it["source"] and it["url"].startswith("https://"), it["key"]
        if it["kind"] == "mediathek":
            assert re.match(r"https://www\.(ardmediathek|zdf|arte|3sat)\.", it["url"]), it["key"]
            # still online well after the plan's four weeks (checked by hand, re-checked daily)
            assert it["availableTo"] >= "2026-12-31", it["key"]
        if it["kind"] == "audio":
            assert it["audio"].startswith("https://") and it["availableTo"] >= "2026-12-31", it["key"]
        if it["kind"] == "netflix":
            assert it["url"].startswith("https://www.netflix.com/de/title/"), it["key"]
        if it["kind"] == "podcast":
            assert it["feed"].startswith("https://") and isinstance(it["episode"], int), it["key"]
    for b in BOOKS.values():
        assert b["author"] and b["title"] and b["format"] in ("paper", "ebook", "audiobook") and b["shops"], b["id"]


def test_every_stock_item_is_used():
    used = {m.get("clip") for name in PLANS for _, d in days(name) for m in d["materials"]}
    assert set(KEYS) <= used | {None}, set(KEYS) - used


def test_plan_prompts_are_tagged_ai():
    for p in load("plan/weeks-1-4.json")["prompts"]:
        assert p["origin"] == "ai"


def test_no_tagesschau_after_matts_20_percent():
    """#22: tagesschau was far too hard (20 %) — every reading day after it uses nachrichtenleicht."""
    for name in PLANS:
        for week, d in days(name):
            for m in d["materials"]:
                if m["kind"] == "news" and not (name.endswith("2b.json") and week == 1 and d["day"] == "Di"):
                    assert m["feed"] == "leicht" and m["minutes"] >= 5, f"{name} W{week} {d['day']}"
                    assert "nachrichtenleicht.de" in m["desc"] and "tagesschau" not in d["lesen"]


def test_every_book_is_read_in_a_plan():
    """A book in the catalog means a purchase card — only for books a plan actually uses."""
    used = {m["book"] for name in PLANS for _, d in days(name) for m in d["materials"] if m["kind"] == "book"}
    assert set(BOOKS) == used


def test_book_parts_are_whole_stories_with_pages():
    """Update 5: a day's part of Verbrechen is one or two whole stories with their page range."""
    parts = [m["part"] for _, d in days("plan/phase-2b.json") for m in d["materials"]
             if m["kind"] == "book" and m["book"] == "schirach-verbrechen"]
    assert parts[0].startswith("S. 7–42") and parts[-1] == "S. 185–205: „Der Äthiopier“"
    for part in parts:
        a, b = map(int, re.match(r"S\. (\d+)–(\d+): „", part).groups())
        assert 0 < b - a < 41, part  # at most ~40 pages in a 35-minute block


GENRES = {"scifi", "fantasy", "history", "nonfiction", "krimi"}  # #32: no romance


def test_every_book_has_an_allowed_genre():
    for b in BOOKS.values():
        assert b["genre"] in GENRES, b["id"]
    assert "gut-gegen-nordwind" not in BOOKS and not any("nordwind" in i.get("id", "") for i in STOCK.get("later", []))


def test_qualityland_is_read_by_chapter_from_the_start():
    """#32: whole chapters of the e-book's table of contents, in order, no gaps, ≈ 35 min at 110 words/min."""
    b = BOOKS["kling-qualityland"]
    assert b["format"] == "ebook" and b["asin"] and len(b["shops"]) == 1 and "amazon.de" in b["shops"][0]["url"]
    titles = [c["title"] for c in b["chapters"]]
    mats = [m for w in load("plan/phase-2b.json")["weeks"] for d in w["days"] for m in d["materials"]
            if m["kind"] == "book" and m["book"] == b["id"]]
    assert len(mats) == 4
    nxt = 0
    for m in mats:
        first, last = (titles.index(t) for t in m["chapters"])
        assert first == nxt and last >= first, m["chapters"]
        nxt = last + 1
        minutes = sum(c["audioMin"] for c in b["chapters"][first:last + 1]) * 137 / 110
        assert 30 <= minutes <= 45, (m["chapters"], round(minutes))
        assert f"„{titles[last]}“" in m["part"] and f"„{titles[last]}“" in m["desc"] and "Seite" not in m["part"]
        assert first == 0 or f"„{titles[first]}“" in m["part"]


THEME_CHECK = re.compile(r"^20\d\d-\d\d-\d\d: \S")


def test_every_item_has_a_theme_check():
    """#33: synopsis (and subtitles, once there) checked for child abuse; the result is in stock.json."""
    for it in STOCK["items"]:
        assert THEME_CHECK.match(it.get("themeCheck", "")), it["key"]
        if it["tag"] == "krimi":
            assert "Synopsis" in it["themeCheck"], it["key"]
    for b in BOOKS.values():
        assert THEME_CHECK.match(b.get("themeCheck", "")) or b["genre"] != "krimi", b["id"]


def test_nothing_about_child_abuse_is_planned_after_week_1():
    """#33: Tatort: Schweigen (week 1, seen) is the only item whose check found it; nothing later uses one."""
    flagged = {k for k, it in KEYS.items() if it["tag"] == "krimi" and themes.CLEAN not in it["themeCheck"]}
    assert flagged == {"tatort-schweigen"}
    for b in BOOKS.values():
        assert b["genre"] != "krimi" or themes.CLEAN in b["themeCheck"], b["id"]
    for name in PLANS:
        for week, d in days(name):
            for m in d["materials"]:
                assert m.get("clip") not in flagged or (name.endswith("2b.json") and week == 1), f"{name} W{week} {d['day']}"


def test_library_texts_and_day_texts_are_clean():
    for t in texts.library():
        assert not themes.ABUSE.search(t["title"] + " " + t["text"]), t["id"]
    for name in PLANS:
        for week, d in days(name):
            assert not themes.ABUSE.search(json.dumps(d, ensure_ascii=False)), f"{name} W{week} {d['day']}"
