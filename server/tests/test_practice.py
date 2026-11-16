from kaskade import practice

RF = {"id": "x", "questions": [{"id": "q1", "statement": "…", "correct": True},
                               {"id": "q2", "statement": "…", "correct": False},
                               {"id": "q3", "statement": "…", "correct": True}]}
MC = {"id": "y", "questions": [{"id": "m1", "question": "?", "options": ["a", "b", "c"], "correct": 2}]}
ZU = {"id": "z", "ads": [{"id": "a"}, {"id": "b"}],
      "situations": [{"id": "s1", "text": "…", "correct": "a"}, {"id": "s2", "text": "…", "correct": "0"}]}


def test_score_richtig_falsch():
    r = practice.score(RF, {"q1": True, "q2": True, "q3": True})
    assert (r["points"], r["total"], r["pct"]) == (2, 3, 0.667) and r["passed"] is True
    assert [x["ok"] for x in r["review"]] == [True, False, True]


def test_score_mc_and_missing_answers():
    assert practice.score(MC, {"m1": 2})["points"] == 1
    r = practice.score(MC, {})
    assert r["points"] == 0 and r["passed"] is False and r["review"][0]["given"] is None


def test_score_zuordnung_including_none():
    r = practice.score(ZU, {"s1": "a", "s2": "0"})
    assert r["points"] == 2
    assert practice.score(ZU, {"s1": "b", "s2": "a"})["points"] == 0


def test_pass_mark_is_60_percent():
    five = {"id": "f", "questions": [{"id": f"q{i}", "correct": True} for i in range(5)]}
    assert practice.score(five, {f"q{i}": True for i in range(3)})["passed"] is True   # 60 %
    assert practice.score(five, {f"q{i}": True for i in range(2)})["passed"] is False  # 40 %


def test_public_hides_answers_and_transcript():
    item = {**RF, "script": [{"speaker": "A", "text": "Hallo"}]}
    p = practice.public(item)
    assert "script" not in p and all("correct" not in q for q in p["questions"])
    assert all("correct" not in s for s in practice.public(ZU)["situations"])


def test_self_check():
    r = practice.self_check({"aufgabe": True, "anrede": True, "konnektoren": True, "verbstellung": False})
    assert (r["points"], r["total"], r["passed"]) == (3, 4, True)
    assert practice.self_check({})["pct"] == 0


def test_readiness_uses_last_three_attempts():
    a = [
        {"module": "lesen", "points": 1, "total": 5, "created_at": "2026-10-01"},
        {"module": "lesen", "points": 4, "total": 5, "created_at": "2026-10-02"},
        {"module": "lesen", "points": 3, "total": 5, "created_at": "2026-10-03"},
        {"module": "lesen", "points": 5, "total": 5, "created_at": "2026-10-04"},
        {"module": "hoeren", "points": 2, "total": 5, "created_at": "2026-10-04"},
    ]
    r = practice.readiness(a)
    assert r["lesen"] == {"attempts": 4, "latest": 1.0, "average": 0.8, "passed": True}
    assert r["hoeren"]["passed"] is False
    assert r["schreiben"] == {"attempts": 0, "latest": None, "average": None, "passed": None}
