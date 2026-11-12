from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import db, texts, tts

router = APIRouter(prefix="/api/texts")


def read_ids() -> dict[str, str]:
    with db.tx() as conn:
        rows = conn.execute("SELECT text_id, MAX(read_at) FROM text_reads GROUP BY text_id").fetchall()
    return {r[0]: r[1] for r in rows}


@router.get("")
def list_texts():
    read = read_ids()
    return [{**texts.summary(t), "readAt": read.get(t["id"])} for t in texts.library()]


@router.get("/{text_id}")
def get_text(text_id: str):
    t = texts.get(text_id)
    if not t:
        raise HTTPException(404, "Text nicht gefunden")
    return {**t, **texts.summary(t), "readAt": read_ids().get(text_id)}


@router.post("/{text_id}/read")
def mark_read(text_id: str):
    if not texts.get(text_id):
        raise HTTPException(404, "Text nicht gefunden")
    with db.tx() as conn:
        conn.execute("INSERT INTO text_reads(text_id, read_at) VALUES (?, ?)", (text_id, db.now_iso()))
    return {"id": text_id, "read": True}


@router.get("/{text_id}/audio")
def audio(text_id: str):
    t = texts.get(text_id)
    if not t:
        raise HTTPException(404, "Text nicht gefunden")
    path = tts.audio_for(t["text"].replace("\n\n", "\n"))
    if path is None:
        raise HTTPException(404, "Keine Sprachausgabe auf dem Server (Piper fehlt)")
    return FileResponse(path, media_type="audio/ogg", headers={"Cache-Control": "max-age=31536000"})
