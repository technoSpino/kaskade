import pytest

from kaskade import placement


@pytest.mark.parametrize("b1, b2, level", [
    (5, 5, "B2"), (4, 4, "B2"), (4, 3, "B1+"), (5, 2, "B1"), (4, 0, "B1"),
    (3, 5, "A2+"), (2, 5, "A2"), (0, 0, "A2"),
])
def test_reading_level(b1, b2, level):
    assert placement.reading_level(b1, b2) == level


def test_score_reading_uses_answer_key():
    key = {q["id"]: q["correct"] for t in placement.reading_texts()["texts"] for q in t["questions"]}
    perfect = placement.score_reading(key)
    assert (perfect["b1"], perfect["b2"], perfect["level"]) == (5, 5, "B2")
    wrong = {qid: (c + 1) % 3 for qid, c in key.items()}
    assert placement.score_reading(wrong)["b1"] == 0
    assert placement.score_reading({})["level"] == "A2"


def test_public_reading_hides_answers():
    for t in placement.reading_public():
        for q in t["questions"]:
            assert "correct" not in q and "explanation" not in q


@pytest.mark.parametrize("coverage, ctype, level", [
    (None, None, None), (85, "adult", "B1"), (70, "adult", "A2+"), (40, "adult", "A2"),
    (80, "simple", "A2"), (50, "simple", "A1"),
])
def test_listening_level(coverage, ctype, level):
    assert placement.listening_level(coverage, ctype) == level


def test_start_hours_monotonic_in_coverage():
    hours = [placement.start_hours("2A", c) for c in (50, 60, 70, 79)]
    assert hours == sorted(hours)
    assert placement.start_hours("1", None) < placement.start_hours("2A", None) < placement.start_hours("2B", 90)


def test_result_from_full_state():
    state = {
        "vocab": {"result": {"estimate": 1700, "coreKnown": 1300, "coreShare": 0.65}},
        "reading": {"result": {"b1": 5, "b2": 3, "level": "B1+"}},
        "satzcheck": {"result": {"coverage": 78, "contentType": "adult", "verdict": {"phase": "2A", "title": "x"}}},
        "writing": {"text": "Liebe Jana", "writingId": 1, "grade": None},
        "speaking": {"recordings": [1, 2, 3]},
    }
    r = placement.result(state)
    assert r["phase"] == "2A" and r["words"] == 1700 and r["coreKnown"] == 1300
    assert r["skills"] == {"lesen": "B1+", "hoeren": "A2+", "schreiben": None, "sprechen": None}
    assert "ohne KI" in r["notes"]["schreiben"]
    assert r["notes"]["sprechen"].startswith("3 Aufnahmen")


def test_result_without_satzcheck_uses_vocab():
    assert placement.result({"vocab": {"result": {"estimate": 600, "coreKnown": 500, "coreShare": 0.3}}})["phase"] == "1"
    assert placement.result({})["phase"] == "2A"
    assert placement.result({})["notes"]["sprechen"] == "übersprungen"
