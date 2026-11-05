import json
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import ai, config, db, placement

router = APIRouter(prefix="/api")

AUDIO_EXT = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav"}


def _placement_row(r) -> dict:
    return {
        "id": r["id"], "createdAt": r["created_at"], "updatedAt": r["updated_at"], "status": r["status"],
        "state": json.loads(r["state"]), "result": json.loads(r["result"]) if r["result"] else None,
    }


def _get_placement(pid: int):
    with db.tx() as conn:
        r = conn.execute("SELECT * FROM placements WHERE id = ?", (pid,)).fetchone()
    if not r:
        raise HTTPException(404, "Einstufung nicht gefunden")
    return r


@router.get("/placement/content")
def content():
    t = placement.tasks()
    return {"reading": placement.reading_public(), "writing": t["writing"], "speaking": t["speaking"], "ai": ai.available()}


@router.get("/placement/current")
def current():
    """The open placement if there is one, else the latest finished one, else null."""
    with db.tx() as conn:
        r = conn.execute("SELECT * FROM placements WHERE status = 'in_progress' ORDER BY id DESC LIMIT 1").fetchone()
        if not r:
            r = conn.execute("SELECT * FROM placements ORDER BY id DESC LIMIT 1").fetchone()
    return _placement_row(r) if r else None


@router.post("/placement")
def create():
    now = db.now_iso()
    with db.tx() as conn:
        conn.execute("UPDATE placements SET status = 'abandoned' WHERE status = 'in_progress'")
        cur = conn.execute(
            "INSERT INTO placements(created_at, updated_at, status, state) VALUES (?, ?, 'in_progress', ?)",
            (now, now, json.dumps({"step": "wortschatz"})),
        )
        pid = cur.lastrowid
    return _placement_row(_get_placement(pid))


class StateIn(BaseModel):
    state: dict


@router.put("/placement/{pid}")
def save_state(pid: int, body: StateIn):
    r = _get_placement(pid)
    if r["status"] != "in_progress":
        raise HTTPException(409, "Diese Einstufung ist schon abgeschlossen.")
    with db.tx() as conn:
        conn.execute("UPDATE placements SET state = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(body.state, ensure_ascii=False), db.now_iso(), pid))
    return {"ok": True}


@router.post("/placement/{pid}/finish")
def finish(pid: int):
    r = _get_placement(pid)
    state = json.loads(r["state"])
    res = placement.result(state)
    with db.tx() as conn:
        conn.execute("UPDATE placements SET status = 'done', result = ?, updated_at = ? WHERE id = ?",
                     (json.dumps(res, ensure_ascii=False), db.now_iso(), pid))
    db.set_setting("phase", res["phase"])
    db.set_setting("startHours", res["startHours"])
    return _placement_row(_get_placement(pid))


class ReadingAnswers(BaseModel):
    answers: dict[str, int]


@router.post("/placement/reading/score")
def score_reading(body: ReadingAnswers):
    return placement.score_reading(body.answers)


class WritingIn(BaseModel):
    context: str
    promptId: str
    text: str


def _find_task(prompt_id: str) -> dict | None:
    w = placement.tasks()["writing"]
    if w["id"] == prompt_id:
        return w
    plan = config.CONTENT_DIR / "plan/weeks-1-4.json"
    if plan.exists():
        for p in json.loads(plan.read_text(encoding="utf-8")).get("prompts", []):
            if p["id"] == prompt_id:
                return p
    return None


@router.post("/writing")
def save_writing(body: WritingIn):
    task = _find_task(body.promptId)
    if task is None:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    if not body.text.strip():
        raise HTTPException(422, "Der Text ist leer.")
    grade = ai.grade_writing(task, body.text)
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO writings(created_at, context, prompt_id, text, grade) VALUES (?, ?, ?, ?, ?)",
            (db.now_iso(), body.context, body.promptId, body.text,
             json.dumps(grade, ensure_ascii=False) if grade else None),
        )
        wid = cur.lastrowid
    return {"id": wid, "grade": grade, "ai": ai.available(), "words": len(body.text.split())}


@router.get("/writing")
def list_writing(context: str | None = None):
    with db.tx() as conn:
        q = "SELECT * FROM writings" + (" WHERE context = ?" if context else "") + " ORDER BY id DESC"
        rows = conn.execute(q, (context,) if context else ()).fetchall()
    return [{"id": r["id"], "createdAt": r["created_at"], "context": r["context"], "promptId": r["prompt_id"],
             "text": r["text"], "grade": json.loads(r["grade"]) if r["grade"] else None} for r in rows]


@router.post("/recordings")
def upload_recording(audio: UploadFile = File(...), context: str = Form(...)):
    ctype = (audio.content_type or "").split(";")[0]
    ext = AUDIO_EXT.get(ctype) or Path(audio.filename or "").suffix.lower()
    if ext not in AUDIO_EXT.values():
        raise HTTPException(422, "Unbekanntes Audioformat")
    with db.tx() as conn:
        cur = conn.execute("INSERT INTO recordings(created_at, context, filename) VALUES (?, ?, '')",
                           (db.now_iso(), context))
        rid = cur.lastrowid
        filename = f"rec-{rid}{ext}"
        conn.execute("UPDATE recordings SET filename = ? WHERE id = ?", (filename, rid))
    config.RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    with (config.RECORDINGS_DIR / filename).open("wb") as out:
        shutil.copyfileobj(audio.file, out)
    return {"id": rid, "context": context}


@router.get("/recordings/{rid}/file")
def recording_file(rid: int):
    with db.tx() as conn:
        r = conn.execute("SELECT filename FROM recordings WHERE id = ?", (rid,)).fetchone()
    if not r or not (config.RECORDINGS_DIR / r["filename"]).exists():
        raise HTTPException(404, "Aufnahme nicht gefunden")
    return FileResponse(config.RECORDINGS_DIR / r["filename"])
