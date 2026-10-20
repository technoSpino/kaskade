"""Text-to-speech with Piper (German voice 'thorsten', dataset CC0).

Audio is cached in ~/kaskade-data/tts/audio/<sha1>.ogg (Opus). Nothing here is
required: without Piper or the voice file, `available()` is False and the
frontend falls back to the browser's speech synthesis.
"""
import hashlib
import shutil
import subprocess
import tempfile
import threading
import wave
from functools import lru_cache
from pathlib import Path

from . import config

VOICE = "de_DE-thorsten-medium"
_lock = threading.Lock()


def voice_path() -> Path:
    return config.TTS_DIR / "voices" / f"{VOICE}.onnx"


def audio_dir() -> Path:
    return config.TTS_DIR / "audio"


def available() -> bool:
    try:
        import piper  # noqa: F401
    except ImportError:
        return False
    return voice_path().exists() and shutil.which("ffmpeg") is not None


CODECS = {"ogg": ["-c:a", "libopus", "-b:a", "32k"], "mp3": ["-c:a", "libmp3lame", "-b:a", "64k"]}


def cache_path(text: str, fmt: str = "ogg") -> Path:
    key = hashlib.sha1(f"{VOICE}\n{text.strip()}".encode("utf-8")).hexdigest()
    return audio_dir() / f"{key}.{fmt}"


@lru_cache(maxsize=1)
def _voice():
    from piper import PiperVoice

    return PiperVoice.load(str(voice_path()))


def _synthesize(text: str, out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        with _lock, wave.open(str(wav), "wb") as wf:
            _voice().synthesize_wav(text, wf)
        out.parent.mkdir(parents=True, exist_ok=True)
        fmt = out.suffix.lstrip(".")
        part = out.with_suffix(f".part.{fmt}")
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), *CODECS[fmt], "-ac", "1", str(part)],
            check=True,
        )
        part.replace(out)


def audio_for(text: str, synthesize=_synthesize, fmt: str = "ogg") -> Path | None:
    """Cached audio file for `text`, generating it if needed. None if TTS is unavailable."""
    path = cache_path(text, fmt)
    if path.exists():
        return path
    if synthesize is _synthesize and not available():
        return None
    synthesize(text, path)
    return path if path.exists() else None


# ── Dialogues: speaker B is Thorsten pitch-shifted up, so two voices are distinguishable.
PITCH_B = 1.18
GAP_SECONDS = 0.6


def script_key(segments: list[dict]) -> str:
    return "\n".join(f"{s['speaker']}:{s['text'].strip()}" for s in segments)


def _synthesize_script(segments: list[dict], out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        files = []
        gap = tmpd / "gap.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
                        "-t", str(GAP_SECONDS), str(gap)], check=True)
        for n, seg in enumerate(segments):
            raw = tmpd / f"{n}.wav"
            with _lock, wave.open(str(raw), "wb") as wf:
                _voice().synthesize_wav(seg["text"], wf)
            if seg.get("speaker") == "B":
                shifted = tmpd / f"{n}b.wav"
                subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(raw), "-af",
                                f"asetrate=22050*{PITCH_B},aresample=22050,atempo={1 / PITCH_B:.4f}", str(shifted)],
                               check=True)
                raw = shifted
            files += [raw, gap]
        listing = tmpd / "list.txt"
        listing.write_text("".join(f"file '{f}'\n" for f in files))
        out.parent.mkdir(parents=True, exist_ok=True)
        fmt = out.suffix.lstrip(".")
        part = out.with_suffix(f".part.{fmt}")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                        *CODECS[fmt], "-ac", "1", str(part)], check=True)
        part.replace(out)


def script_audio(segments: list[dict], synthesize=_synthesize_script, fmt: str = "ogg") -> Path | None:
    """Cached two-voice audio for a script [{speaker: 'A'|'B', text}]."""
    path = cache_path(script_key(segments), fmt)
    if path.exists():
        return path
    if synthesize is _synthesize_script and not available():
        return None
    synthesize(segments, path)
    return path if path.exists() else None
