"""#19: mined cards — the KI fills what the dictionary doesn't know (marked), edit, delete, one card per line."""
import pytest

from kaskade import ai, analyze, mining

LINE = "Wenn man überhetzt, versaust du dir nachher die Chance."


@pytest.fixture()
def fake_ai(monkeypatch):
    """The Claude call, mocked: records what was asked, answers like the real prompt asks."""
    calls = []
    answers = {
        "versaust": {"lemma": "versauen", "gloss": "to mess up, to ruin", "article": None, "plural": None,
                     "case": None, "caseReason": None},
        "überhetzt": {"lemma": "überhetzen", "gloss": "to rush (something) too much", "article": None,
                      "plural": None, "case": None, "caseReason": None},
        "Herrlichkeit": {"lemma": "Herrlichkeit", "gloss": "glory", "article": "die", "plural": "Herrlichkeiten",
                         "case": "N", "caseReason": "Teil des Subjekts → Nominativ"},
    }
    monkeypatch.setattr(ai, "available", lambda: True)

    def word_info(sentence, target):
        calls.append((sentence, target))
        return answers.get(target)

    monkeypatch.setattr(ai, "word_info", word_info)
    monkeypatch.setattr(analyze, "known_lemma", lambda lemma: lemma in {"versauen", "Chance", "Wetter"})
    return calls


def mine(client, **kw):
    body = {"sentence": LINE, "target": "überhetzt", "lemma": "überhetzen", "display": "überhetzen", "gloss": "",
            "source": "Schauen · Tatort", **kw}
    return client.post("/api/mined", json=body).json()


def card(client, cid):
    return next(c for c in client.get("/api/mined").json() if c["id"] == cid)


def test_missing_gloss_is_filled_by_ai_and_marked(client, fake_ai):
    r = mine(client)
    assert r["duplicate"] is False and r["ai"] == ["lemma", "gloss"]  # lemma unknown to the dictionary, no gloss
    c = card(client, r["id"])
    assert c["gloss"] == "to rush (something) too much" and c["lemma"] == "überhetzen"
    assert c["aiFields"] == ["lemma", "gloss"]
    assert fake_ai == [(LINE, "überhetzt")]


def test_unknown_lemma_is_corrected_by_ai(client, fake_ai):
    r = mine(client, target="versaust", lemma="versausen", display="versauen", gloss="to mess up")
    c = card(client, r["id"])
    assert c["lemma"] == "versauen" and c["display"] == "versauen" and c["gloss"] == "to mess up"
    assert c["aiFields"] == ["lemma"]  # the dictionary's gloss stays, unmarked


def test_known_word_with_gloss_never_asks_the_ai(client, fake_ai):
    r = mine(client, target="Chance", lemma="Chance", display="die Chance · die Chancen", gloss="chance", case="A")
    assert r["ai"] == [] and fake_ai == []
    assert card(client, r["id"])["aiFields"] == []


def test_ai_case_with_reason_only_when_the_parser_gave_none(client, fake_ai):
    s = "Denn dein ist das Reich und die Kraft und die Herrlichkeit, in Ewigkeit."
    r = client.post("/api/mined", json={"sentence": s, "target": "Herrlichkeit", "lemma": "Herrlichkeit",
                                        "display": "Herrlichkeit", "gloss": ""}).json()
    c = card(client, r["id"])
    assert c["case"] == "N" and c["note"] == "Teil des Subjekts → Nominativ"
    assert c["display"] == "die Herrlichkeit · die Herrlichkeiten"
    assert set(c["aiFields"]) == {"lemma", "gloss", "case"}


def test_without_a_key_mining_keeps_the_dictionary_data(client, monkeypatch):
    monkeypatch.setattr(analyze, "known_lemma", lambda lemma: False)
    assert ai.available() is False and ai.word_info(LINE, "versaust") is None
    r = mine(client)
    c = card(client, r["id"])
    assert c["gloss"] == "—" and c["aiFields"] == [] and r["ai"] == []


def test_ai_answers_are_validated(monkeypatch):
    class Msg:
        def __init__(self, text):
            self.content = [type("B", (), {"text": text})()]

    answer = {"text": ""}

    class Client:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kw):
                assert "versaust" in kw["messages"][0]["content"]
                return Msg(answer["text"])

    monkeypatch.setattr(ai, "available", lambda: True)
    monkeypatch.setattr(ai, "_client", lambda: Client)
    answer["text"] = '{"lemma": "versauen", "gloss": "to mess up", "article": "dem", "plural": null, "case": "X", "caseReason": "egal"}'
    assert ai.word_info(LINE, "versaust") == {"lemma": "versauen", "gloss": "to mess up", "article": None,
                                              "plural": None, "case": None, "caseReason": None}
    answer["text"] = "Das weiß ich nicht."
    assert ai.word_info(LINE, "versaust") is None


