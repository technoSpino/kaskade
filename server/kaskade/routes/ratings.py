"""#23 "Wie viel hast du verstanden?" after a block, Schauen's "zu schwer" lines; #24 book modes."""
import datetime as dt
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException
from typing import Literal

from pydantic import BaseModel, Field

from .. import db, materials, plan, ratings, rolling, satzcheck, srs, transcripts

router = APIRouter(prefix="/api")

RATED_BLOCKS = ("input", "lesen")
EXTERNAL = ("news", "book", "lesetest", "youtube", "netflix")  # read or watched outside Kaskade's pages


def _today() -> date:
    return srs.now_utc().astimezone(srs.TZ).date()


def _plan():
    from .today import plan_start
    data = plan.plan(db.get_setting("phase"))
    return data, plan_start(_today())


def assignments(day: date) -> dict[str, dict]:
    """The items Heute showed (or shows) for each block of `day`."""
    data, start = _plan()
    ctx = materials.Ctx(day)
    ctx.live = day == ctx.real_today
    return {it["block"]: it for it in materials.day_items(plan.plan_day(start, day, data, ctx.pauses), ctx, data, start)}


def rateable(it: dict) -> bool:
    return it["block"] in RATED_BLOCKS or it["kind"] == "lesetest"


def share_for(it: dict, day: date) -> dict | None:
    """Schauen's measured share for a clip item: lines marked too hard of the lines heard today."""
    if it["kind"] not in ("clip", "satzcheck") or not it.get("mediaId") or it.get("audio"):
        return None
    hard = ratings.hard_marks(day, it["mediaId"])
    # #29: count the lines of the track he marked on (the spoken one is the default when it exists)
    spoken = transcripts.load(it["mediaId"])
    track = spoken if spoken and (hard[-1]["track"] == "spoken" if hard else True) else rolling.load_cues(it["mediaId"])
    cues = [c for c in track if not satzcheck.is_non_speech(c.get("text", ""))]
    frm = (it.get("range") or [0])[0]
    to = max(it.get("position") or 0, frm)
    marks = [m["start"] for m in hard]
    s = ratings.hard_share(cues, frm, to, marks)
    return s if s["lines"] else None


def annotate(items: dict[str, dict], day: date, done: set[str], running: str | None, worked: set[str]) -> None:
    """Each rateable item gets its rating (or None) and `ask`: Heute offers the question now —
    once the block is ticked off, or its timer ran and stopped (for things read outside Kaskade
    also while it runs). `worked`: blocks with a timer today."""
    rated = ratings.on_day(day)
    for block, first in items.items():
        for it in [first, *first.get("then", [])]:
            info = ratings.rate_info(it, day) if rateable(it) else None
            if not info:
                continue
            r = rated.get((block, info["item"]))
            started = block in worked or running == block
            it["rating"] = r
            it["rateItem"] = info["item"]
            it["rateLabel"] = info["label"]
            it["ask"] = r is None and (block in done or started and (running != block or it["kind"] in EXTERNAL))
            if it["ask"]:
                it["share"] = share_for(it, day)


class RatingIn(BaseModel):
    block: str
    item: str | None = None           # which of the block's items (#27: lesen can hold two); default the first
    pct: int | None = None            # None = skipped
    date: dt.date | None = None       # a past day (e.g. the first data point); default today
    hard: int | None = Field(default=None, ge=0)
    lines: int | None = Field(default=None, ge=0)


@router.post("/ratings")
def rate(body: RatingIn):
    day = body.date or _today()
    if day > _today():
        raise HTTPException(422, "Das Datum liegt in der Zukunft.")
    if body.pct is not None and body.pct not in ratings.PCTS:
        raise HTTPException(422, "Bitte 20, 40, 60, 80 oder 100 %.")
    first = assignments(day).get(body.block)
    info, it = None, None
    for x in [first, *first.get("then", [])] if first else []:
        i = ratings.rate_info(x, day) if rateable(x) else None
        if i and (body.item is None or body.item == i["item"]):
            info, it = i, x
            break
    if not info:
        raise HTTPException(422, "Für diesen Block gibt es an dem Tag nichts einzuschätzen.")
    hard, lines = body.hard, body.lines
    if hard is None and (s := share_for(it, day)):
        hard, lines = s["marked"], s["lines"]
    return ratings.save(day, body.block, info, body.pct, hard, lines)


@router.get("/ratings/today")
def today_ratings():
    """Today's rateable blocks — Schauen and the reader find theirs here (by clip or text)."""
    day = _today()
    rated = ratings.on_day(day)
    out = []
    for it in materials.flat(list(assignments(day).values())):
        block = it["block"]
        info = ratings.rate_info(it, day) if rateable(it) else None
        if not info:
            continue
        r = rated.get((block, info["item"]))
        out.append({"block": block, "item": info["item"], "kind": info["kind"], "label": info["label"],
                    "mediaId": it.get("mediaId"), "range": it.get("range"), "textId": it.get("textId"),
                    "rating": r})
    return out


@router.get("/ratings")
def list_ratings(days: int = 60):
    """Fahrplan: every rating of the last `days` days, the "zu schwer" ones, and each book's mode."""
    day = _today()
    data, start = _plan()
    return {"ratings": ratings.recent(day - timedelta(days=days)),
            "tooHard": ratings.too_hard(day, start, data),
            "books": book_modes(day, start, data)}


def book_modes(day: date, start: date, data: dict) -> list[dict]:
    """How each book of the plan is read next (from tomorrow), once a test or rating says something."""
    out = []
    for book_id in materials.first_days(start, data):
        m = ratings.book_mode(book_id, day + timedelta(days=1), start, data)
        if m["show"]:
            out.append(m)
    return out


class HardIn(BaseModel):
    start: float = Field(ge=0)
    end: float | None = None
    text: str = Field(min_length=1, max_length=500)
    track: Literal["spoken", "ard"] | None = None  # #29: the line was on this track


@router.post("/media/{media_id}/hard")
def mark_hard(media_id: int, body: HardIn):
    """Schauen, key Z: this line was too hard (no card) — counted for today's rating question."""
    day = _today()
    with db.tx() as conn:
        if not conn.execute("SELECT 1 FROM media WHERE id = ?", (media_id,)).fetchone():
            raise HTTPException(404, "Clip nicht gefunden")
    ratings.mark_hard(day, media_id, body.start, body.end, body.text.strip(), "spoken" if body.track == "spoken" else None)
    return {"marks": ratings.hard_marks(day, media_id)}


@router.get("/media/{media_id}/hard")
def hard_lines(media_id: int):
    return {"marks": ratings.hard_marks(_today(), media_id)}
