import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import analyze, config, db, mining, snippet, srs, texts

router = APIRouter(prefix="/api")


class AnalyzeIn(BaseModel):
    text: str = Field(max_length=20000)
    # #34: a subtitle line (character range) parsed inside its whole sentence; only its tokens come back
    focus: tuple[int, int] | None = None


@router.post("/analyze")
def analyze_text(body: AnalyzeIn):
    if not body.text.strip():
        raise HTTPException(422, "Kein Text")
    if body.focus and not 0 <= body.focus[0] < body.focus[1] <= len(body.text):
        raise HTTPException(422, "Ungültiger Ausschnitt")
    try:
        return analyze.analyze(body.text, body.focus)
    except OSError:
        raise HTTPException(503, "Sprachanalyse nicht verfügbar (spaCy-Modell fehlt)")


@router.get("/texts/{text_id}/analysis")
def text_analysis(text_id: str):
    t = texts.get(text_id)
    if not t:
        raise HTTPException(404, "Text nicht gefunden")
    return analyze_text(AnalyzeIn(text=t["text"]))


class MineIn(BaseModel):
    sentence: str = Field(min_length=3, max_length=400)
    target: str = Field(min_length=1)
    lemma: str = Field(min_length=1)
    display: str | None = None
    gloss: str = ""
    en: str | None = None
    note: str | None = None
    case: Literal["N", "A", "D", "G"] | None = None
    source: str | None = None
    # Mined from a clip: the line's time range → an audio snippet for the card.
    mediaId: int | None = None
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)
    track: Literal["spoken", "ard"] | None = None  # #29: a line of the Whisper track (word times)


def _snippet(mid: int, media_id: int, start: float, end: float, spoken: bool = False) -> str | None:
    """Cut the line's audio from the clip; returns the snippet file name or None."""
    with db.tx() as conn:
        row = conn.execute("SELECT media_file FROM media WHERE id = ?", (media_id,)).fetchone()
    if not row or not row["media_file"]:
        return None
    source = config.MEDIA_DIR / row["media_file"]
    name = f"mine-{mid}.m4a"
    pad = (snippet.SPOKEN_PAD, snippet.SPOKEN_PAD) if spoken else (snippet.PAD_BEFORE, snippet.PAD_AFTER)
    return name if source.exists() and snippet.cut(source, start, end, config.SNIPPETS_DIR / name, pad) else None


@router.post("/mined")
def mine(body: MineIn):
    if body.target not in body.sentence:
        raise HTTPException(422, "Das Wort steht nicht im Satz.")
    clip = body.mediaId is not None and body.start is not None and body.end is not None
    if clip and body.end <= body.start:
        raise HTTPException(422, "Ungültiger Zeitbereich.")
    sentence = body.sentence.strip()
    spoken = clip and body.track == "spoken"
    with db.tx() as conn:
        dup = conn.execute("SELECT * FROM mined WHERE sentence = ? ORDER BY id", (sentence,)).fetchone()
    if dup:
        # "Satz schon gemint" — another word of the line can go onto the same card (#19)
        return {"id": f"mine:{dup['id']}", "duplicate": True, "sameWord": body.target in mining.targets(dup)}
    w = mining.enrich(sentence, body.target, _word(body))
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO mined(created_at, sentence, target, lemma, display, gloss, en, note, kasus, source,"
            " media_id, clip_start, clip_end, ai_fields, track) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (db.now_iso(), sentence, body.target, w["lemma"], w["display"], w["gloss"] or "—", body.en, w["note"],
             w["case"], body.source, body.mediaId if clip else None, body.start if clip else None,
             body.end if clip else None, json.dumps(w["ai"]) if w["ai"] else None, "spoken" if spoken else None),
        )
        mid = cur.lastrowid
    audio = _snippet(mid, body.mediaId, body.start, body.end, spoken) if clip else None
    if audio:
        with db.tx() as conn:
            conn.execute("UPDATE mined SET audio = ? WHERE id = ?", (audio, mid))
    return {"id": f"mine:{mid}", "duplicate": False, "audio": bool(audio), "ai": w["ai"]}


def _word(body: MineIn) -> dict:
    return {"lemma": body.lemma, "display": body.display or body.lemma, "gloss": body.gloss, "case": body.case,
            "note": body.note}


def _mined_card(n: int) -> dict:
    card = srs.card_content(f"mine:{n}")
    if not card:
        raise HTTPException(404, "Karte nicht gefunden")
    return card


@router.post("/mined/{n}/words")
def add_word(n: int, body: MineIn):
    """A second target word of the same line onto the existing card (#19)."""
    r = mining.row(n)
    if not r:
        raise HTTPException(404, "Karte nicht gefunden")
    if body.target not in r["sentence"]:
        raise HTTPException(422, "Das Wort steht nicht im Satz.")
    if body.target in mining.targets(r):
        raise HTTPException(409, "Das Wort ist schon auf der Karte.")
    w = mining.enrich(r["sentence"], body.target, _word(body))
    words = [*json.loads(r["words"] or "[]"),
             {"target": body.target, **{k: w[k] for k in ("lemma", "display", "case", "note", "ai")},
              "gloss": w["gloss"] or "—"}]
    with db.tx() as conn:
        conn.execute("UPDATE mined SET words = ? WHERE id = ?", (json.dumps(words, ensure_ascii=False), n))
    return _mined_card(n)


class MinedEdit(BaseModel):
    lemma: str | None = Field(default=None, min_length=1, max_length=80)
    display: str | None = Field(default=None, min_length=1, max_length=120)
    gloss: str | None = Field(default=None, max_length=200)
    case: Literal["N", "A", "D", "G"] | None = None
    note: str | None = Field(default=None, max_length=300)


@router.patch("/mined/{n}")
def edit_mined(n: int, body: MinedEdit):
    """Matt corrects a mined card; what he edits is his, no longer marked KI."""
    r = mining.row(n)
    if not r:
        raise HTTPException(404, "Karte nicht gefunden")
    sent = body.model_fields_set
    cols = {"lemma": "lemma", "display": "display", "gloss": "gloss", "case": "kasus", "note": "note"}
    values = {cols[f]: getattr(body, f) for f in sent}
    if "gloss" in values:
        values["gloss"] = (values["gloss"] or "").strip() or "—"
    if "note" in values:
        values["note"] = (values["note"] or "").strip() or None
    edited = {"lemma" if f in ("lemma", "display") else f for f in sent}
    values["ai_fields"] = json.dumps([f for f in json.loads(r["ai_fields"] or "[]") if f not in edited])
    with db.tx() as conn:
        conn.execute(f"UPDATE mined SET {', '.join(f'{c} = ?' for c in values)} WHERE id = ?", (*values.values(), n))
    return _mined_card(n)


@router.delete("/mined/{n}")
def delete_mined(n: int):
    if not mining.delete(n):
        raise HTTPException(404, "Karte nicht gefunden")
    return {"ok": True}


@router.get("/mined")
def list_mined():
    return list(reversed(srs.mined_cards()))
