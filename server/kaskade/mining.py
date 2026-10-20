"""Mined cards (#19): what the dictionary doesn't know, the KI fills in — and says so.

A mined word carries lemma, display (article · plural), gloss and case. When the dictionary has
no gloss or doesn't know the lemma, Claude is asked for that word in that sentence; the fields
it filled are listed in `ai` and the card shows them with a "KI" mark. Without a key nothing
changes: the card keeps what the dictionary had.
"""
import json

from . import ai, analyze, config, db

AI_FIELDS = ("lemma", "gloss", "case")


def needs_ai(lemma: str, gloss: str | None) -> bool:
    g = (gloss or "").strip()
    return not g or g == "—" or not analyze.known_lemma(lemma)


def noun_display(lemma: str, article: str | None, plural: str | None) -> str:
    if not article:
        return lemma
    return f"{article} {lemma}" + (f" · die {plural}" if plural else "")


def enrich(sentence: str, target: str, word: dict) -> dict:
    """word = {lemma, display, gloss, case, note}; returns it with the KI's fields and `ai`."""
    out = {**word, "ai": list(word.get("ai") or [])}
    if not needs_ai(word["lemma"], word.get("gloss")):
        return out
    info = ai.word_info(sentence, target)
    if not info:
        return out

    def mark(field):
        if field not in out["ai"]:
            out["ai"].append(field)

    if not analyze.known_lemma(word["lemma"]):
        out["lemma"] = info["lemma"]
        out["display"] = noun_display(info["lemma"], info["article"], info["plural"])
        mark("lemma")
    g = (word.get("gloss") or "").strip()
    if (not g or g == "—") and info["gloss"]:
        out["gloss"] = info["gloss"]
        mark("gloss")
    if not word.get("case") and info["case"]:
        out["case"] = info["case"]
        if not word.get("note"):
            out["note"] = info["caseReason"]
        mark("case")
    return out


def row(n: int):
    with db.tx() as conn:
        return conn.execute("SELECT * FROM mined WHERE id = ?", (n,)).fetchone()


def targets(r) -> list[str]:
    return [r["target"], *(w["target"] for w in json.loads(r["words"] or "[]"))]


def delete(n: int) -> bool:
    """Remove a mined card with its schedule, its review history and its audio snippet."""
    r = row(n)
    if not r:
        return False
    card_id = f"mine:{n}"
    with db.tx() as conn:
        conn.execute("DELETE FROM review_log WHERE card_id = ?", (card_id,))
        conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        conn.execute("DELETE FROM mined WHERE id = ?", (n,))
    if r["audio"]:
        (config.SNIPPETS_DIR / r["audio"]).unlink(missing_ok=True)
    return True
