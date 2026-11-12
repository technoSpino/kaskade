"""Content validation for data/practice (original B1-style items)."""
import json

import pytest

from kaskade import config

from .test_content_placement import no_empty_strings

LESEN = json.loads((config.CONTENT_DIR / "practice/lesen.json").read_text(encoding="utf-8"))["items"]
HOEREN = json.loads((config.CONTENT_DIR / "practice/hoeren.json").read_text(encoding="utf-8"))["items"]
ALL = LESEN + HOEREN


def test_four_items_each_and_unique_ids():
    assert len(LESEN) == 4 and len(HOEREN) == 4
    ids = [i["id"] for i in ALL]
    qids = [q["id"] for i in ALL for q in (i.get("questions") or i.get("situations"))]
    assert len(set(ids)) == len(ids) and len(set(qids)) == len(qids)


@pytest.mark.parametrize("item", ALL, ids=[i["id"] for i in ALL])
def test_item_well_formed(item):
    no_empty_strings(item)
    assert item["minutes"] > 0 and item["instructions"]
    kind = item["kind"]
    if kind == "zuordnung":
        ads = {a["id"] for a in item["ads"]}
        answers = [s["correct"] for s in item["situations"]]
        assert all(a in ads or a == "0" for a in answers)
        assert answers.count("0") >= 1
        used = [a for a in answers if a != "0"]
        assert len(used) == len(set(used)), "each ad matches at most one person"
        assert len(ads - set(used)) >= 1, "at least one distractor ad"
        return
    for q in item["questions"]:
        if "statement" in q:
            assert isinstance(q["correct"], bool)
        else:
            assert len(q["options"]) == 3 and q["correct"] in (0, 1, 2)
    if all("statement" in q for q in item["questions"]):
        values = [q["correct"] for q in item["questions"]]
        assert True in values and False in values, "mix of richtig and falsch"


@pytest.mark.parametrize("item", HOEREN, ids=[i["id"] for i in HOEREN])
def test_listening_scripts_are_tts_friendly(item):
    assert item["plays"] in (1, 2)
    for seg in item["script"]:
        assert seg["speaker"] in ("A", "B") and seg["name"]
        for bad in ("€", "%", "z. B.", "ca.", "Nr."):
            assert bad not in seg["text"], (bad, seg["text"][:60])
    if item["kind"] in ("gespraech", "radio"):
        assert {s["speaker"] for s in item["script"]} == {"A", "B"}
