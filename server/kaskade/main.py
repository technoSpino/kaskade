"""Kaskade API. Run: uvicorn kaskade.main:app --host 127.0.0.1 --port 8000"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from uvicorn.logging import DefaultFormatter

from . import config, db, srs, stock
from .routes import cards, feed, media, placement, practice, ratings, reader, satzcheck, texts, today, vocab

# Our own log lines (#30: every saved clip position) in the journal, formatted like uvicorn's
_log = logging.getLogger("kaskade")
if not _log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(DefaultFormatter("%(levelprefix)s %(message)s"))
    _log.addHandler(_handler)
    _log.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    db.init()
    stock.backfill_tags()
    stock.link_existing()
    yield


app = FastAPI(title="Kaskade API", lifespan=lifespan)
app.include_router(vocab.router)
app.include_router(media.router)
app.include_router(satzcheck.router)
app.include_router(placement.router)
app.include_router(cards.router)
app.include_router(today.router)
app.include_router(texts.router)
app.include_router(reader.router)
app.include_router(feed.router)
app.include_router(practice.router)
app.include_router(ratings.router)


@app.get("/api/status")
def status():
    """Learner status for the header and Heute (phase from the last Einstufung)."""
    with db.tx() as conn:
        running = today.current_timer(conn, srs.now_utc())
    return {
        "phase": db.get_setting("phase"),
        "name": db.get_setting("name", "Matt"),
        "running": {"block": running["block"], "startedAt": running["started_at"]} if running else None,
        "theme": db.get_setting("theme"),
        "httpsUrl": config.HTTPS_URL,  # the microphone needs HTTPS (#17)
    }


THEMES = {"signal", "nacht", "papier", "bauhaus", "fokus", "magazin"}


class ThemeIn(BaseModel):
    theme: str


@app.put("/api/settings/theme")
def set_theme(body: ThemeIn):
    if body.theme not in THEMES:
        raise HTTPException(422, "Unbekannter Stil")
    db.set_setting("theme", body.theme)
    return {"theme": body.theme}


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "db": str(config.DB_PATH),
        "ai": config.anthropic_key() is not None,
    }
