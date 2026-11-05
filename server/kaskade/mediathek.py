"""ARD/ZDF Mediathek downloads with yt-dlp as background jobs with progress (follow-up #8).

Unlike YouTube, the Mediathek doesn't block this server. Downloads prefer ≤ 540p H.264 and
German subtitles; jobs live in memory (a restart forgets running jobs, files stay consistent).
"""
import re
import threading
import time
import uuid
from pathlib import Path

URL_RE = re.compile(r"^https?://(www\.)?(ardmediathek\.de|zdf\.de|3sat\.de)/", re.I)
FORMAT = "b[height<=540][vcodec^=avc1]/b[height<=720][vcodec^=avc1]/b[height<=720]/b"
SUB_LANGS = ["deu", "de", "de-DE", "ger"]

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def valid_url(url: str) -> bool:
    return bool(URL_RE.match(url.strip()))


def fetch(url: str, dest: Path, stem: str, hook) -> dict:
    """Download media + German subtitles (as .srt) into `dest` as `stem.*`. Returns yt-dlp's info."""
    import yt_dlp  # heavy; only needed here

    opts = {
        "format": FORMAT,
        "outtmpl": str(dest / f"{stem}.%(ext)s"),
        "writesubtitles": True,
        "subtitleslangs": SUB_LANGS,
        "subtitlesformat": "vtt/ttml/srt/best",
        "postprocessors": [{"key": "FFmpegSubtitlesConvertor", "format": "srt", "when": "before_dl"}],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 30,
        "retries": 3,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=True)


def start(url: str, run) -> str:
    """Start `run(job_id, url)` in a thread; returns the job id."""
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {"id": job_id, "url": url, "status": "running", "phase": "start", "progress": 0.0,
                         "downloaded": 0, "total": None, "speed": None, "message": None, "mediaId": None,
                         "startedAt": time.time()}
    threading.Thread(target=run, args=(job_id, url), daemon=True).start()
    return job_id


def update(job_id: str, **fields) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def get(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def progress_hook(job_id: str):
    """yt-dlp progress hook → job fields (bytes, total, speed, 0–1)."""
    def hook(d: dict) -> None:
        if d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        done = d.get("downloaded_bytes") or 0
        frag = (d.get("fragment_index"), d.get("fragment_count"))
        share = done / total if total else (frag[0] / frag[1] if all(frag) else 0.0)
        update(job_id, phase="download", downloaded=done, total=total, speed=d.get("speed"),
               progress=round(min(0.99, share), 3))
    return hook
