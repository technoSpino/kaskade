"""Einstufung: reading score, per-skill levels and the overall result."""
import json
from functools import lru_cache

from . import config, origin


@lru_cache(maxsize=1)
def reading_texts() -> dict:
    return json.loads((config.CONTENT_DIR / "placement/reading.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def tasks() -> dict:
    return json.loads((config.CONTENT_DIR / "placement/tasks.json").read_text(encoding="utf-8"))


def reading_public() -> list[dict]:
    """Texts and questions without the answer key."""
    out = []
    for t in reading_texts()["texts"]:
        qs = [{k: q[k] for k in ("id", "question", "options")} for q in t["questions"]]
        out.append({**{k: t[k] for k in ("id", "level", "title", "kind", "text")}, **origin.tag(t), "questions": qs})
    return out


def score_reading(answers: dict[str, int]) -> dict:
    """answers: {question_id: option_index} → correct count per text + level."""
    scores, review = {}, []
    for t in reading_texts()["texts"]:
        n = 0
        for q in t["questions"]:
            ok = answers.get(q["id"]) == q["correct"]
            n += ok
            review.append({"id": q["id"], "correct": q["correct"], "ok": ok, "explanation": q["explanation"]})
        scores[t["id"]] = n
    return {**scores, "level": reading_level(scores.get("b1", 0), scores.get("b2", 0)), "review": review}


def reading_level(b1: int, b2: int) -> str:
    """5 questions per text."""
    if b1 >= 4:
        if b2 >= 4:
            return "B2"
        if b2 >= 3:
            return "B1+"
        return "B1"
    if b1 == 3:
        return "A2+"
    return "A2"


def listening_level(coverage: int | None, content_type: str | None) -> str | None:
    """Rough listening estimate from the Satz-Check (subtitled, so optimistic)."""
    if coverage is None:
        return None
    if content_type == "simple":
        return "A2" if coverage >= 75 else "A1"
    if coverage >= 80:
        return "B1"
    if coverage >= 60:
        return "A2+"
    return "A2"


def start_hours(phase: str, coverage: int | None) -> int:
    """Rough Refold hours already 'banked' — basis for the B2 forecast (~1,150 h)."""
    if phase == "1":
        return 50
    if phase == "2B":
        return 350
    if coverage is None:
        return 150
    return int(max(150, min(330, 150 + 9 * (coverage - 60))))


def result(state: dict) -> dict:
    vocab = (state.get("vocab") or {}).get("result")
    reading = (state.get("reading") or {}).get("result")
    sc = (state.get("satzcheck") or {}).get("result")
    writing = state.get("writing") or {}
    speaking = state.get("speaking") or {}

    coverage = sc["coverage"] if sc else None
    if sc:
        phase = sc["verdict"]["phase"]
    elif vocab:
        phase = "1" if vocab["estimate"] < 1000 else "2A"
    else:
        phase = "2A"

    grade = writing.get("grade")
    recordings = [r for r in (speaking.get("recordings") or []) if r]
    return {
        "phase": phase,
        "words": vocab["estimate"] if vocab else None,
        "coreKnown": vocab["coreKnown"] if vocab else None,
        "coreShare": vocab["coreShare"] if vocab else None,
        "satzcheck": {"coverage": coverage, "verdict": sc["verdict"]} if sc else None,
        "startHours": start_hours(phase, coverage),
        "skills": {
            "lesen": reading["level"] if reading else None,
            "hoeren": listening_level(coverage, sc.get("contentType") if sc else None),
            "schreiben": grade.get("level") if grade else None,
            "sprechen": None,
        },
        "notes": {
            "schreiben": "KI-Bewertung" if grade else ("gespeichert, ohne KI nicht bewertet" if writing.get("text") else "übersprungen"),
            "sprechen": f"{len(recordings)} Aufnahmen gespeichert, noch nicht bewertet" if recordings else "übersprungen",
        },
    }
