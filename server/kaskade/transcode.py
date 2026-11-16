"""Make every clip play everywhere (Safari, Firefox, Chrome): H.264/AAC in MP4 with +faststart.

Runs after an upload/download as a background task; on failure the original file stays.
"""
import json
import os
import subprocess
from pathlib import Path

AUDIO_OK = {"aac", "mp3"}      # play in every browser as they are
TIMEOUT = 4 * 3600             # a feature film on 2 CPUs stays well below this


def enabled() -> bool:
    # The E2E instance turns this off: Playwright's Chromium can't play H.264.
    return os.environ.get("KASKADE_TRANSCODE", "1") != "0"


def probe(path: Path) -> dict:
    """{'video': codec | None, 'audio': codec | None} of the first video/audio stream."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=60).stdout
    streams = json.loads(out).get("streams", [])
    first = lambda kind: next((s["codec_name"] for s in streams if s.get("codec_type") == kind), None)  # noqa: E731
    video = first("video")
    if video in {"mjpeg", "png"}:  # cover art in an audio file is not a video
        video = None
    return {"video": video, "audio": first("audio")}


def plan(info: dict) -> str:
    """'keep' | 'remux' (copy streams, just +faststart) | 'transcode' (video) | 'audio' (audio → AAC)."""
    if info["video"] is None:
        return "keep" if info["audio"] in AUDIO_OK else "audio"
    if info["video"] == "h264" and info["audio"] in (None, "aac"):
        return "remux"
    return "transcode"


def command(step: str, src: Path, dst: Path) -> list[str]:
    base = ["nice", "-n", "10", "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(src)]
    if step == "remux":
        return base + ["-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-movflags", "+faststart", str(dst)]
    if step == "audio":
        return base + ["-vn", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dst)]
    return base + ["-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-pix_fmt", "yuv420p", "-vf", "scale=-2:'min(720,ih)'", "-c:a", "aac", "-b:a", "128k",
                   "-ac", "2", "-movflags", "+faststart", str(dst)]


def convert(src: Path) -> Path | None:
    """Convert `src` in place (same stem, .mp4 / .m4a). Returns the playable file, or None if it failed."""
    try:
        step = plan(probe(src))
    except (subprocess.SubprocessError, OSError, ValueError):
        return None
    if step == "keep":
        return src
    final = src.with_suffix(".m4a" if step == "audio" else ".mp4")
    tmp = src.with_name(f"{src.stem}.converting{final.suffix}")
    try:
        subprocess.run(command(step, src, tmp), check=True, capture_output=True, timeout=TIMEOUT)
    except (subprocess.SubprocessError, OSError):
        tmp.unlink(missing_ok=True)
        return None
    if not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        return None
    os.replace(tmp, final)
    if final != src:
        src.unlink(missing_ok=True)
    return final
