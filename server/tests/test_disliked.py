"""#37: no more Merz gegen Merz — Folge 2 and 3 leave the plan, Thursday goes back to Die 100."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from kaskade import config, db, materials, plan, stock

from .test_api_materials import add_clip, at, b2, by_block  # noqa: F401  (fixture)

TUE_3 = datetime(2026, 11, 3, 9, 15, tzinfo=timezone.utc)           # Di 3.11. 10:15 Berlin, in the lesen block
OFF = [{"from": "2026-10-19", "to": "2026-10-25"}, {"from": "2026-10-26", "to": "2026-11-01"}]   # two weeks off
GONE = {"merz-gegen-merz-2", "merz-gegen-merz-3"}


def matt(monkeypatch, dislike=True):
    """His state on Di 3.11.: week 1 and SOKO done, Folge 1 watched in today's input block and rated 60 %."""
    at(monkeypatch, TUE_3)
    ids = {k: add_clip(k, seconds=s) for k, s in {
        "tatort-schweigen": 5361.0, "soko-leipzig-das-auge": 2611.0, "merz-gegen-merz-1": 1355.68,
        "merz-gegen-merz-2": 1386.72, "merz-gegen-merz-3": 1367.44, "die-100-sozialstaat": 1500.0,
        "respekt-buerokratie": 1742.0}.items()}
    with db.tx() as conn:
        for key, pos in {"tatort-schweigen": 5359.6, "soko-leipzig-das-auge": 2611.0, "merz-gegen-merz-1": 1355.68}.items():
            conn.execute("INSERT INTO media_progress(media_id, position, updated_at) VALUES (?, ?, 'x')", (ids[key], pos))
        conn.execute("INSERT INTO watch_ranges VALUES ('2026-11-02', 'input', 'soko-leipzig-das-auge', 1314, 2611, 1, 2611)")
        conn.execute("INSERT INTO watch_ranges VALUES ('2026-11-03', 'input', 'merz-gegen-merz-1', 0, 1356, 1, NULL)")
        conn.execute("INSERT INTO plan_done VALUES ('2026-11-03', 'input')")
        conn.execute("INSERT INTO ratings(created_at, local_date, block, item, kind, label, pct, hard, lines, detail) VALUES"
                     " ('2026-11-03T09:10:40+00:00', '2026-11-03', 'input', 'clip:merz-gegen-merz-1:0-1356', 'clip',"
                     " 'Merz gegen Merz, Folge 1', 60, 0, 432, ?)", (json.dumps({"mediaId": ids["merz-gegen-merz-1"], "from": 0, "to": 1356}),))
    db.set_setting("pauses", OFF)
    if dislike:
        db.set_setting("dislikedShows", ["merz-gegen-merz"])
    return ids


def input_on(client, day):
    return by_block(client.get("/api/materials", params={"today": day}).json()["today"])["input"]


@pytest.mark.parametrize("dislike", [False, True])
def test_thursday_goes_back_to_die_100_and_today_stays(b2, monkeypatch, dislike):
    matt(monkeypatch, dislike)   # the plan change alone does it; the disliked list doesn't change it
    today = b2.get("/api/today").json()["assignments"]["input"]
    assert today["clip"] == "merz-gegen-merz-1" and today["range"] == [0, 1356]   # what he watched this morning
    assert b2.get("/api/ratings/today").json()[0]["rating"]["pct"] == 60
    assert input_on(b2, "2026-11-04")["kind"] == "netflix"                        # King of Stonks stays
    thu = input_on(b2, "2026-11-05")
    assert (thu["clip"], thu["range"]) == ("die-100-sozialstaat", [0, 1482])      # 0:00–24:42
    assert input_on(b2, "2026-11-06")["kind"] == "youtube"
    assert input_on(b2, "2026-11-09")["clip"] == "respekt-buerokratie"            # week 3 as planned
    assert input_on(b2, "2026-11-10")["clip"] == "charite-19-ankunft"
    with db.tx() as conn:
        rows = [tuple(r) for r in conn.execute("SELECT local_date, clip, start, end FROM watch_ranges WHERE block = 'input'"
                                               " ORDER BY local_date")]
    assert rows == [("2026-11-02", "soko-leipzig-das-auge", 1314, 2611), ("2026-11-03", "merz-gegen-merz-1", 0, 1356)]


