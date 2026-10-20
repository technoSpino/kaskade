"""Media library for Satz-Check: uploads and YouTube downloads in ~/kaskade-data/media."""
import json
import logging
import os
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import config, db, mediathek, satzcheck, srs, stock, transcode, transcripts

router = APIRouter(prefix="/api/media")
log = logging.getLogger(__name__)

MEDIA_EXT = {".mp4", ".webm", ".mkv", ".m4v", ".mov", ".mp3", ".m4a", ".ogg", ".oga", ".wav", ".opus", ".aac"}
SUB_EXT = {".srt", ".vtt"}
YT_RE = re.compile(r"^https?://(www\.|m\.)?(youtube\.com|youtu\.be)/", re.I)


def _progress() -> dict[int, dict]:
    with db.tx() as conn:
        rows = conn.execute("SELECT media_id, position, updated_at FROM media_progress").fetchall()
    return {r["media_id"]: {"position": r["position"], "watchedAt": r["updated_at"]} for r in rows}


def _row(r, with_cues=False, progress: dict | None = None) -> dict:
    cues = json.loads(r["cues"])
    p = (progress if progress is not None else _progress()).get(r["id"], {})
    out = {
        "id": r["id"], "createdAt": r["created_at"], "kind": r["kind"], "title": r["title"],
        "sourceUrl": r["source_url"], "hasMedia": bool(r["media_file"]),
        "isAudio": bool(r["media_file"]) and Path(r["media_file"]).suffix in {".mp3", ".m4a", ".ogg", ".oga", ".wav", ".opus", ".aac"},
        "cueCount": len(cues), "duration": cues[-1]["end"] if cues else (r["duration"] or 0),
        "position": p.get("position", 0), "watchedAt": p.get("watchedAt"),
        "status": r["status"] or "ready",
        # plan stock (#16): catalog key, genre tag, where it comes from
        "key": r["key"], "tag": r["tag"] or None, "source": (stock.item(r["key"]) or {}).get("source") if r["key"] else None,
        "hasSpoken": bool(r["spoken_cues"]),  # #29: a "gesprochen" track from a Whisper transcript
    }
    if with_cues:
        out["cues"] = cues
        out["spokenCues"] = json.loads(r["spoken_cues"]) if r["spoken_cues"] else None
    return out


def _insert(kind, title, source_url, media_file, cues) -> int:
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO media(created_at, kind, title, source_url, media_file, cues, tag) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (db.now_iso(), kind, title, source_url, media_file, json.dumps(cues, ensure_ascii=False),
             stock.guess_tag(title) or ""),
        )
        return cur.lastrowid


