import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import db, origin, plan, practice, tts

router = APIRouter(prefix="/api/practice")


def _attempts() -> list[dict]:
    with db.tx() as conn:
        rows = conn.execute("SELECT module, item_id, points, total, created_at FROM practice_attempts").fetchall()
    return [dict(r) for r in rows]


def _store(module, item_id, points, total, timed, seconds, detail) -> None:
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO practice_attempts(created_at, module, item_id, points, total, timed, seconds, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (db.now_iso(), module, item_id, points, total, int(timed), seconds, json.dumps(detail, ensure_ascii=False)),
        )


def _writing_prompts() -> list[dict]:
    try:
        prompts = plan.plan()["prompts"]
    except FileNotFoundError:  # plan content missing: practice still works without writing tasks
        return []
    return [p for p in prompts if p["skill"] == "schreiben"]


@router.get("")
def overview():
    attempts = _attempts()
    last = {}
    for a in sorted(attempts, key=lambda a: a["created_at"]):
        last[(a["module"], a["item_id"])] = round(a["points"] / a["total"], 3) if a["total"] else None
    summary = lambda m, i: {"id": i["id"], "title": i["title"], "kind": i.get("kind") or i.get("type"),
                            "minutes": i["minutes"], "last": last.get((m, i["id"])), **origin.tag(i)}
    return {
        "lesen": [summary("lesen", i) for i in practice.bank("lesen")],
        "hoeren": [summary("hoeren", i) for i in practice.bank("hoeren")],
        "schreiben": [summary("schreiben", p) for p in _writing_prompts()],
        "readiness": practice.readiness(attempts),
        "passMark": practice.PASS,
        "selfChecks": practice.SELF_CHECKS,
    }


@router.get("/{module}/{item_id}")
def item(module: Literal["lesen", "hoeren"], item_id: str):
    it = practice.get(module, item_id)
    if not it:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    return practice.public(it)


@router.get("/hoeren/{item_id}/audio")
def audio(item_id: str):
    it = practice.get("hoeren", item_id)
    if not it:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    path = tts.script_audio(it["script"])
    if path is None:
        raise HTTPException(404, "Keine Sprachausgabe auf dem Server (Piper fehlt)")
    return FileResponse(path, media_type="audio/ogg")


class SubmitIn(BaseModel):
    answers: dict[str, bool | int | str]
    seconds: int | None = None
    timed: bool = False


@router.post("/{module}/{item_id}/submit")
def submit(module: Literal["lesen", "hoeren"], item_id: str, body: SubmitIn):
    it = practice.get(module, item_id)
    if not it:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    result = practice.score(it, body.answers)
    _store(module, item_id, result["points"], result["total"], body.timed, body.seconds, body.answers)
    extra = {"script": it["script"]} if "script" in it else {}
    return {**result, **extra}


class SelfCheckIn(BaseModel):
    checks: dict[str, bool]
    text: str = ""
    seconds: int | None = None
    timed: bool = False


@router.post("/schreiben/{prompt_id}/selfcheck")
def selfcheck(prompt_id: str, body: SelfCheckIn):
    if not any(p["id"] == prompt_id for p in _writing_prompts()):
        raise HTTPException(404, "Aufgabe nicht gefunden")
    result = practice.self_check(body.checks)
    _store("schreiben", prompt_id, result["points"], result["total"], body.timed, body.seconds,
           {"checks": body.checks, "words": len(body.text.split())})
    if body.text.strip():
        with db.tx() as conn:
            conn.execute("INSERT INTO writings(created_at, context, prompt_id, text) VALUES (?, 'practice', ?, ?)",
                         (db.now_iso(), prompt_id, body.text))
    return result
