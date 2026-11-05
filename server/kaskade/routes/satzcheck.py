import json
import re
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import analyze, db, satzcheck, textcov

router = APIRouter(prefix="/api/satzcheck")


class Rating(BaseModel):
    cue: int
    text: str
    rating: Literal["v", "h", "s"]


class Run(BaseModel):
    mediaId: int | None = None
    contentType: Literal["simple", "adult"]
    windowStart: float
    windowEnd: float
    ratings: list[Rating]


def known_words() -> int | None:
    with db.tx() as conn:
        row = conn.execute("SELECT result FROM vocab_tests ORDER BY id DESC LIMIT 1").fetchone()
    return json.loads(row["result"])["estimate"] if row else None


def evaluate(content_type: str, ratings: list[str]) -> dict:
    s = satzcheck.summarize(ratings)
    words = known_words()
    return {**s, "words": words, "verdict": satzcheck.verdict(s["coverage"], content_type, words)}


SHORT_LINE = 8  # words
# Spoken reductions and fillers: known words, just said fast.
COLLOQUIAL = set("""ner nen nem ne n nee nö nix nich is hab haste biste gibts isses weißte kannste willste
musste guck na äh ähm hm okay ok tja jo joa jep nö mhm""".split())


def line_kind(text: str) -> str:
    """'tempo' when a hard line is short and every word is among the 2,000 core words (it was the
    speed, not the vocabulary), else 'wortschatz'. Names and spoken reductions ('ner, nee) don't count."""
    cov = textcov.coverage(text, extra_known=COLLOQUIAL)
    d = analyze.dictionary()
    in_dict = lambda w: w in d["entries"] or w in d["forms"] or w.lower() in d["forms"]  # noqa: E731
    unknown = [w for w in cov["unknown"] if not (w[:1].isupper() and not in_dict(w))]  # capitalised + unknown word = a name
    distinct = {w.lower() for w in re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text)}  # repeats don't make a line long
    return "tempo" if len(distinct) <= SHORT_LINE and not unknown else "wortschatz"


def diagnose(ratings: list[dict], media_id: int | None) -> list[dict]:
    """The "zu schwer" lines that were about listening speed, with their time in the clip."""
    cues = []
    if media_id:
        with db.tx() as conn:
            row = conn.execute("SELECT cues FROM media WHERE id = ?", (media_id,)).fetchone()
        cues = json.loads(row["cues"]) if row else []
    out = []
    for r in ratings:
        if r["rating"] != "s" or satzcheck.is_non_speech(r["text"]):
            continue
        try:
            kind = line_kind(r["text"])
        except OSError:  # spaCy model missing: no diagnosis
            return []
        if kind == "tempo":
            cue = cues[r["cue"]] if 0 <= r["cue"] < len(cues) else None
            out.append({"cue": r["cue"], "text": r["text"], "start": cue["start"] if cue else None,
                        "end": cue["end"] if cue else None})
    return out


@router.post("")
def save_run(run: Run):
    if not run.ratings:
        raise HTTPException(422, "Noch keine Sätze bewertet.")
    result = evaluate(run.contentType, [r.rating for r in run.ratings])
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO satzcheck_runs(created_at, media_id, content_type, window_start, window_end, ratings, result)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (db.now_iso(), run.mediaId, run.contentType, run.windowStart, run.windowEnd,
             json.dumps([r.model_dump() for r in run.ratings], ensure_ascii=False), json.dumps(result, ensure_ascii=False)),
        )
        run_id = cur.lastrowid
    tempo = diagnose([r.model_dump() for r in run.ratings], run.mediaId)
    return {"id": run_id, "createdAt": db.now_iso(), "contentType": run.contentType, **result,
            "mediaId": run.mediaId, "tempo": tempo}


def run_result(row) -> dict:
    """A stored run's result, recounted on speech lines only (see satzcheck.speech_only)."""
    return satzcheck.speech_only(json.loads(row["result"]), json.loads(row["ratings"]), row["content_type"])


@router.get("/history")
def history():
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT r.id, r.created_at, r.content_type, r.ratings, r.result, r.media_id, m.title FROM satzcheck_runs r"
            " LEFT JOIN media m ON m.id = r.media_id ORDER BY r.id DESC"
        ).fetchall()
    return [
        {"id": r["id"], "createdAt": r["created_at"], "contentType": r["content_type"], "title": r["title"],
         "mediaId": r["media_id"], **run_result(r), "tempo": diagnose(json.loads(r["ratings"]), r["media_id"])}
        for r in rows
    ]


def mineable_lines() -> list[dict]:
    """Lines rated "mit Hilfe" or "zu schwer" in any Satz-Check (newest first, each text once),
    flagged when a card from that line already exists — candidates for sentence cards."""
    with db.tx() as conn:
        runs = conn.execute(
            "SELECT r.id, r.ratings, m.title, r.media_id FROM satzcheck_runs r"
            " LEFT JOIN media m ON m.id = r.media_id ORDER BY r.id DESC").fetchall()
        mined = {r[0] for r in conn.execute("SELECT sentence FROM mined")}
    out, seen = [], set()
    for run in runs:
        for r in json.loads(run["ratings"]):
            text = r["text"].strip()
            if r["rating"] == "v" or text in seen or satzcheck.is_non_speech(text):
                continue
            seen.add(text)
            out.append({"runId": run["id"], "mediaId": run["media_id"], "title": run["title"], "cue": r["cue"],
                        "text": text, "rating": r["rating"], "mined": text in mined})
    return out


@router.get("/lines")
def lines():
    return mineable_lines()