def _get(media_id: int):
    with db.tx() as conn:
        r = conn.execute("SELECT * FROM media WHERE id = ?", (media_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Medium nicht gefunden")
    return r


@router.get("")
def list_media():
    transcripts.import_all()  # #29: transcripts that arrived (or were replaced) since: cheap when nothing changed
    with db.tx() as conn:
        rows = conn.execute("SELECT * FROM media ORDER BY id DESC").fetchall()
    progress = _progress()
    return [_row(r, progress=progress) for r in rows]


def last_clip() -> dict | None:
    """The clip to continue in "Schauen & minen": the one watched most recently,
    else the newest clip with a video/audio file."""
    clips = [c for c in list_media() if c["hasMedia"]]
    watched = sorted((c for c in clips if c["watchedAt"]), key=lambda c: c["watchedAt"], reverse=True)
    return (watched or clips or [None])[0]


@router.get("/last")
def last():
    return last_clip()


class ProgressIn(BaseModel):
    position: float = Field(ge=0)
    # #30: the playhead went back > 60 s without him choosing a line — sent with the next save
    reason: Literal["jump"] | None = None
    from_: float | None = Field(default=None, alias="from", ge=0)


@router.put("/{media_id}/progress")
def save_progress(media_id: int, body: ProgressIn):
    _get(media_id)
    new = round(body.position, 2)
    with db.tx() as conn:
        old = conn.execute("SELECT position FROM media_progress WHERE media_id = ?", (media_id,)).fetchone()
        conn.execute(
            "INSERT INTO media_progress(media_id, position, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT(media_id) DO UPDATE SET position = excluded.position, updated_at = excluded.updated_at",
            (media_id, new, db.now_iso()))
    old = old["position"] if old else None
    if body.reason == "jump":
        log.warning("position media %s: jumped back from %s to %s (saved before: %s)", media_id, body.from_, new, old)
    else:
        log.info("position media %s: %s → %s", media_id, old, new)
    return {"id": media_id, "position": new}


class TagIn(BaseModel):
    tag: str = ""


@router.patch("/{media_id}")
def set_tag(media_id: int, body: TagIn):
    """Genre of a clip (krimi, comedy …), editable in "Deine Clips"; "" = none."""
    if body.tag and body.tag not in stock.TAGS:
        raise HTTPException(422, "Unbekanntes Genre")
    _get(media_id)
    with db.tx() as conn:
        conn.execute("UPDATE media SET tag = ? WHERE id = ?", (body.tag, media_id))
    return _row(_get(media_id))


@router.get("/tags")
def tags():
    return [{"id": k, "label": v} for k, v in stock.TAGS.items()]


def range_reached(key: str | None) -> float | None:
    """#30: how far he got in this clip's last plan range before today (watch_ranges.reached), if known."""
    if not key:
        return None
    with db.tx() as conn:
        r = conn.execute("SELECT reached FROM watch_ranges WHERE clip = ? AND local_date < ? ORDER BY local_date DESC LIMIT 1",
                         (key, srs.local_date(srs.now_utc()))).fetchone()
    return r["reached"] if r else None


@router.get("/{media_id}")
def get_media(media_id: int):
    transcripts.import_all(media_id)  # #29: its transcript arrived or was replaced: rebuild the track first
    r = _get(media_id)
    return _row(r, with_cues=True) | {"rangeReached": range_reached(r["key"])}


@router.get("/{media_id}/file")
def media_file(media_id: int):
    r = _get(media_id)
    if not r["media_file"]:
        raise HTTPException(404, "Keine Mediendatei")
    path = config.MEDIA_DIR / r["media_file"]
    if not path.exists():
        raise HTTPException(404, "Mediendatei fehlt auf dem Server")
    return FileResponse(path)


@router.delete("/{media_id}")
def delete_media(media_id: int):
    r = _get(media_id)
    if r["media_file"]:
        (config.MEDIA_DIR / r["media_file"]).unlink(missing_ok=True)
    with db.tx() as conn:
        conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
        conn.execute("DELETE FROM media_progress WHERE media_id = ?", (media_id,))
    return {"ok": True}


def convert_media(media_id: int) -> None:
    """Background task: make the clip's file H.264/AAC MP4 (+faststart); keep the original if that fails."""
    with db.tx() as conn:
        row = conn.execute("SELECT media_file FROM media WHERE id = ?", (media_id,)).fetchone()
    if not row or not row["media_file"]:
        return
    result = transcode.convert(config.MEDIA_DIR / row["media_file"])
    with db.tx() as conn:
        if result is None:
            conn.execute("UPDATE media SET status = 'original' WHERE id = ?", (media_id,))
        else:
            conn.execute("UPDATE media SET media_file = ?, status = 'ready' WHERE id = ?", (result.name, media_id))


def schedule_conversion(media_id: int, tasks: BackgroundTasks) -> None:
    if not transcode.enabled():
        return
    with db.tx() as conn:
        conn.execute("UPDATE media SET status = 'converting' WHERE id = ?", (media_id,))
    tasks.add_task(convert_media, media_id)


# ── Chunked uploads (follow-up #9) ───────────────────────────────────────────
# The web server in front of the API (vite preview, Node) aborts requests that take longer
# than 5 minutes — a big video from a home connection does. So the app sends the video in
# small pieces first and then registers it like a normal upload.
CHUNK_MAX = 16 * 1024 * 1024
STALE_SECONDS = 24 * 3600


def _partial_dir() -> Path:
    d = config.MEDIA_DIR / ".partial"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _partial(upload_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}", upload_id):
        raise HTTPException(404, "Upload nicht gefunden")
    path = _partial_dir() / upload_id
    if not path.exists():
        raise HTTPException(404, "Upload nicht gefunden")
    return path


class UploadStartIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, le=8 * 1024 ** 3)


@router.post("/uploads")
def start_upload(body: UploadStartIn):
    ext = Path(body.filename).suffix.lower()
    if ext not in MEDIA_EXT:
        raise HTTPException(422, f"Dateityp {ext or '?'} wird nicht unterstützt (z. B. .mp4, .webm, .mp3).")
    now = time.time()
    for old in _partial_dir().iterdir():  # forget abandoned uploads
        if now - old.stat().st_mtime > STALE_SECONDS:
            old.unlink(missing_ok=True)
    upload_id = secrets.token_hex(8)
    (_partial_dir() / upload_id).touch()
    (_partial_dir() / f"{upload_id}.json").write_text(json.dumps({"filename": body.filename, "size": body.size}))
    return {"uploadId": upload_id, "chunkSize": 8 * 1024 * 1024}


@router.put("/uploads/{upload_id}")
async def upload_chunk(upload_id: str, offset: int, request: Request):
    path = _partial(upload_id)
    have = path.stat().st_size
    if offset != have:  # e.g. a retried chunk that already arrived: tell the client where we are
        return {"received": have}
    written = 0
    with path.open("ab") as out:
        async for piece in request.stream():
            written += len(piece)
            if written > CHUNK_MAX:
                out.truncate(have)
                raise HTTPException(413, "Stück zu groß")
            out.write(piece)
    return {"received": have + written}


def _take_partial(upload_id: str) -> tuple[Path, str]:
    """The finished chunked upload and its original file name (checks the size)."""
    path = _partial(upload_id)
    meta = json.loads((_partial_dir() / f"{upload_id}.json").read_text())
    if path.stat().st_size != meta["size"]:
        raise HTTPException(409, "Die Datei ist noch nicht vollständig hochgeladen.")
    return path, meta["filename"]


@router.post("/upload")
def upload(
    tasks: BackgroundTasks,
    subtitles: UploadFile = File(...),
    media: UploadFile | None = File(None),
    uploadId: str | None = Form(None),
    title: str = Form(""),
):
    sub_ext = Path(subtitles.filename or "").suffix.lower()
    if sub_ext not in SUB_EXT:
        raise HTTPException(422, "Untertitel bitte als .srt oder .vtt hochladen.")
    raw = subtitles.file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    cues = satzcheck.parse_subtitles(text)
    if not cues:
        raise HTTPException(422, "In der Untertiteldatei wurden keine Sätze gefunden.")

    media_ext = None
    partial = None
    if uploadId:
        partial, original_name = _take_partial(uploadId)
        media_ext = Path(original_name).suffix.lower()
    elif media is not None and media.filename:
        media_ext = Path(media.filename).suffix.lower()
        if media_ext not in MEDIA_EXT:
            raise HTTPException(422, f"Dateityp {media_ext or '?'} wird nicht unterstützt (z. B. .mp4, .webm, .mp3).")

    name = title.strip() or Path(subtitles.filename or "Clip").stem
    media_id = _insert("upload", name, None, None, cues)
    if media_ext:
        config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"upload-{media_id}{media_ext}"
        if partial:
            os.replace(partial, config.MEDIA_DIR / filename)
            (_partial_dir() / f"{uploadId}.json").unlink(missing_ok=True)
        else:
            with (config.MEDIA_DIR / filename).open("wb") as out:
                shutil.copyfileobj(media.file, out, length=1024 * 1024)
        with db.tx() as conn:
            conn.execute("UPDATE media SET media_file = ? WHERE id = ?", (filename, media_id))
        schedule_conversion(media_id, tasks)
    return _row(_get(media_id))


class YoutubeIn(BaseModel):
    url: str


def cookies_path() -> Path:
    """Optional YouTube cookies (Netscape cookies.txt) so yt-dlp passes YouTube's bot check."""
    return config.DATA_DIR / "youtube-cookies.txt"


MAC_ONE_LINER = ('yt-dlp -f "b[height<=540][vcodec^=avc1]/b[height<=540]" --write-subs --write-auto-subs '
                 '--sub-langs "de.*" --convert-subs srt -o "%(title)s.%(ext)s" "LINK"')


def youtube_opts(dest: Path, stem: str) -> dict:
    opts = {
        "format": "worst[ext=mp4][height>=240]/worst[ext=mp4]/worst",
        "outtmpl": str(dest / f"{stem}.%(ext)s"),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["de", "de-DE", "de-orig"],
        "subtitlesformat": "vtt",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "retries": 1,
    }
    if cookies_path().exists():
        opts["cookiefile"] = str(cookies_path())
    return opts


def fetch_youtube(url: str, dest: Path, stem: str) -> dict:
    """Download low-res media + German subtitles with yt-dlp. Returns info dict."""
    import yt_dlp  # imported lazily: heavy and only needed here

    with yt_dlp.YoutubeDL(youtube_opts(dest, stem)) as ydl:
        return ydl.extract_info(url, download=True)


@router.post("/youtube")
def youtube(body: YoutubeIn, tasks: BackgroundTasks):
    url = body.url.strip()
    if not YT_RE.match(url):
        raise HTTPException(422, "Das ist keine YouTube-Adresse.")
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    with db.tx() as conn:
        next_id = (conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM media").fetchone()[0])
    stem = f"yt-{next_id}"
    fallback = " Bitte Video und Untertitel auf dem Mac laden (Befehl unten) und oben hochladen."
    try:
        info = fetch_youtube(url, config.MEDIA_DIR, stem)
    except Exception as e:  # yt-dlp raises many types; all mean "didn't work"
        for f in config.MEDIA_DIR.glob(f"{stem}.*"):
            f.unlink(missing_ok=True)
        msg = str(e)
        if "Sign in" in msg or "bot" in msg.lower() or "403" in msg:
            if cookies_path().exists():
                reason = "YouTube blockiert trotz Cookies — vielleicht sind sie abgelaufen. Neue cookies.txt hochladen, oder:"
            else:
                reason = "YouTube blockiert Downloads von diesem Server („Sign in to confirm you're not a bot“). Mit einer cookies.txt geht es meist, oder:"
        else:
            reason = "Download fehlgeschlagen."
        raise HTTPException(502, reason + fallback)

    subs = sorted(config.MEDIA_DIR.glob(f"{stem}*.vtt"))
    media_files = [f for f in config.MEDIA_DIR.glob(f"{stem}.*") if f.suffix.lower() in MEDIA_EXT]
    if not subs:
        for f in media_files:
            f.unlink(missing_ok=True)
        raise HTTPException(422, "Dieses Video hat keine deutschen Untertitel." + fallback)
    cues = satzcheck.parse_subtitles(subs[0].read_text(encoding="utf-8", errors="replace"))
    for s in subs:
        s.unlink(missing_ok=True)  # cues live in the DB; keep no third-party subtitle files around
    media_id = _insert("youtube", info.get("title") or url, url, media_files[0].name if media_files else None, cues)
    if media_files:
        schedule_conversion(media_id, tasks)
    return _row(_get(media_id))


class MediathekIn(BaseModel):
    url: str


def _mediathek_title(info: dict) -> str:
    title = (info.get("title") or "").strip() or "Mediathek"
    series = (info.get("series") or "").strip()
    return f"{series}: {title}" if series and series.lower() not in title.lower() else title


def run_mediathek(job_id: str, url: str) -> None:
    """Thread body of a Mediathek job: download, subtitles → cues, register the clip, convert."""
    stem = f"mt-{job_id}"
    leftovers = lambda: list(config.MEDIA_DIR.glob(f"{stem}*"))  # noqa: E731

    def fail(message: str) -> None:
        for f in leftovers():
            f.unlink(missing_ok=True)
        mediathek.update(job_id, status="error", message=message)

    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        info = mediathek.fetch(url, config.MEDIA_DIR, stem, mediathek.progress_hook(job_id))
    except Exception as e:  # yt-dlp raises many types; all mean "didn't work"
        msg = str(e)
        if "geo" in msg.lower() or "not available in your country" in msg.lower():
            return fail("Dieses Video ist von hier aus gesperrt (Geo-Sperre).")
        return fail("Download fehlgeschlagen. Ist der Link eine einzelne Sendung in der ARD- oder ZDF-Mediathek?")
    subs = sorted(config.MEDIA_DIR.glob(f"{stem}*.srt")) or sorted(config.MEDIA_DIR.glob(f"{stem}*.vtt"))
    files = [f for f in leftovers() if f.suffix.lower() in MEDIA_EXT]
    if not files:
        return fail("Es wurde keine Videodatei geladen.")
    if not subs:
        return fail("Zu diesem Video gibt es keine deutschen Untertitel (UT).")
    cues = satzcheck.parse_subtitles(subs[0].read_text(encoding="utf-8", errors="replace"))
    for f in subs:
        f.unlink(missing_ok=True)  # cues live in the DB; keep no subtitle files around
    if not cues:
        return fail("Die Untertitel waren leer.")
    media_id = _insert("mediathek", _mediathek_title(info), url, files[0].name, cues)
    mediathek.update(job_id, mediaId=media_id, phase="convert", progress=0.99)
    if transcode.enabled():
        with db.tx() as conn:
            conn.execute("UPDATE media SET status = 'converting' WHERE id = ?", (media_id,))
        convert_media(media_id)
    mediathek.update(job_id, status="done", phase="done", progress=1.0)


@router.post("/mediathek", status_code=202)
def from_mediathek(body: MediathekIn):
    url = body.url.strip()
    if not mediathek.valid_url(url):
        raise HTTPException(422, "Bitte einen Link aus der ARD- oder ZDF-Mediathek einfügen.")
    return {"jobId": mediathek.start(url, run_mediathek)}


@router.get("/jobs/{job_id}")
def job(job_id: str):
    j = mediathek.get(job_id)
    if j is None:
        raise HTTPException(404, "Download nicht gefunden (Server neu gestartet?)")
    return j


@router.get("/youtube/help")
def youtube_help():
    p = cookies_path()
    return {"cookies": p.exists(), "cookiesUpdatedAt": p.stat().st_mtime if p.exists() else None, "macCommand": MAC_ONE_LINER}


@router.post("/youtube/cookies")
def upload_cookies(file: UploadFile = File(...)):
    raw = file.file.read(2 * 1024 * 1024 + 1)
    text = raw.decode("utf-8", errors="replace")
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
    looks_netscape = text.lstrip().startswith(("# Netscape HTTP Cookie File", "# HTTP Cookie File")) or \
        any(l.count("\t") >= 6 for l in lines)
    if len(raw) > 2 * 1024 * 1024 or not looks_netscape:
        raise HTTPException(422, "Das ist keine cookies.txt im Netscape-Format (z. B. mit der Erweiterung „Get cookies.txt LOCALLY“ exportieren).")
    if not any("youtube.com" in l for l in lines):
        raise HTTPException(422, "In der Datei sind keine Cookies von youtube.com.")
    path = cookies_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)  # it's a login: only this user may read it
    return youtube_help()


@router.delete("/youtube/cookies")
def delete_cookies():
    cookies_path().unlink(missing_ok=True)
    return youtube_help()

