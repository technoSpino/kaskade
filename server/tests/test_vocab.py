import pytest

from kaskade import vocab

BANDS = [
    {"id": "b1", "from": 1, "to": 1000, "size": 800},
    {"id": "b2", "from": 1001, "to": 3000, "size": 1600},
]


def answers(b1_yes, b2_yes, pseudo_yes, n=10):
    out = [{"word": f"a{i}", "band": "b1", "yes": i < b1_yes} for i in range(n)]
    out += [{"word": f"b{i}", "band": "b2", "yes": i < b2_yes} for i in range(n)]
    out += [{"word": f"p{i}", "band": "pseudo", "yes": i < pseudo_yes} for i in range(n)]
    return out


@pytest.mark.parametrize("h, fa, expected", [
    (1.0, 0.0, 1.0),
    (0.5, 0.0, 0.5),
    (0.6, 0.2, 0.5),
    (0.1, 0.3, 0.0),   # clamped at 0
    (1.0, 1.0, 0.0),   # says yes to everything → no information
])
def test_corrected(h, fa, expected):
    assert vocab.corrected(h, fa) == pytest.approx(expected)


def test_perfect_answers_know_everything():
    r = vocab.score(answers(10, 10, 0), BANDS)
    assert r["estimate"] == 2400
    assert r["falseAlarmRate"] == 0
    assert r["reliable"] is True
    assert [b["corrected"] for b in r["bands"]] == [1.0, 1.0]


def test_false_alarms_reduce_estimate():
    honest = vocab.score(answers(8, 4, 0), BANDS)
    guessing = vocab.score(answers(8, 4, 3), BANDS)
    assert guessing["estimate"] < honest["estimate"]
    assert guessing["reliable"] is False  # 30 % false alarms


def test_core_share_only_counts_top_2000():
    # b1 fully known, b2 (ranks 1001–3000) half inside the top 2,000 and unknown.
    r = vocab.score(answers(10, 0, 0), BANDS)
    assert r["coreShare"] == pytest.approx(800 / (800 + 800))
    assert r["coreKnown"] == 1000


def test_yes_to_everything_scores_zero():
    r = vocab.score(answers(10, 10, 10), BANDS)
    assert r["estimate"] == 0


def test_build_test_has_bands_and_all_pseudowords():
    items = vocab.build_test(seed=1)
    data = vocab.pools()
    for band in data["bands"]:
        assert sum(i["band"] == band["id"] for i in items) == data["perBand"]
    assert sum(i["band"] == "pseudo" for i in items) == len(data["pseudowords"])
    assert len({i["word"] for i in items}) == len(items)


def test_build_test_is_shuffled_differently_per_seed():
    assert vocab.build_test(seed=1) != vocab.build_test(seed=2)
