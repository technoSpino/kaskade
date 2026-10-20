"""#33: no crime story about child abuse — the search, the Materialcheck flag, and Kernsätze der Woche."""
import json

from kaskade import db, feed, materials, srs, stock, themes

FINE = [{"start": 1.0, "end": 2.0, "text": "Wo waren Sie gestern Abend?"},
        {"start": 3.0, "end": 4.0, "text": "Die Wohnung war leer."}]
ABOUT_IT = [{"start": float(i), "end": i + 1.0, "text": t} for i, t in enumerate([
    "Es geht um Missbrauch.", "Das Vertrauen wurde missbraucht.", "Ein Netzwerk von Pädophilen.", "Sie war noch minderjährig."])]


def clip(key, cues, tag="krimi", spoken=None):
    with db.tx() as conn:
        return conn.execute(
            "INSERT INTO media(created_at, kind, title, media_file, cues, spoken_cues, key, tag, status)"
            " VALUES (?, 'mediathek', ?, 'x.mp4', ?, ?, ?, ?, 'ready')",
            (db.now_iso(), key, json.dumps(cues), json.dumps(spoken) if spoken else None, key, tag)).lastrowid


def catalog(monkeypatch, items):
    monkeypatch.setattr(stock, "catalog", lambda: {"items": items, "books": []})


def test_the_search_words():
    assert [bool(themes.ABUSE.search(c["text"])) for c in ABOUT_IT] == [True] * 4
    assert themes.ABUSE.search("Kinderschänder") and themes.ABUSE.search("KINDERPORNOGRAFIE")
    assert not any(themes.ABUSE.search(c["text"]) for c in FINE)
    assert themes.hits(ABOUT_IT[:2] + FINE) == [{"at": 0.0, "text": "Es geht um Missbrauch."},
                                                 {"at": 1.0, "text": "Das Vertrauen wurde missbraucht."}]


def test_scan_flags_a_crime_clip_about_it_and_one_whose_subtitles_just_arrived(client, monkeypatch):
    catalog(monkeypatch, [
        {"key": "done-krimi", "tag": "krimi", "themeCheck": "2026-10-16: Synopsis + UT geprüft — Kindesmissbrauch ist der Fall"},
        {"key": "new-krimi", "tag": "krimi", "themeCheck": "2026-10-16: Synopsis geprüft, kein Kindesmissbrauch; UT folgt nach dem Import"},
        {"key": "clean-krimi", "tag": "krimi", "themeCheck": "2026-10-16: Synopsis + UT geprüft, kein Kindesmissbrauch"},
        {"key": "bad-krimi", "tag": "krimi", "themeCheck": "2026-10-16: Synopsis geprüft, kein Kindesmissbrauch"},
        {"key": "comedy", "tag": "comedy", "themeCheck": "2026-10-16: kein Krimi"}])
    done = clip("done-krimi", FINE, spoken=ABOUT_IT)   # already known: listed, no decision needed
    new = clip("new-krimi", FINE)                      # its subtitles are in now → write the themeCheck
    clip("clean-krimi", FINE)
    bad = clip("bad-krimi", ABOUT_IT)                  # the synopsis didn't say → stop before it's planned
    one = clip("comedy", FINE + ABOUT_IT[:1], tag="comedy")
    out = {r["mediaId"]: r for r in themes.scan()}
    assert set(out) == {done, new, bad, one}
    assert out[done]["hits"] == 4 and out[done]["review"] is None and out[done]["at"] == [0.0, 1.0, 2.0, 3.0]
    assert out[new]["hits"] == 0 and out[new]["review"] == "UT sind da (0 Treffer) — themeCheck in stock.json nachtragen"
    assert out[bad]["review"] == "4 Treffer zu Kindesmissbrauch — Synopsis lesen, bevor es geplant wird"
    assert out[one]["hits"] == 1 and out[one]["review"] is None  # one passing mention is fine


def test_materialcheck_writes_the_scan_for_the_operator(client, monkeypatch):
    from datetime import date
    monkeypatch.setenv("KASKADE_OFFLINE", "1")
    db.set_setting("phase", "2B")
    db.set_setting("planStart", "2026-10-12")
    mid = clip("tatort-schweigen", ABOUT_IT)
    written = materials.write_check(date(2026, 10, 16))
    [row] = written["themes"]
    assert row["mediaId"] == mid and row["hits"] == 4 and row["review"] is None  # stock.json: "ist der Fall"
    assert "Kindesmissbrauch ist der Fall" in row["themeCheck"]
    assert "themes" not in client.get("/api/materials").json()["check"]  # not on Heute


def test_kernsaetze_skip_lines_about_it_and_keep_the_card(client, monkeypatch):
    deck = srs.deck()
    for c in deck[:3]:
        srs.review(c["id"], 3)
    real = srs.card_content
    swapped = {deck[1]["id"]: "Der Kommissar ermittelt wegen Missbrauch im Verein."}
    monkeypatch.setattr(srs, "card_content", lambda cid: {**real(cid), "sentence": swapped[cid]} if cid in swapped else real(cid))
    sentences = feed.week_sentences(srs.now_utc())
    assert sentences == [deck[0]["sentence"], deck[2]["sentence"]]
    assert srs.card_content(deck[1]["id"])["sentence"] == swapped[deck[1]["id"]]  # the card itself is untouched
