"""#40: every highlighted word has a meaning — lookup, compound, cached KI, else no highlight.
The dictionary and all sentences are invented for the test."""
import json

import pytest

from kaskade import ai, analyze, db, meanings

FAKE = {
    "entries": {
        "Zuschlag": [{"pos": "NOUN", "gl": ["surcharge, extra charge", "extra pay"], "g": "m", "pl": "Zuschläge"}],
        "Kind": [{"pos": "NOUN", "gl": ["kid; child (young person)"], "g": "n", "pl": "Kinder"}],
        "sozial": [{"pos": "ADJ", "gl": ["social"]}],
        "Leistung": [{"pos": "NOUN", "gl": ["performance, achievement", "service"], "g": "f", "pl": "Leistungen"}],
        "Schraube": [{"pos": "NOUN", "gl": ["screw"], "g": "f", "pl": "Schrauben"}],
        "stellen": [{"pos": "VERB", "gl": ["causative of stehen: to put, place"]}],
        "bekommen": [{"pos": "VERB", "gl": ["to get, receive"]}],
        "herausbekommen": [{"pos": "VERB", "gl": ["to figure out"]}],
        "kriegen": [{"pos": "VERB", "gl": ["to get"]}],
        "herauskriegen": [{"pos": "VERB", "gl": ["to work out"]}],
        "Rente": [{"pos": "NOUN", "gl": ["pension"], "g": "f", "pl": "Renten"}],
        "Kasse": [{"pos": "NOUN", "gl": ["cash register, till"], "g": "f", "pl": "Kassen"}],
        "Pate": [{"pos": "NOUN", "gl": ["godfather"], "g": "m", "pl": "Paten"}],
        "Schaft": [{"pos": "NOUN", "gl": ["shaft"], "g": "m", "pl": "Schäfte"}],
        "Bass": [{"pos": "NOUN", "gl": ["bass"], "g": "m", "pl": "Bässe"}],
        "Familie": [{"pos": "NOUN", "gl": ["family"], "g": "f", "pl": "Familien"}],
    },
    "forms": {"Zuschläge": "Zuschlag", "Zuschlägen": "Zuschlag", "Kinder": "Kind", "Leistungen": "Leistung",
              "Schrauben": "Schraube", "bekommt": "bekommen", "Kassen": "Kasse", "Renten": "Rente"},
}


@pytest.fixture()
def fake_dict(monkeypatch):
    monkeypatch.setattr(analyze, "dictionary", lambda: FAKE)
    monkeypatch.setattr(analyze, "core_known_estimate", lambda: 0)


# ── 1. better lookup ──

def test_inflected_compound_to_its_base_form(fake_dict):
    d = analyze.derive("Stellschrauben", "NOUN")
    assert d["word"] == "Stellschraube" and d["compound"]["text"] == "Stellschraube = Stell + Schraube"
    assert analyze.dict_entry(d)["display"] == "die Stellschraube · die Stellschrauben"
    assert d["gl"] == ["to put, place + screw"]


@pytest.mark.parametrize("text, verb", [("rausbekommt", "herausbekommen"), ("rauszukriegen", "herauskriegen")])
def test_colloquial_particle_verbs(fake_dict, text, verb):
    d = analyze.derive(text, "VERB")
    assert d["word"] == verb and d["note"] == "raus- = heraus- (umgangssprachlich)" and d["gl"]


def test_compound_split_with_the_heads_article_and_plural(fake_dict):
    d = analyze.derive("Kinderzuschlag", "NOUN")
    e = analyze.dict_entry(d)
    assert e["compound"]["text"] == "Kinderzuschlag = Kinder + Zuschlag"
    assert [(p["text"], p["lemma"], p["gloss"]) for p in e["compound"]["parts"]] == [
        ("Kinder", "Kind", "kid"), ("Zuschlag", "Zuschlag", "surcharge, extra charge")]
    assert e["gloss"] == "kid + surcharge, extra charge" and e["display"] == "der Kinderzuschlag · die Kinderzuschläge"
    assert e["lemma"] == "Kinderzuschlag"


def test_compound_with_an_adjective_and_a_linking_n(fake_dict):
    e = analyze.dict_entry(analyze.derive("Sozialleistungen", "NOUN"))
    assert e["compound"]["text"] == "Sozialleistung = sozial + Leistung"
    assert e["display"] == "die Sozialleistung · die Sozialleistungen" and e["gloss"] == "social + performance, achievement"
    assert analyze.derive("Rentenkasse", "NOUN")["compound"]["text"] == "Rentenkasse = Renten + Kasse"
    assert analyze.derive("Sozialzuschlägen", "NOUN")["word"] == "Sozialzuschlag"


