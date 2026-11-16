"""Content validation for the reading library (data/texts)."""
import json

import pytest

from kaskade import config

from .test_content_placement import no_empty_strings

FILES = sorted((config.CONTENT_DIR / "texts").glob("t*.json"))
TEXTS = [json.loads(f.read_text(encoding="utf-8")) for f in FILES]


def test_library_size():
    assert len(TEXTS) >= 20


def test_ids_match_files_and_are_unique():
    assert [t["id"] for t in TEXTS] == [f.stem for f in FILES]


@pytest.mark.parametrize("t", TEXTS, ids=[t["id"] for t in TEXTS])
def test_text_schema(t):
    no_empty_strings(t)
    assert t["level"] in ("A2+", "B1")
    assert t["slot"] in ("input", "lesen")
    assert 150 <= len(t["text"].split()) <= 350
    assert len(t["text"].split("\n\n")) >= 3
    for g in t["glossary"]:
        assert g["term"] in t["text"], g["term"]
        assert g["gloss"]
    assert len(t["questions"]) == 3
    for q in t["questions"]:
        assert q["question"].endswith("?") and len(q["options"]) == 3 and 0 <= q["correct"] < 3


def test_both_slots_and_levels_present():
    assert {t["slot"] for t in TEXTS} == {"input", "lesen"}
    assert {t["level"] for t in TEXTS} == {"A2+", "B1"}


@pytest.mark.parametrize("t", TEXTS, ids=[t["id"] for t in TEXTS])
def test_at_most_5_percent_outside_top_2000(t):
    textcov = pytest.importorskip("kaskade.textcov")
    pytest.importorskip("spacy")
    names = set(t.get("names", []))  # names spaCy doesn't recognise as names
    r = textcov.coverage(t["text"], extra_known=names)
    assert r["coverage"] >= 0.95, sorted(set(r["unknown"]))
    # every word outside the core is explained in the glossary (names excepted)
    terms = {g["term"].lower() for g in t["glossary"]}
    missing = [w for w in set(r["unknown"]) if w.lower() not in terms]
    assert not missing, missing
