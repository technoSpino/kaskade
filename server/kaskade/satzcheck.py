"""Satz-Check: subtitle parsing, sentence coverage and Refold gate verdicts."""
import html
import re

TIME_RE = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
)
TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]*\}")

# Refold gates
SIMPLE_GATE = 75       # simple content → Phase 1 done
ADULT_GATE = 80        # adult content + ~2,000 words → ready for 2B
LOWER_2A = 60          # 60–79 % on adult content = solidly in 2A
WORDS_2B = 1900        # "≈ 2,000 words" (vocab estimate is rounded to 50)


def _secs(h, m, s, ms) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_subtitles(text: str) -> list[dict]:
    """Parse SRT or WebVTT into [{start, end, text}], sorted, de-duplicated."""
    text = text.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l for l in block.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            m = TIME_RE.search(line)
            if not m:
                continue
            g = m.groups()
            start, end = _secs(*g[:4]), _secs(*g[4:])
            body = " ".join(TAG_RE.sub("", l).strip() for l in lines[i + 1:])
            body = html.unescape(re.sub(r"\s+", " ", body)).strip()
            if body and end > start:
                cues.append({"start": round(start, 3), "end": round(end, 3), "text": body})
            break
    cues.sort(key=lambda c: c["start"])
    # Auto-generated subtitles repeat rolling lines; drop exact repeats.
    out = []
    for c in cues:
        if out and c["text"] == out[-1]["text"]:
            out[-1]["end"] = max(out[-1]["end"], c["end"])
        else:
            out.append(c)
    return out


NON_SPEECH_RE = re.compile(r"^\s*(?:\*[^*]*\*|\[[^\]]*\]|\([^)]*\))\s*$")
MUSIK_RE = re.compile(r"^musik\.?$", re.I)  # #30: Whisper's word for a theme tune, not a line of dialogue


def is_non_speech(text: str) -> bool:
    """Sound/music cues, not speech: lines fully wrapped in *…*, […] or (…), starting with ♪, or only "Musik"."""
    t = text.strip()
    return not t or t.startswith(("♪", "♫", "#")) or bool(NON_SPEECH_RE.match(t)) or bool(MUSIK_RE.match(t))


def window(cues: list[dict], start: float, length: float = 180) -> list[dict]:
    """Speech cues that begin inside [start, start + length) — sound and music cues don't count."""
    return [c for c in cues if start <= c["start"] < start + length and not is_non_speech(c["text"])]


def summarize(ratings: list[str]) -> dict:
    """ratings: 'v' (verstanden) | 'h' (mit Hilfe) | 's' (zu schwer)."""
    v, h, s = (ratings.count(x) for x in "vhs")
    rated = v + h + s
    coverage = round((v + h) / rated * 100) if rated else 0
    return {"v": v, "h": h, "s": s, "rated": rated, "coverage": coverage}


def verdict(coverage: int, content_type: str, words: int | None) -> dict:
    """Phase verdict against Refold's gates."""
    if content_type == "simple":
        if coverage >= SIMPLE_GATE:
            return {"phase": "2A", "key": "phase1-done", "title": "Phase 1 geschafft",
                    "advice": "Einfacher Inhalt sitzt. Jetzt die 2.000 Kernwörter und Inhalt für Erwachsene mit Untertiteln."}
        return {"phase": "1", "key": "phase1", "title": "Noch Phase 1",
                "advice": "Weiter mit einfachem Inhalt für Erwachsene (Lernserien wie Nicos Weg, Easy German) und Grundwortschatz."}
    if coverage >= ADULT_GATE:
        if words is not None and words >= WORDS_2B:
            return {"phase": "2B", "key": "ready-2b", "title": "Bereit für Phase 2B",
                    "advice": "Ab jetzt Sätze aus echten Serien minen. Die Kernwörter laufen nur noch nebenbei."}
        return {"phase": "2A", "key": "2a-words", "title": "Verständnis reicht — Wortschatz noch nicht",
                "advice": "Satz-Abdeckung über 80 %, aber noch unter ≈ 2.000 Wörtern. Kernwörter weiter, dann 2B."}
    if coverage >= LOWER_2A:
        return {"phase": "2A", "key": "2a", "title": "Phase 2A — fast da",
                "advice": "Weiter Kernwörter (30 min) und interaktiv schauen. Nächster Satz-Check in 4 Wochen."}
    return {"phase": "2A", "key": "too-hard", "title": "Noch zu schwer",
            "advice": "Für den Moment leichteren Inhalt wählen, zum Beispiel klar gesprochene Serien (Der Bergdoktor) oder Lernserien für Erwachsene."}


def speech_only(result: dict, ratings: list[dict], content_type: str) -> dict:
    """A stored run recounted without sound/music lines (runs before follow-up #1 rated them).
    When the number changes, the old one stays visible as coverageAll."""
    speech = [r["rating"] for r in ratings if not is_non_speech(r["text"])]
    if not speech or len(speech) == len(ratings):
        return result
    s = summarize(speech)
    return {**result, **s, "coverageAll": result["coverage"], "nonSpeech": len(ratings) - len(speech),
            "verdict": verdict(s["coverage"], content_type, result.get("words"))}

