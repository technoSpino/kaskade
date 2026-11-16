"""Content validation for data/placement."""
import json

import pytest

from kaskade import config

DIR = config.CONTENT_DIR / "placement"


@pytest.fixture(scope="module")
def reading():
    return json.loads((DIR / "reading.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tasks():
    return json.loads((DIR / "tasks.json").read_text(encoding="utf-8"))


def no_empty_strings(obj, path="$"):
    if isinstance(obj, str):
        assert obj.strip(), f"empty string at {path}"
    elif isinstance(obj, dict):
        for k, v in obj.items():
            no_empty_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            no_empty_strings(v, f"{path}[{i}]")


def test_no_empty_strings(reading, tasks):
    no_empty_strings(reading)
    no_empty_strings(tasks)


@pytest.mark.parametrize("tid, lo, hi", [("b1", 220, 320), ("b2", 330, 440)])
def test_reading_text_lengths(reading, tid, lo, hi):
    t = next(t for t in reading["texts"] if t["id"] == tid)
    assert lo <= len(t["text"].split()) <= hi


def test_reading_questions_well_formed(reading):
    ids = set()
    for t in reading["texts"]:
        assert len(t["questions"]) == 5
        positions = set()
        for q in t["questions"]:
            assert q["id"].startswith(t["id"]) and q["id"] not in ids
            ids.add(q["id"])
            assert len(q["options"]) == 3 and len(set(q["options"])) == 3
            assert 0 <= q["correct"] < 3
            positions.add(q["correct"])
            assert q["question"].endswith("?")
        assert len(positions) >= 2, "correct answers should not all be in the same position"


def test_tasks_well_formed(tasks):
    w = tasks["writing"]
    assert len(w["points"]) == 3 and w["words"] > 0
    assert len(tasks["speaking"]) == 3
    assert len({s["id"] for s in tasks["speaking"]}) == 3
