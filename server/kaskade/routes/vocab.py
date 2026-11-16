import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db, vocab

router = APIRouter(prefix="/api/vocab")


class Answer(BaseModel):
    word: str
    band: str
    yes: bool


class Submission(BaseModel):
    answers: list[Answer]


@router.get("/test")
def get_test():
    return {"items": vocab.build_test()}


@router.post("/result")
def post_result(sub: Submission):
    answers = [a.model_dump() for a in sub.answers]
    band_ids = {b["id"] for b in vocab.pools()["bands"]} | {"pseudo"}
    if not answers or any(a["band"] not in band_ids for a in answers):
        raise HTTPException(422, "Ungültige Antworten")
    result = vocab.score(answers)
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO vocab_tests(created_at, answers, result) VALUES (?, ?, ?)",
            (db.now_iso(), json.dumps(answers), json.dumps(result)),
        )
        result_id = cur.lastrowid
    return {"id": result_id, **result}


@router.get("/latest")
def latest():
    with db.tx() as conn:
        row = conn.execute(
            "SELECT id, created_at, result FROM vocab_tests ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return {"id": row["id"], "createdAt": row["created_at"], **json.loads(row["result"])}
