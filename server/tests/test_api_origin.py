"""The APIs pass on where content comes from (origin ai/real + source), incl. mined cards (#16)."""
from kaskade import origin, texts

from .test_api_watch import upload

MINE = {"target": "Abend", "lemma": "Abend", "gloss": "evening"}


def mine(client, sentence, source, **extra):
    r = client.post("/api/mined", json={**MINE, "sentence": sentence, "source": source, **extra})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def mined_by_id(client):
    return {c["id"]: c for c in client.get("/api/mined").json()}


def test_library_texts_are_ai_written(client):
    lst = client.get("/api/texts").json()
    assert lst and all(t["origin"] == "ai" and t["source"] is None for t in lst)
    assert client.get(f"/api/texts/{lst[0]['id']}").json()["origin"] == "ai"


def test_placement_and_practice_items_carry_origin(client):
    c = client.get("/api/placement/content").json()
    assert all(t["origin"] == "ai" for t in c["reading"])
    assert c["writing"]["origin"] == "ai" and all(s["origin"] == "ai" for s in c["speaking"])
    ov = client.get("/api/practice").json()
    assert all(i["origin"] == "ai" for m in ("lesen", "hoeren", "schreiben") for i in ov[m])
    first = ov["hoeren"][0]["id"]
    assert client.get(f"/api/practice/hoeren/{first}").json()["origin"] == "ai"


def test_core_deck_card_is_ai(client):
    card = client.get("/api/cards/next").json()["card"]
    assert card["n"] == 1 and card["origin"] == "ai" and card["originSource"] is None


def test_mined_cards_keep_the_origin_of_their_source(client):
    title = texts.library()[0]["title"]
    from_text = mine(client, "Am Abend lese ich.", f"Lesen · {title}")
    own = mine(client, "Der Abend war lang.", "Eigener Text")
    check = mine(client, "Wo waren Sie gestern Abend?", "Satz-Check · Tatort: Schweigen")
    clip = upload(client, title="Tatort: Schweigen (NDR)")
    watched = mine(client, "Guten Abend, Herr Kommissar.", "Schauen · egal", mediaId=clip["id"], start=0.5, end=2.0)
    cards = mined_by_id(client)
    assert (cards[from_text]["origin"], cards[from_text]["originSource"]) == ("ai", None)
    assert (cards[own]["origin"], cards[own]["originSource"]) == ("real", "Eigener Text")
    assert (cards[check]["origin"], cards[check]["originSource"]) == ("real", "Tatort: Schweigen")
    # cut from a clip: the clip's title is the source
    assert (cards[watched]["origin"], cards[watched]["originSource"]) == ("real", "Tatort: Schweigen (NDR)")
    # the next card (mined first) carries it too
    nxt = client.get("/api/cards/next").json()["card"]
    assert nxt["id"] == from_text and nxt["origin"] == "ai"


def test_of_mined_rules():
    lib = {"Ein Text": {"origin": "real", "source": "Autorin, Buch"}}
    assert origin.of_mined("Lesen · Ein Text", None, lib) == {"origin": "real", "source": "Autorin, Buch"}
    assert origin.of_mined("Lesen · Unbekannt", None, lib) == {"origin": "ai", "source": None}
    assert origin.of_mined("Lesen", None, lib)["origin"] == "ai"
    assert origin.of_mined("Schauen", None, lib) == {"origin": "real", "source": "Schauen"}
    assert origin.of_mined(None, None, lib) == {"origin": None, "source": None}