def test_same_line_again_says_so_and_adds_a_second_word(client, fake_ai):
    first = mine(client)
    again = mine(client)
    assert again == {"id": first["id"], "duplicate": True, "sameWord": True}
    other = mine(client, target="versaust", lemma="versausen", display="versauen", gloss="to mess up")
    assert other == {"id": first["id"], "duplicate": True, "sameWord": False}
    n = first["id"].split(":")[1]
    c = client.post(f"/api/mined/{n}/words", json={"sentence": LINE, "target": "versaust", "lemma": "versausen",
                                                    "display": "versauen", "gloss": "to mess up"}).json()
    assert [w["target"] for w in c["words"]] == ["versaust"]
    assert c["words"][0]["lemma"] == "versauen" and c["words"][0]["ai"] == ["lemma"]
    assert client.post(f"/api/mined/{n}/words", json={"sentence": LINE, "target": "versaust", "lemma": "x"}).status_code == 409
    assert client.post(f"/api/mined/{n}/words", json={"sentence": LINE, "target": "Kaffee", "lemma": "x"}).status_code == 422
    assert len(client.get("/api/mined").json()) == 1


def test_edit_a_mined_card_clears_the_ki_mark(client, fake_ai):
    r = mine(client)
    n = r["id"].split(":")[1]
    c = client.patch(f"/api/mined/{n}", json={"gloss": "to rush", "case": "A", "note": "  "}).json()
    assert c["gloss"] == "to rush" and c["case"] == "A" and c["note"] is None
    assert c["aiFields"] == ["lemma"]  # he wrote the gloss himself now
    c = client.patch(f"/api/mined/{n}", json={"lemma": "überhetzen", "display": "überhetzen", "case": None}).json()
    assert c["aiFields"] == [] and c["case"] is None
    assert client.patch(f"/api/mined/{n}", json={"case": "X"}).status_code == 422
    assert client.patch("/api/mined/999", json={"gloss": "x"}).status_code == 404


def test_delete_a_mined_card_with_its_schedule(client, fake_ai):
    from kaskade import config
    r = mine(client)
    n = int(r["id"].split(":")[1])
    assert client.post(f"/api/cards/{r['id']}/review", json={"rating": 3}).status_code == 200
    config.SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
    (config.SNIPPETS_DIR / "mine-1.m4a").write_bytes(b"x")
    from kaskade import db
    with db.tx() as conn:
        conn.execute("UPDATE mined SET audio = 'mine-1.m4a' WHERE id = ?", (n,))
    assert client.delete(f"/api/mined/{n}").json() == {"ok": True}
    assert client.get("/api/mined").json() == []
    assert client.get("/api/cards/stats").json()["mined"] == 0
    assert not (config.SNIPPETS_DIR / "mine-1.m4a").exists()
    assert client.delete(f"/api/mined/{n}").status_code == 404
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM review_log WHERE card_id = ?", (r["id"],)).fetchone()[0] == 0
    assert mining.row(n) is None


def test_case_rule_no_badge_rather_than_a_wrong_one(client):
    pytest.importorskip("spacy")
    r = analyze.analyze("Denn dein ist das Reich und die Kraft und die Herrlichkeit, in Ewigkeit.")
    shown = {" ".join(t["text"] for t in r["tokens"][c["start"]:c["end"]]): c["case"] for c in r["chunks"]}
    assert "die Herrlichkeit" not in shown and "die Kraft" not in shown  # parser says Acc, role says subject
    assert shown["das Reich"] == "N"
    r = analyze.analyze("Vergib uns unsere Schuld, wie wir vergeben unseren Schuldigern.")
    shown = {" ".join(t["text"] for t in r["tokens"][c["start"]:c["end"]]): c["case"] for c in r["chunks"]}
    assert shown["unseren Schuldigern"] == "D" and "unsere Schuld" not in shown  # oa but parsed Nom → none
    r = analyze.analyze("Wir fahren mit dem Hund und der Katze in die Stadt.")
    shown = {" ".join(t["text"] for t in r["tokens"][c["start"]:c["end"]]): c["case"] for c in r["chunks"]}
    assert shown["dem Hund"] == "D" and shown["die Stadt"] == "A"


def test_dictionary_headword_and_noun_cards(client):
    pytest.importorskip("spacy")
    r = analyze.analyze("Denn dein ist das Reich.")
    reich = next(t for t in r["tokens"] if t["text"] == "Reich")
    assert reich["entry"] is None or reich["entry"]["lemma"] == "Reich"  # never the adjective card "reich"
