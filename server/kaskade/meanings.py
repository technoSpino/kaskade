"""#40: every highlighted word in Schauen has a meaning. What the dictionary, a base form, a particle
verb or a compound split (analyze.derive) doesn't give, the KI is asked for — once per (word, sentence),
kept in ki_meanings, and asked ahead of time so the word panel never waits on a tap: the Materialcheck
does each planned clip's next part, opening a clip does the rest of today's range in the background.
A word the KI calls misheard, or with no KI at all, is not highlighted (analyze leaves its state off).
"""
import json
import logging
import re
import threading

from . import ai, analyze, config, db
from .satzcheck import is_non_speech

log = logging.getLogger(__name__)

MAX_ASK = 400  # per clip part — a bound on the cost if something goes wrong
FAILS = 3  # no usable answer this often in a row: stop, the next run tries again

# The line around a subtitle line as Schauen analyses it (sentenceAround in app/src/lib/watch.js, #34):
# neighbouring lines up to a sentence end, at most 3 each way, not across a pause > 2 s or a new speaker.
SENTENCE_END = re.compile(r"[.?!][\")»«“”'’]*$")
CONTINUED = re.compile(r"(\.\.\.|…)[\")»«“”'’]*$")
NEW_SPEAKER = re.compile(r"^[-–]\s")
SENTENCE_CUES, SENTENCE_GAP = 3, 2


def ends_sentence(text: str) -> bool:
    t = text.strip()
    return bool(SENTENCE_END.search(t)) and not CONTINUED.search(t)


def sentence_around(cues: list[dict], i: int, mx: int = SENTENCE_CUES) -> tuple[str, tuple[int, int]]:
    def joins(a, b):
        return not ends_sentence(a["text"]) and not NEW_SPEAKER.match(b["text"].strip()) and b["start"] - a["end"] <= SENTENCE_GAP
    frm = to = i
    while frm > 0 and i - frm < mx and joins(cues[frm - 1], cues[frm]):
        frm -= 1
    while to < len(cues) - 1 and to - i < mx and joins(cues[to], cues[to + 1]):
        to += 1
    parts = [c["text"].strip() for c in cues[frm:to + 1]]
    at = sum(len(p) + 1 for p in parts[:i - frm])
    return " ".join(parts), (at, at + len(parts[i - frm]))


def lines(media_id: int, frm: float, to: float) -> list[tuple[str, tuple[int, int]]]:
    """(text, focus) of every line in [frm, to] on both tracks — what Schauen sends to /api/analyze."""
    with db.tx() as conn:
        r = conn.execute("SELECT cues, spoken_cues FROM media WHERE id = ?", (media_id,)).fetchone()
    if not r:
        return []
    out = []
    for track in (r["spoken_cues"], r["cues"]):
        cues = [c for c in json.loads(track or "[]") if not is_non_speech(c.get("text", ""))]
        out += [sentence_around(cues, i) for i, c in enumerate(cues) if c["end"] > frm and c["start"] < to]
    return list(dict.fromkeys(out))


def missing(media_id: int, frm: float, to: float) -> list[tuple[str, str]]:
    found: list = []
    for text, focus in lines(media_id, frm, to):
        analyze.analyze(text, focus, missing=found)
    return list(dict.fromkeys(found))


def ask(word: str, sentence: str) -> dict | None:
    """Ask the KI for one word in its sentence and keep the answer (also "no real word"). None: no KI."""
    info = ai.word_meaning(sentence, word)
    if not info:
        return None
    real = info["real"] and info["gloss"]
    row = {"word": word, "sentence": sentence, "lemma": info["lemma"] if real else None, "gloss": info["gloss"] if real else None,
           "article": info["article"] if real else None, "plural": info["plural"] if real else None,
           "kasus": info["case"] if real else None, "case_reason": info["caseReason"] if real else None,
           "model": config.ANTHROPIC_MODEL, "in_tokens": info["usage"]["in"], "out_tokens": info["usage"]["out"],
           "created_at": db.now_iso()}
    with db.tx() as conn:
        conn.execute(f"INSERT OR REPLACE INTO ki_meanings({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                     tuple(row.values()))
    return row


def fill(media_id: int, frm: float, to: float) -> dict:
    """Ask the KI for every word of [frm, to] that would be highlighted without a meaning."""
    if not ai.available():
        return {"asked": 0, "meanings": 0, "dropped": 0, "ki": False}
    todo = missing(media_id, frm, to)
    asked = meant = failed = 0
    for word, sentence in todo[:MAX_ASK]:
        row = ask(word, sentence)
        if row is None:  # no usable answer: not kept, asked again next time
            failed += 1
            if failed >= FAILS:
                break  # the KI isn't answering
            continue
        failed = 0
        asked += 1
        meant += bool(row["gloss"])
    return {"asked": asked, "meanings": meant, "dropped": asked - meant, "ki": True, "left": len(todo) - asked}


_running: set[tuple[int, float, float]] = set()
_lock = threading.Lock()


def fill_in_background(media_id: int, frm: float, to: float) -> bool:
    """Start fill() for a clip part unless it is already running; returns whether it started."""
    key = (media_id, frm, to)
    if not ai.available():
        return False
    with _lock:
        if key in _running:
            return False
        _running.add(key)

    def run():
        try:
            log.info("#40 meanings %s %s–%s: %s", media_id, frm, to, fill(media_id, frm, to))
        except Exception:
            log.exception("#40 meanings failed")
        finally:
            with _lock:
                _running.discard(key)

    threading.Thread(target=run, daemon=True).start()
    return True


def planned(items: list[dict]) -> list[tuple[int, float, float]]:
    """Each planned clip's next part from the Materialcheck's items (earliest day first)."""
    out = {}
    for it in items:
        if it.get("mediaId") and it.get("range") and it["range"][1]:
            out.setdefault(it["mediaId"], (it["mediaId"], float(it["range"][0]), float(it["range"][1])))
    return list(out.values())