def test_bibliothek_and_materials_no_longer_list_folge_2_and_3(b2, monkeypatch):
    ids = matt(monkeypatch)
    keys = {c["key"] for c in b2.get("/api/media").json()}
    assert "merz-gegen-merz-1" in keys and not GONE & keys          # Folge 1 stays: he watched it
    assert b2.get(f"/api/media/{ids['merz-gegen-merz-2']}").status_code == 200   # hidden, not deleted
    assert (config.MEDIA_DIR / "stock-merz-gegen-merz-2.mp4").exists()
    seen = set()
    for i in range(0, 32, 2):
        g = b2.get("/api/materials", params={"today": (date(2026, 11, 3) + timedelta(days=i)).isoformat()}).json()
        seen |= {it.get("clip") for grp in (g["today"], g["next"]) for it in materials.flat(grp["items"])}
    assert "die-100-sozialstaat" in seen and not GONE & seen


def test_a_disliked_show_on_a_later_day_is_a_gap_not_a_clip(b2, monkeypatch):
    matt(monkeypatch)
    # weeks 5+ repeat weeks 1–4 as written: Mo 30.11. would be Folge 1 again
    mon = input_on(b2, "2026-11-30")
    assert mon["kind"] == "none" and mon["status"] == "todo" and "ist aus dem Plan" in mon["detail"]
    gaps = materials.check(date(2026, 11, 30), date(2026, 10, 12), plan.plan("2B"), days=1, links=False)["gaps"]
    assert [g["block"] for g in gaps if "ist aus dem Plan" in g["problem"]] == ["input"]
    # a show added later drops out of the rolling queue too: its slot takes the next clip
    db.set_setting("dislikedShows", ["merz-gegen-merz", "die-100"])
    assert input_on(b2, "2026-11-05")["clip"] == "respekt-buerokratie"
    assert b2.get("/api/today").json()["assignments"]["input"]["clip"] == "merz-gegen-merz-1"   # today stays


def test_the_disliked_list_blocks_a_stock_key_with_that_prefix(client, monkeypatch):
    db.set_setting("dislikedShows", ["merz-gegen-merz"])
    assert stock.disliked("merz-gegen-merz-9") and not stock.disliked("netflix-king-of-stonks") and not stock.disliked(None)
    cat = {"items": [
        {"key": "merz-gegen-merz-4", "kind": "mediathek", "title": "Merz gegen Merz, Folge 4", "url": "https://www.zdf.de/x"},
        {"key": "merz-gegen-merz-5", "kind": "mediathek", "title": "Merz gegen Merz, Folge 5", "match": "Eine Komödie, Teil 5",
         "url": "https://www.zdf.de/y"},
        {"key": "stromberg-1", "kind": "mediathek", "title": "Stromberg, Folge 1", "tag": "comedy", "url": "https://www.ardmediathek.de/z"}]}
    monkeypatch.setattr(stock, "catalog", lambda: cat)
    fetched = []
    monkeypatch.setitem(stock.FETCHERS, "mediathek", lambda it: fetched.append(it["key"]))
    with db.tx() as conn:   # his own upload whose title matches the disliked item
        own = conn.execute("INSERT INTO media(created_at, kind, title, cues) VALUES ('x', 'upload', 'Eine Komödie, Teil 5', '[]')").lastrowid
    report = stock.run(date(2026, 11, 3))
    assert fetched == ["stromberg-1"]                                    # comedy as a genre stays
    assert report["disliked"] == ["merz-gegen-merz-4", "merz-gegen-merz-5"] and report["linked"] == []
    assert stock.run(date(2026, 11, 3), only={"merz-gegen-merz-4"})["disliked"] == ["merz-gegen-merz-4"]
    assert fetched == ["stromberg-1"]
    # … and his own upload stays his: not linked to the disliked key, so it stays in the library
    assert own in {c["id"] for c in client.get("/api/media").json()}