def test_no_made_up_meanings(fake_dict):
    assert analyze.derive("Patenschaft", "NOUN") is None  # -schaft is a suffix, no "Paten + Schaft"
    assert analyze.derive("Basser", "NOUN") is None       # misheard, not a form of Bass
    assert analyze.derive("Tinasse", "NOUN") is None


# ── 3. no meaning → no highlight ──

SENT = "Die Familie bekommt jetzt mehr Kinderzuschlag und Tinasse."


def word(r, text):
    return next(t for t in r["tokens"] if t["text"] == text)


def test_a_word_without_any_meaning_is_not_highlighted(client, fake_dict):
    r = analyze.analyze(SENT)
    kz, ti = word(r, "Kinderzuschlag"), word(r, "Tinasse")
    assert kz["state"] == "neu" and kz["entry"]["compound"]["text"] == "Kinderzuschlag = Kinder + Zuschlag"
    assert ti["state"] is None and ti["entry"] is None  # still tappable: "Keine Übersetzung gefunden."
    assert all(t["entry"] and t["entry"]["gloss"] for t in r["tokens"] if t["state"] in ("neu", "lernend"))


def test_a_glossary_word_stays_highlighted_in_lesen(client, fake_dict):
    assert word(analyze.analyze(SENT, glossed={"Tinasse"}), "Tinasse")["state"] == "neu"


# ── 2. the KI, asked ahead and cached per (word, sentence) ──

LINES = [{"start": 0.5, "end": 2.0, "text": "Die Familie bekommt jetzt mehr Kinderzuschlag und Tinasse."},
         {"start": 2.5, "end": 4.0, "text": "Das ist ziemlich tricky."}]


@pytest.fixture()
def clip(client):
    with db.tx() as conn:
        return conn.execute("INSERT INTO media(created_at, kind, title, cues) VALUES ('2026-11-05', 'upload', 'Testclip', ?)",
                            (json.dumps(LINES),)).lastrowid


@pytest.fixture()
def fake_ki(monkeypatch):
    calls = []
    answers = {"tricky": {"lemma": "tricky", "gloss": "tricky, difficult", "article": None, "plural": None,
                          "case": None, "caseReason": None, "real": True},
               "Tinasse": {"lemma": "Tinasse", "gloss": None, "article": None, "plural": None,
                           "case": None, "caseReason": None, "real": False}}

    def word_meaning(sentence, target):
        calls.append((target, sentence))
        return {**answers[target], "usage": {"in": 300, "out": 40}}

    monkeypatch.setattr(ai, "available", lambda: True)
    monkeypatch.setattr(ai, "word_meaning", word_meaning)
    return calls


def test_the_ki_is_asked_once_per_word_and_sentence(client, fake_dict, fake_ki, clip):
    assert word(analyze.analyze(LINES[1]["text"]), "tricky")["state"] is None  # not asked yet: no highlight
    out = meanings.fill(clip, 0, 10)
    assert sorted(fake_ki) == [("Tinasse", LINES[0]["text"]), ("tricky", LINES[1]["text"])]
    assert out == {"asked": 2, "meanings": 1, "dropped": 1, "ki": True, "left": 0}
    assert meanings.fill(clip, 0, 10)["asked"] == 0 and len(fake_ki) == 2  # cached
    tok = word(analyze.analyze(LINES[1]["text"]), "tricky")
    assert tok["state"] == "neu" and tok["entry"]["gloss"] == "tricky, difficult" and tok["entry"]["ai"] == ["lemma", "gloss"]
    # "misheard": kept as an answer (not asked again), never highlighted
    assert word(analyze.analyze(LINES[0]["text"]), "Tinasse")["state"] is None
    with db.tx() as conn:
        assert conn.execute("SELECT gloss, in_tokens, out_tokens FROM ki_meanings WHERE word = 'Tinasse'").fetchone()[:] == (None, 300, 40)


def test_another_sentence_is_asked_again(client, fake_dict, fake_ki, clip):
    meanings.fill(clip, 0, 10)
    assert word(analyze.analyze("Das wird tricky."), "tricky")["state"] is None


def test_without_ki_nothing_is_asked_and_nothing_highlighted(client, fake_dict, clip):
    assert meanings.fill(clip, 0, 10) == {"asked": 0, "meanings": 0, "dropped": 0, "ki": False}
    assert client.post(f"/api/media/{clip}/meanings", json={"from": 0, "to": 10}).json() == {"started": False}
    assert word(analyze.analyze(LINES[1]["text"]), "tricky")["state"] is None


