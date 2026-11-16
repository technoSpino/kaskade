from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from .. import feed, tts

router = APIRouter(prefix="/api/feed")


def _audio(ep: dict):
    return tts.audio_for(ep["text"], fmt="mp3")


@router.get(".xml")
def feed_xml(request: Request):
    eps = feed.episodes()
    sizes = {}
    for ep in eps:
        path = _audio(ep)
        if path:
            sizes[ep["key"]] = path.stat().st_size
    base = str(request.base_url)
    return Response(feed.rss([e for e in eps if e["key"] in sizes], base, sizes),
                    media_type="application/rss+xml; charset=utf-8")


@router.get("/info")
def info():
    eps = feed.episodes()
    return {"episodes": [{"key": e["key"], "title": e["title"]} for e in eps], "tts": tts.available()}


@router.get("/audio/{key}.mp3")
def audio(key: str):
    ep = next((e for e in feed.episodes() if e["key"] == key), None)
    if not ep:
        raise HTTPException(404, "Folge nicht gefunden")
    path = _audio(ep)
    if not path:
        raise HTTPException(404, "Keine Sprachausgabe auf dem Server")
    return FileResponse(path, media_type="audio/mpeg")
