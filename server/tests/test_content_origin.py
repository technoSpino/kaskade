"""Every content item says where it comes from: AI-written for Kaskade, or real German with a source (#16)."""
import json

import pytest

from kaskade import config
from kaskade.origin import ORIGINS

DATA = config.CONTENT_DIR


def load(rel: str):
    return json.loads((DATA / rel).read_text(encoding="utf-8"))


def content_items():
    """(label, item) for every AI-or-real content item outside the plan files."""
    for f in sorted((DATA / "core-deck").glob("[0-9][0-9][0-9][0-9].json")):
        for c in json.loads(f.read_text(encoding="utf-8")):
            yield f"deck {c['id']}", c
    for f in sorted((DATA / "texts").glob("t*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        yield f"text {t['id']}", t
    for t in load("placement/reading.json")["texts"]:
        yield f"placement reading {t['id']}", t
    tasks = load("placement/tasks.json")
    yield f"placement writing {tasks['writing']['id']}", tasks["writing"]
    for s in tasks["speaking"]:
        yield f"placement speaking {s['id']}", s
    for module in ("lesen", "hoeren"):
        for it in load(f"practice/{module}.json")["items"]:
            yield f"practice {module} {it['id']}", it


ITEMS = list(content_items())


def test_there_is_content():
    assert len(ITEMS) > 2000


@pytest.mark.parametrize("label,item", ITEMS[:1] + [i for i in ITEMS if not i[0].startswith("deck")])
def test_item_has_origin(label, item):
    assert item.get("origin") in ORIGINS, f"{label}: origin missing"
    if item["origin"] == "real":
        assert str(item.get("source", "")).strip(), f"{label}: real items need a source"


def test_every_deck_card_has_origin():
    bad = [label for label, c in ITEMS if label.startswith("deck") and c.get("origin") not in ORIGINS]
    assert bad == []


def test_raw_deck_cards_default_to_ai_and_real_ones_need_a_source():
    import sys
    sys.path.insert(0, str(config.REPO_DIR / "server" / "scripts"))
    from merge_deck import check_card

    card = {"rank": 1, "lemma": "Zeit", "pos": "NOUN", "display": "die Zeit · die Zeiten", "gloss": "time",
            "sentence": "Ich habe keine Zeit.", "target": "Zeit", "en": "I have no time.", "case": None}
    assert check_card(card) == []
    assert check_card({**card, "origin": "real"}) != []
    assert check_card({**card, "origin": "real", "source": "Tatort: Schweigen"}) == []
    assert check_card({**card, "origin": "kaskade"}) != []
