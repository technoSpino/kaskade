import pytest

pytest.importorskip("spacy")
textcov = pytest.importorskip("kaskade.textcov")


def test_core_words_and_inflections_are_known():
    r = textcov.coverage("Ich muss heute arbeiten, aber viele Leute haben am Mittwoch frei. Das passt mir gut.")
    assert r["unknown"] == [] and r["coverage"] == 1.0


def test_rare_words_are_reported():
    r = textcov.coverage("Der Schornsteinfeger inspiziert die Dachrinne.")
    assert "Schornsteinfeger" in r["unknown"]
    assert r["coverage"] < 1.0


def test_names_and_numbers_do_not_count():
    r = textcov.coverage("Frau Schmidt wohnt seit 2019 in Hamburg.")
    assert r["unknown"] == []
    assert r["tokens"] == 4  # Frau, wohnt, seit, in


def test_compounds_of_known_words_count_as_known():
    assert textcov.coverage("Die Haustür ist offen.")["unknown"] == []


def test_empty_text():
    assert textcov.coverage("")["coverage"] == 1.0
