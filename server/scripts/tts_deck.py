"""Pre-generate Piper audio for every core-deck sentence (cached in ~/kaskade-data/tts/audio).

Usage: .venv/bin/python scripts/tts_deck.py [--limit N]
Voice: download de_DE-thorsten-medium.onnx(+.json) from huggingface.co/rhasspy/piper-voices
into ~/kaskade-data/tts/voices/ first.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaskade import srs, tts  # noqa: E402


def main() -> None:
    if not tts.available():
        sys.exit(f"Piper or voice missing: {tts.voice_path()}")
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    cards = srs.deck()[:limit]
    t0, made = time.time(), 0
    for i, c in enumerate(cards, 1):
        if not tts.cache_path(c["sentence"]).exists():
            tts.audio_for(c["sentence"])
            made += 1
        if i % 200 == 0:
            print(f"{i}/{len(cards)} ({made} new, {time.time() - t0:.0f}s)", flush=True)
    print(f"done: {len(cards)} cards, {made} generated in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
