"""Content validation for the core deck (data/core-deck/NNNN.json)."""
import json
import re

import pytest

from kaskade import config

DECK = config.CONTENT_DIR / "core-deck"
FIELDS = ("id", "n", "rank", "lemma", "pos", "display", "gloss", "sentence", "target", "en")
FOLD = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


@pytest.fixture(scope="module")
def batches():
    files = sorted(DECK.glob("[0-9][0-9][0-9][0-9].json"))
    assert files, "no merged deck batches — run scripts/merge_deck.py"
    return [(f.name, json.loads(f.read_text(encoding="utf-8"))) for f in files]


@pytest.fixture(scope="module")
def cards(batches):
    return [c for _, b in batches for c in b]


def fold(s: str) -> str:
    return s.lower().translate(FOLD)


def shares_stem(a: str, b: str, k: int = 3) -> bool:
    a, b = fold(a), fold(b)
    if len(a) < k or len(b) < k:
        return a[:2] in b or b[:2] in a
    return any(a[i:i + k] in b for i in range(len(a) - k + 1))


def test_at_least_2000_cards(cards):
    assert len(cards) >= 2000


def test_batches_are_numbered_and_full(batches):
    for i, (name, batch) in enumerate(batches, 1):
        assert name == f"{i:04d}.json"
        assert len(batch) == 100 or i == len(batches)
        assert batch[0]["n"] == (i - 1) * 100 + 1


def test_ids_and_order(cards):
    assert [c["n"] for c in cards] == list(range(1, len(cards) + 1))
    assert len({c["id"] for c in cards}) == len(cards)
    order = [c["order"] for c in cards]
    assert order == sorted(order)


def test_required_fields_non_empty(cards):
    for c in cards:
        for f in FIELDS:
            assert str(c.get(f, "")).strip(), f"card {c.get('n')}: empty {f}"
        if c.get("note") is not None:
            assert c["note"].strip(), f"card {c['n']}: empty note"


def test_no_duplicate_lemmas(cards):
    seen = {}
    for c in cards:
        assert c["lemma"] not in seen, f"{c['lemma']} in cards {seen.get(c['lemma'])} and {c['n']}"
        seen[c["lemma"]] = c["n"]


def test_ids_are_tied_to_rank(cards):
    for c in cards:
        assert c["id"] == f"core:r{c['rank']:05d}"


def test_no_duplicate_sentences(cards):
    seen = {}
    for c in cards:
        assert c["sentence"] not in seen, f"cards {seen.get(c['sentence'])} and {c['n']}: {c['sentence']}"
        seen[c["sentence"]] = c["n"]


def test_sentence_contains_target(cards):
    for c in cards:
        assert c["target"] in c["sentence"], f"card {c['n']}: {c['target']!r} not in sentence"


def test_target_is_a_form_of_the_lemma(cards):
    # Verbs and pronouns inflect irregularly (ist, gibt, griff, mir) — skip those.
    bad = [
        (c["n"], c["lemma"], c["target"]) for c in cards
        if c["pos"] in ("NOUN", "ADJ", "ADV", "ADP", "CCONJ", "SCONJ")
        and not shares_stem(c["lemma"].split()[0], c["target"])
    ]
    assert not bad, bad


def test_nouns_have_article_and_plural(cards):
    for c in cards:
        if c["pos"] != "NOUN":
            continue
        assert re.match(r"^(der|die|das) ", c["display"]), f"card {c['n']}: {c['display']}"
        assert "·" in c["display"] or "Plural" in c["display"], f"card {c['n']}: {c['display']}"
        assert c["lemma"][:1].isupper(), f"card {c['n']}: {c['lemma']}"


def test_case_badge_values(cards):
    assert {c.get("case") for c in cards} <= {None, "N", "A", "D", "G"}


def test_raw_files_validate_and_cover_every_rank():
    import importlib.util

    spec = importlib.util.spec_from_file_location("merge_deck", config.REPO_DIR / "server/scripts/merge_deck.py")
    merge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(merge)
    for f in sorted((DECK / "raw").glob("r*.json")):
        lo, hi = (int(x) for x in f.stem[1:].split("-"))
        entries = merge.load(f)
        assert [e["rank"] for e in entries] == list(range(lo, hi + 1)), f.name
        for e in entries:
            assert not merge.check_card(e), (f.name, e.get("rank"), merge.check_card(e))
    supplement = merge.load(DECK / "raw/supplement.json")
    for e in supplement:
        assert e["rank"] >= 90000 and e["count"] > 0
        assert not merge.check_card(e), (e["rank"], merge.check_card(e))


def test_sentences_are_sentences(cards):
    for c in cards:
        s = c["sentence"]
        assert s[0].isupper() or s[0] in "„\"", f"card {c['n']}"
        assert s[-1] in ".!?…“\"", f"card {c['n']}"
        assert "  " not in s and s == s.strip()
