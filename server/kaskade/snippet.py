"""Short audio snippets of subtitle lines, cut from a clip with ffmpeg (for mined sentence cards)."""
import subprocess
from pathlib import Path

PAD_BEFORE = 0.25   # subtitles often start a little late …
PAD_AFTER = 0.35    # … and end a little early
MAX_SECONDS = 15.0


SPOKEN_PAD = 0.15   # #29: a line of the Whisper track has word times — only a little padding


def window(start: float, end: float, pad: tuple[float, float] = (PAD_BEFORE, PAD_AFTER)) -> tuple[float, float]:
    """Padded [from, to] for a cue, never negative and at most MAX_SECONDS long."""
    a = max(0.0, start - pad[0])
    b = max(a + 0.1, end + pad[1])
    return round(a, 3), round(min(b, a + MAX_SECONDS), 3)


def cut(source: Path, start: float, end: float, out: Path, pad: tuple[float, float] = (PAD_BEFORE, PAD_AFTER)) -> bool:
    """Write the audio of [start, end] (padded) from `source` to `out` as AAC (.m4a). False on failure."""
    a, b = window(start, end, pad)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(source),
           "-vn", "-ac", "1", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(out)]
    try:
        subprocess.run(cmd, check=True, timeout=60, capture_output=True)
    except (subprocess.SubprocessError, OSError):
        out.unlink(missing_ok=True)
        return False
    return out.exists() and out.stat().st_size > 0
