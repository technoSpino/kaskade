"""B1 practice bank: scoring, attempts and readiness (pass mark 60 % per module)."""
import json
from functools import lru_cache

from . import config

PASS = 0.6
MODULES = ("lesen", "hoeren", "schreiben")
SELF_CHECKS = {
    "aufgabe": "Aufgabe erfüllt: alle Punkte behandelt?",
    "anrede": "Passende Anrede und Gruß (du/Sie)?",
    "konnektoren": "Konnektoren benutzt (weil, deshalb, trotzdem …)?",
    "verbstellung": "Verb an Position 2 / im Nebensatz am Ende?",
}


@lru_cache(maxsize=None)
def bank(module: str) -> list[dict]:
    path = config.CONTENT_DIR / f"practice/{module}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["items"]


def get(module: str, item_id: str) -> dict | None:
    return next((i for i in bank(module) if i["id"] == item_id), None)


def public(item: dict) -> dict:
    """Item without answers."""
    out = {k: v for k, v in item.items() if k not in ("questions", "situations")}
    if "questions" in item:
        out["questions"] = [{k: v for k, v in q.items() if k != "correct"} for q in item["questions"]]
    if "situations" in item:
        out["situations"] = [{k: v for k, v in s.items() if k != "correct"} for s in item["situations"]]
    if "script" in item:
        out.pop("script")  # listening: the transcript is shown only after submitting
    return out


def score(item: dict, answers: dict) -> dict:
    """answers: {question id: True/False | option index | ad id ('0' = none)}."""
    keyed = item.get("questions") or item.get("situations") or []
    review = []
    for q in keyed:
        given = answers.get(q["id"])
        review.append({"id": q["id"], "given": given, "correct": q["correct"], "ok": given == q["correct"]})
    points = sum(r["ok"] for r in review)
    total = len(review)
    return {"points": points, "total": total, "pct": round(points / total, 3) if total else 0.0,
            "passed": total > 0 and points / total >= PASS, "review": review}


def self_check(checks: dict) -> dict:
    points = sum(bool(checks.get(k)) for k in SELF_CHECKS)
    total = len(SELF_CHECKS)
    return {"points": points, "total": total, "pct": round(points / total, 3), "passed": points / total >= PASS}


def readiness(attempts: list[dict]) -> dict:
    """attempts: [{module, points, total, created_at}] (any order) → per-module summary."""
    out = {}
    for m in MODULES:
        rows = sorted((a for a in attempts if a["module"] == m and a["total"]), key=lambda a: a["created_at"])
        if not rows:
            out[m] = {"attempts": 0, "latest": None, "average": None, "passed": None}
            continue
        recent = rows[-3:]
        avg = sum(a["points"] for a in recent) / sum(a["total"] for a in recent)
        latest = rows[-1]["points"] / rows[-1]["total"]
        out[m] = {"attempts": len(rows), "latest": round(latest, 3), "average": round(avg, 3), "passed": avg >= PASS}
    return out
