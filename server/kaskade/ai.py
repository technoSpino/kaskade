"""Optional AI features. Everything here returns None when ANTHROPIC_API_KEY is unset."""
import json
import logging
import re

from . import config

log = logging.getLogger(__name__)

GRADE_PROMPT = """Du bewertest einen kurzen deutschen Text eines erwachsenen Deutschlerners (Ziel: Zertifikat B1).

Aufgabe ({type}): {situation}
Inhaltspunkte:
{points}
Richtwert: etwa {words} Wörter.

Text des Lerners:
<text>
{text}
</text>

Bewerte nach vier Kriterien (je 0–5 Punkte): Erfüllung (alle Inhaltspunkte, Textsorte, Anrede/Gruß), Kohärenz (Konnektoren, Aufbau), Wortschatz (Spektrum, Richtigkeit), Strukturen (Grammatik, Satzbau).
Antworte NUR mit JSON in genau diesem Format, Texte auf einfachem Deutsch (A2–B1):
{{"level": "A2" | "A2+" | "B1" | "B1+" | "B2", "scores": {{"erfuellung": 0, "kohaerenz": 0, "wortschatz": 0, "strukturen": 0}}, "summary": "zwei Sätze Rückmeldung", "corrections": [{{"original": "…", "korrektur": "…", "erklaerung": "…"}}]}}
Höchstens 5 Korrekturen, die wichtigsten zuerst."""


WORD_PROMPT = """Ein erwachsener Deutschlerner (A2–B1) hat in diesem Satz ein Wort markiert, um es zu lernen.

Satz: „{sentence}“
Wort: „{target}“

Gib für dieses Wort, so wie es in genau diesem Satz steht, an:
- lemma: die Grundform (Verb im Infinitiv, Nomen im Nominativ Singular, Adjektiv ohne Endung)
- gloss: kurze englische Bedeutung der Grundform in diesem Satz (Verben als „to …“), höchstens 6 Wörter
- article: "der", "die" oder "das" bei Nomen, sonst null
- plural: Pluralform ohne Artikel bei Nomen (null, wenn es keinen gibt), sonst null
- case: Kasus des Wortes in diesem Satz, "N", "A", "D" oder "G" — nur bei Nomen und Pronomen, sonst null
- caseReason: bei case ein kurzer Grund auf einfachem Deutsch, z. B. „Subjekt → Nominativ“ oder „mit + Dativ“, sonst null

Antworte NUR mit JSON in genau diesem Format:
{{"lemma": "…", "gloss": "…", "article": null, "plural": null, "case": null, "caseReason": null}}"""


def available() -> bool:
    return config.anthropic_key() is not None


def _client():
    import anthropic  # lazy: only needed with a key

    return anthropic.Anthropic(api_key=config.anthropic_key())


def parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def grade_writing(task: dict, text: str) -> dict | None:
    """Grade a B1-style writing task. None if no key or the call fails."""
    if not available() or not text.strip():
        return None
    prompt = GRADE_PROMPT.format(
        type=task.get("type", ""), situation=task.get("situation", ""),
        points="\n".join(f"- {p}" for p in task.get("points", [])),
        words=task.get("words", 80), text=text.strip(),
    )
    try:
        msg = _client().messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        out = "".join(getattr(b, "text", "") for b in msg.content)
        grade = parse_json(out)
        if grade and "level" in grade:
            return grade
        log.warning("AI grade: unparseable answer")
    except Exception:  # network, auth, quota … — never break the app
        log.exception("AI grade failed")
    return None


def _short(value, limit: int) -> str | None:
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def word_info(sentence: str, target: str) -> dict | None:
    """Lemma, gloss, article/plural and case-with-reason of `target` in `sentence` (#19).

    For mined words the dictionary doesn't know. None if no key, the call fails or the answer
    makes no sense — mining then keeps what the dictionary had.
    """
    if not available():
        return None
    try:
        msg = _client().messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=300,
            timeout=30,
            messages=[{"role": "user", "content": WORD_PROMPT.format(sentence=sentence, target=target)}],
        )
        raw = parse_json("".join(getattr(b, "text", "") for b in msg.content)) or {}
    except Exception:  # network, auth, quota … — never break mining
        log.exception("AI word info failed")
        return None
    lemma = _short(raw.get("lemma"), 60)
    if not lemma:
        log.warning("AI word info: unparseable answer")
        return None
    case = raw.get("case") if raw.get("case") in ("N", "A", "D", "G") else None
    return {
        "lemma": lemma,
        "gloss": _short(raw.get("gloss"), 120),
        "article": raw.get("article") if raw.get("article") in ("der", "die", "das") else None,
        "plural": _short(raw.get("plural"), 60),
        "case": case,
        "caseReason": _short(raw.get("caseReason"), 120) if case else None,
    }
