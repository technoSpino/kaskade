"""Graded reading library (data/texts/tNN.json)."""
import json
import logging
from functools import lru_cache

from . import config

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def library() -> list[dict]:
    out = []
    for f in sorted((config.CONTENT_DIR / "texts").glob("t*.json")):
        out.append(json.loads(f.read_text(encoding="utf-8")))
    return out


def get(text_id: str) -> dict | None:
    return next((t for t in library() if t["id"] == text_id), None)


@lru_cache(maxsize=None)
def core_coverage(text_id: str) -> float | None:
    """Share of tokens in the core 2,000 (None if spaCy isn't installed)."""
    t = get(text_id)
    if not t:
        return None
    try:
        from . import textcov
        return textcov.coverage(t["text"])["coverage"]
    except Exception:  # spaCy missing: the library still works without the number
        log.info("text coverage unavailable", exc_info=True)
        return None


def summary(t: dict) -> dict:
    return {
        "id": t["id"], "title": t["title"], "level": t["level"], "theme": t["theme"], "slot": t["slot"],
        "words": len(t["text"].split()), "glossaryCount": len(t["glossary"]), "coverage": core_coverage(t["id"]),
        "origin": t.get("origin", "ai"), "source": t.get("source"),
    }


def next_unread(slot: str, read: set[str]) -> dict | None:
    """First text for a block slot that hasn't been read yet (else the first one again)."""
    candidates = [t for t in library() if t["slot"] == slot]
    for t in candidates:
        if t["id"] not in read:
            return summary(t)
    return summary(candidates[0]) if candidates else None