def test_opening_a_clip_asks_in_the_background(client, fake_dict, fake_ki, clip):
    r = client.post(f"/api/media/{clip}/meanings", json={"from": 0, "to": 2.2})
    assert r.status_code == 202 and r.json() == {"started": True}
    for _ in range(100):
        if not meanings._running:
            break
        import time
        time.sleep(0.05)
    assert fake_ki == [("Tinasse", LINES[0]["text"])]  # the range: only the first line
    assert client.post(f"/api/media/{clip}/meanings", json={"from": 5, "to": 3}).status_code == 422


def test_the_ki_meaning_is_mined_as_it_is(client, fake_dict, fake_ki, clip, monkeypatch):
    meanings.fill(clip, 0, 10)
    monkeypatch.setattr(ai, "word_info", lambda *a: pytest.fail("asked the KI again"))
    entry = word(analyze.analyze(LINES[1]["text"]), "tricky")["entry"]
    body = {"sentence": LINES[1]["text"], "target": "tricky", "lemma": entry["lemma"], "display": entry["display"],
            "gloss": entry["gloss"], "ai": entry["ai"], "source": "Schauen · Testclip"}
    r = client.post("/api/mined", json=body).json()
    assert r["ai"] == ["lemma", "gloss"]
    card = next(c for c in client.get("/api/mined").json() if c["id"] == r["id"])
    assert card["gloss"] == "tricky, difficult" and card["aiFields"] == ["lemma", "gloss"]


def test_a_compound_is_mined_without_asking_the_ki(client, fake_dict, monkeypatch):
    monkeypatch.setattr(ai, "available", lambda: True)
    monkeypatch.setattr(ai, "word_info", lambda *a: pytest.fail("asked the KI"))
    e = word(analyze.analyze(SENT), "Kinderzuschlag")["entry"]
    r = client.post("/api/mined", json={"sentence": SENT, "target": "Kinderzuschlag", "lemma": e["lemma"],
                                        "display": e["display"], "gloss": e["gloss"]}).json()
    assert r["ai"] == []


def test_a_misheard_answer_keeps_mining_as_before(monkeypatch):
    monkeypatch.setattr(ai, "word_meaning", lambda s, t: {"lemma": "x", "gloss": None, "real": False, "usage": {}})
    assert ai.word_info("Das ist Tinasse.", "Tinasse") is None


# ── the line around a subtitle line, as Schauen sends it (same cases as watch.test.js) ──

def test_sentence_around_matches_the_app():
    split = [{"start": 0, "end": 1.5, "text": "Wo warst du?"}, {"start": 2.2, "end": 3.4, "text": "Mir fällt bei diesem Wetter"},
             {"start": 3.5, "end": 5, "text": "wirklich nichts mehr ein."}, {"start": 5.5, "end": 6.5, "text": "Gut."}]
    assert meanings.sentence_around(split, 2) == ("Mir fällt bei diesem Wetter wirklich nichts mehr ein.", (28, 53))
    assert meanings.sentence_around(split, 1)[1] == (0, 27)
    assert meanings.sentence_around(split, 0)[0] == "Wo warst du?"
    dots = [{"start": 0, "end": 1, "text": "Ich bin in den Keller gegangen und..."}, {"start": 1, "end": 2, "text": "...dort stand eine Kiste."}]
    assert meanings.sentence_around(dots, 1)[0] == "Ich bin in den Keller gegangen und... ...dort stand eine Kiste."
    assert meanings.sentence_around([{"start": 0, "end": 1, "text": "Und dann"}, {"start": 1, "end": 2, "text": "- Was dann?"}], 1)[0] == "- Was dann?"
    assert meanings.sentence_around([{"start": 0, "end": 1, "text": "Und dann"}, {"start": 3.5, "end": 4, "text": "kam er."}], 1)[0] == "kam er."
    many = [{"start": i, "end": i + 1, "text": f"Wort{i}"} for i in range(9)]
    assert meanings.sentence_around(many, 4)[0] == " ".join(f"Wort{i}" for i in range(1, 8))


def test_the_materialcheck_takes_each_planned_clips_next_part():
    items = [{"mediaId": 7, "range": [0, 1482]}, {"mediaId": 7, "range": [1482, 2900]}, {"mediaId": 3, "range": [60, 600]},
             {"mediaId": None, "range": [0, 10]}, {"kind": "book"}]
    assert meanings.planned(items) == [(7, 0.0, 1482.0), (3, 60.0, 600.0)]
