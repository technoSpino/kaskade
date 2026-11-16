"""Content validation for data/freq and data/vocab-test."""
import json

import pytest

from kaskade import config

FREQ = config.CONTENT_DIR / "freq/lemmas.tsv"
POOLS = config.CONTENT_DIR / "vocab-test/pools.json"


@pytest.fixture(scope="module")
def lemma_rows():
    lines = FREQ.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "rank\tlemma\tpos\tcount\tforms"
    return [line.split("\t") for line in lines[1:]]


@pytest.fixture(scope="module")
def pools():
    return json.loads(POOLS.read_text(encoding="utf-8"))


def ranks_of(word, rows):
    """All ranks where `word` is the lemma or one of the listed forms."""
    w = word.lower()
    return [int(r[0]) for r in rows if r[1].lower() == w or w in r[4].split(",")]


def test_lemma_list_is_ranked_and_unique(lemma_rows):
    assert len(lemma_rows) > 10000
    ranks = [int(r[0]) for r in lemma_rows]
    assert ranks == list(range(1, len(ranks) + 1))
    counts = [int(r[3]) for r in lemma_rows]
    assert counts == sorted(counts, reverse=True)
    lemmas = [r[1] for r in lemma_rows]
    assert len(lemmas) == len(set(lemmas))
    assert all(lemma.strip() for lemma in lemmas)


def test_frequency_licence_is_documented():
    readme = (config.CONTENT_DIR / "freq/README.md").read_text(encoding="utf-8")
    assert "CC BY-SA 4.0" in readme and "OpenSubtitles" in readme


def test_bands_are_contiguous(pools):
    bands = pools["bands"]
    assert bands[0]["from"] == 1
    for a, b in zip(bands, bands[1:]):
        assert b["from"] == a["to"] + 1
    assert bands[-1]["to"] == 8000
    for band in bands:
        assert 0 < band["size"] <= band["to"] - band["from"] + 1
        assert len(band["words"]) >= pools["perBand"]


def test_pool_words_lie_in_their_band(pools, lemma_rows):
    wrong = []
    for band in pools["bands"]:
        for w in band["words"]:
            ranks = ranks_of(w, lemma_rows)
            if not any(band["from"] <= r <= band["to"] for r in ranks):
                wrong.append((band["id"], w, ranks[:3]))
    assert not wrong, wrong


def test_pool_words_are_unique(pools):
    words = [w for b in pools["bands"] for w in b["words"]] + pools["pseudowords"]
    assert len(words) == len({w.lower() for w in words})


def test_pseudowords_are_not_in_frequency_list(pools, lemma_rows):
    hits = [w for w in pools["pseudowords"] if ranks_of(w, lemma_rows)]
    assert not hits, hits
    assert len(pools["pseudowords"]) >= 25
