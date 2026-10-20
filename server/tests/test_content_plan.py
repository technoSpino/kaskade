"""Content validation for data/plan."""
import json

from kaskade import config

from .test_content_placement import no_empty_strings

PLAN = json.loads((config.CONTENT_DIR / "plan/weeks-1-4.json").read_text(encoding="utf-8"))
PLAN_2B = json.loads((config.CONTENT_DIR / "plan/phase-2b.json").read_text(encoding="utf-8"))


def test_no_empty_strings():
    no_empty_strings({k: v for k, v in PLAN.items() if k != "weeks"})
    for w in PLAN["weeks"]:
        for d in w["days"]:
            no_empty_strings(d)


def test_block_matches_phase_2a_schedule():
    """#27: no exam block — freies Lesen runs 10:35–11:30."""
    assert [(b["start"], b["minutes"]) for b in PLAN["block"]] == [
        ("09:00", 30), ("09:30", 55), ("10:25", 10), ("10:35", 55)]


def test_four_weeks_of_five_days():
    assert [w["week"] for w in PLAN["weeks"]] == [1, 2, 3, 4]
    for w in PLAN["weeks"]:
        assert [d["day"] for d in w["days"]] == ["Mo", "Di", "Mi", "Do", "Fr"]


def test_no_exam_in_the_plan_but_all_prompts_kept():
    """#27: no exam date yet — no exam field on any day; the 16 prompts stay for the Prüfung page."""
    for plan in (PLAN, PLAN_2B):
        for w in plan["weeks"]:
            for d in w["days"]:
                assert "exam" not in d and all(m["block"] != "pruefung" for m in d["materials"]), d["day"]
        assert all(b["kind"] != "pruefung" for b in plan["block"])
    assert len(PLAN["prompts"]) == 16 and len({p["id"] for p in PLAN["prompts"]}) == 16


def test_prompts_well_formed():
    for p in PLAN["prompts"]:
        assert p["skill"] in ("schreiben", "sprechen")
        assert 3 <= len(p["points"]) <= 5 and p["tips"]
        if p["skill"] == "schreiben":
            assert 30 <= p["words"] <= 120
    types = {p["type"] for p in PLAN["prompts"]}
    assert len(types) >= 5


def test_no_mock_exam_and_no_week5_todo_pointing_to_it():
    """#27: the week-6 mock exam is parked ("Später" in TASK.md), and so is week 5's text about it."""
    assert "week6" not in PLAN and "week5" not in PLAN
    assert "Probetest" not in json.dumps(PLAN, ensure_ascii=False) and "Probeprüfung" not in json.dumps(PLAN, ensure_ascii=False)


# ── Phase 2B plan ──────────────────────────────────────────────────────────


def test_2b_block_is_contiguous_with_less_core_deck_time():
    blocks = PLAN_2B["block"]
    assert [(b["start"], b["minutes"]) for b in blocks] == [
        ("09:00", 15), ("09:15", 65), ("10:20", 10), ("10:30", 60)]
    # same ids/kinds as 2A, so timers, "Fertig" and week totals carry over
    assert [(b["id"], b["kind"]) for b in blocks] == [(b["id"], b["kind"]) for b in PLAN["block"]]
    t = 9 * 60
    for b in blocks:
        h, m = map(int, b["start"].split(":"))
        assert h * 60 + m == t
        t += b["minutes"]
    assert t == 11 * 60 + 30
    assert sum(b["minutes"] for b in blocks if b["kind"] != "pause") == 140


def test_every_block_09_00_to_11_30_adds_up_to_150_minutes():
    for plan in (PLAN, PLAN_2B):
        assert sum(b["minutes"] for b in plan["block"]) == 150
        assert plan["block"][0]["start"] == "09:00" and len(plan["block"]) == 4


def test_every_block_has_label_and_short_label():
    for b in PLAN["block"] + PLAN_2B["block"]:
        assert b["label"].strip() and b["short"].strip() and len(b["short"]) <= 8


def test_2b_weeks():
    no_empty_strings({k: v for k, v in PLAN_2B.items() if k != "weeks"})
    assert [w["week"] for w in PLAN_2B["weeks"]] == [1, 2, 3, 4]
    for w in PLAN_2B["weeks"]:
        assert [d["day"] for d in w["days"]] == ["Mo", "Di", "Mi", "Do", "Fr"]
        for d in w["days"]:
            no_empty_strings(d)


def test_content_is_for_adults():
    """Follow-up #7: no teen/youth/children's media anywhere in plans, texts or practice items."""
    import re
    banned = [r"\bDRUCK\b", r"\bfunk\b", r"Kinderserie", r"Kinderbuch", r"Kindersendung", r"Jugendbuch",
              r"Jugendserie", r"Nachrichten für Kinder", r"\bComic"]
    for folder in ("plan", "texts", "practice"):
        for f in sorted((config.CONTENT_DIR / folder).glob("*.json")):
            text = f.read_text(encoding="utf-8")
            hits = [p for p in banned if re.search(p, text)]
            assert not hits, f"{f.name}: {hits}"
