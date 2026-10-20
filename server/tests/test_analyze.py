import pytest

pytest.importorskip("spacy")
from kaskade import analyze  # noqa: E402


def chunks(text):
    r = analyze.analyze(text)
    return [(" ".join(t["text"] for t in r["tokens"][c["start"]:c["end"]]), c["case"], c["explain"]) for c in r["chunks"]]


def test_prepositions_govern_case(client):
    c = chunks("Ich spreche mit meinem Vermieter über die Heizung.")
    assert ("meinem Vermieter", "D", "mit + Dativ") in c
    assert any(t == "die Heizung" and k == "A" and "Wechselpräposition" in e for t, k, e in c)


def test_objects_and_subject(client):
    c = chunks("Ich gebe dem Kind einen Apfel.")
    assert ("Ich", "N", "Subjekt → Nominativ") in c
    assert ("dem Kind", "D", "Dativobjekt von „geben“") in c
    assert ("einen Apfel", "A", "Akkusativobjekt von „geben“") in c


def test_genitive_and_contraction(client):
    c = chunks("Wegen des Streiks bleibe ich im Haus.")
    assert ("des Streiks", "G", "wegen + Genitiv") in c
    assert any(e.startswith("im (in dem) + Dativ") for _, _, e in c)


def test_explain_labels():
    assert analyze.explain("D", {"kind": "prep", "word": "zum", "role": "prep"}) == "zum (zu dem) + Dativ"
    assert analyze.explain("A", None) == "Akkusativ"
    assert analyze.explain("G", {"kind": "word", "word": "Haus", "role": "ag"}) == "Genitivattribut (wessen?)"


def test_word_state_rules():
    states = {"core:r1": "lernend"}
    assert analyze.word_state(None, states, 500) == "neu"
    assert analyze.word_state({"id": "core:r1", "n": 1}, states, 500) == "lernend"
    assert analyze.word_state({"id": "core:r2", "n": 300}, states, 500) == "bekannt"
    assert analyze.word_state({"id": "core:r3", "n": 800}, states, 500) == "neu"
    assert analyze.word_state({"id": "mine:1", "n": None}, {}, 500) == "neu"


def test_word_states_follow_cards(client, monkeypatch):
    from kaskade import srs
    monkeypatch.setattr(analyze, "core_known_estimate", lambda: 0)
    card = next(c for c in srs.deck() if c["lemma"] == "Problem")
    r = analyze.analyze("Das Problem ist groß.")
    tok = next(t for t in r["tokens"] if t["text"] == "Problem")
    assert tok["state"] == "neu" and tok["entry"]["cardId"] == card["id"]
    srs.review(card["id"], 3)
    tok = next(t for t in analyze.analyze("Das Problem ist groß.")["tokens"] if t["text"] == "Problem")
    assert tok["state"] == "lernend"
    srs.mark_known(next(c for c in srs.deck() if c["lemma"] == "groß")["id"])
    tok = next(t for t in analyze.analyze("Das Problem ist groß.")["tokens"] if t["text"] == "groß")
    assert tok["state"] == "bekannt"


def test_function_words_have_no_state(client):
    r = analyze.analyze("Ich bin mit dir.")
    assert all(t["state"] is None for t in r["tokens"] if t["pos"] in ("PRON", "AUX", "ADP"))


# ── #34: separable verbs (all sentences invented) ──

def word(r, text):
    return next(t for t in r["tokens"] if t["text"] == text)


@pytest.mark.parametrize("text, verb, particle, lemma", [
    ("Mir fällt nichts ein.", "fällt", "ein", "einfallen"),
    ("Er lud uns zum Essen ein.", "lud", "ein", "einladen"),
    ("Wann fängt der Film an?", "fängt", "an", "anfangen"),
    ("Gestern fielen mir zwei Hunde im Park auf.", "fielen", "auf", "auffallen"),
])
def test_a_split_off_prefix_makes_the_particle_verb_on_both_words(client, text, verb, particle, lemma):
    r = analyze.analyze(text)
    v, p = word(r, verb), word(r, particle)
    assert v["entry"] == p["entry"] and v["entry"]["lemma"] == lemma and v["lemma"] == p["lemma"] == lemma
    assert v["entry"]["target"] == verb and v["entry"]["split"] == f"{verb} … {particle}"
    assert v["pair"] == p["i"] and p["pair"] == v["i"]
    assert v["state"] == p["state"] is not None


def test_einfallen_shows_its_principal_parts(client):
    entry = word(analyze.analyze("Mir fällt nichts ein."), "ein")["entry"]
    assert entry["display"] == "einfallen · fiel ein · ist eingefallen" and entry["cardId"]


def test_an_article_at_the_end_of_a_cut_line_stays_an_article(client):
    """spaCy calls the article an svp here — but not a PTKVZ: no *einkommen*, though it is a dictionary verb."""
    doc = analyze.nlp()("Wir warteten lange und dann kam ein")
    assert [(t.tag_, t.dep_) for t in doc if t.text == "ein"] == [("ART", "svp")]
    r = analyze.analyze("Wir warteten lange und dann kam ein")
    assert word(r, "kam")["entry"]["lemma"] == "kommen" and "pair" not in word(r, "kam")
    assert word(r, "ein")["entry"]["lemma"] == "ein" and "pair" not in word(r, "ein")


def test_no_join_when_the_particle_verb_is_no_headword(client):
    """The parser's false pair: *wiedertrainieren* is neither a card nor in the dictionary."""
    r = analyze.analyze("Du trainierst morgen wieder.")
    assert "pair" not in word(r, "wieder") and "pair" not in word(r, "trainierst")
    assert word(r, "wieder")["lemma"] == "wieder"


def test_a_line_is_analysed_inside_its_sentence(client):
    """Verb on line 1, prefix on line 2: each line's own words come back, parsed as one sentence."""
    line1, line2 = "Mir fällt bei diesem Wetter", "wirklich nichts mehr ein."
    text = f"{line1} {line2}"
    alone = analyze.analyze(line2)
    assert word(alone, "ein")["entry"]["lemma"] != "einfallen"  # the cut line alone: no verb to join
    first = analyze.analyze(text, (0, len(line1)))
    second = analyze.analyze(text, (len(line1) + 1, len(text)))
    assert [t["text"] for t in first["tokens"]] == ["Mir", "fällt", "bei", "diesem", "Wetter"]
    assert [t["text"] for t in second["tokens"]] == ["wirklich", "nichts", "mehr", "ein", "."]
    assert word(first, "fällt")["entry"]["lemma"] == word(second, "ein")["entry"]["lemma"] == "einfallen"
    assert word(second, "ein")["pair"] == word(first, "fällt")["i"]
