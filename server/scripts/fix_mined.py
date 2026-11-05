"""#19: re-check cards mined before the fix — case only where the parser is sure, the dictionary's
headword as lemma, and the KI (marked) for what the dictionary still doesn't know.

Usage: .venv/bin/python scripts/fix_mined.py [--dry-run]
       (with the key: set -a; . ~/kaskade-data/.env; set +a — first)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaskade import analyze, db, mining  # noqa: E402


def parser_view(sentence: str, target: str) -> dict:
    """What today's analysis says about `target`: sure case (or None) and the dictionary headword."""
    r = analyze.analyze(sentence)
    tok = next((t for t in r["tokens"] if t["text"] == target), None)
    if not tok:
        return {"case": None, "explain": None, "lemma": None}
    ch = r["chunks"][tok["chunk"]] if tok["chunk"] is not None else None
    return {"case": ch and ch["case"], "explain": ch and ch["explain"], "lemma": (tok["entry"] or {}).get("lemma")}


def fixed(sentence: str, w: dict) -> dict:
    """w = {target, lemma, display, gloss, case, note, ai} → corrected copy."""
    out = dict(w)
    p = parser_view(sentence, w["target"])
    if w.get("case") and "case" not in w.get("ai", []) and w["case"] != p["case"]:
        out["case"], out["note"] = p["case"], p["explain"]  # no sure case → no badge, and no case note
    if not analyze.known_lemma(w["lemma"]) and p["lemma"] and analyze.known_lemma(p["lemma"]):
        out["lemma"] = p["lemma"]  # versausen → versauen, straight from the dictionary
        if w["display"] == w["lemma"]:
            out["display"] = p["lemma"]
    return mining.enrich(sentence, w["target"], out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    db.init()
    with db.tx() as conn:
        rows = conn.execute("SELECT * FROM mined ORDER BY id").fetchall()
    for r in rows:
        main_word = {"target": r["target"], "lemma": r["lemma"], "display": r["display"], "gloss": r["gloss"],
                     "case": r["kasus"], "note": r["note"], "ai": json.loads(r["ai_fields"] or "[]")}
        new = fixed(r["sentence"], main_word)
        words = [fixed(r["sentence"], w) for w in json.loads(r["words"] or "[]")]
        changes = {k: (main_word[k], new[k]) for k in main_word if main_word[k] != new[k]}
        print(f"mine:{r['id']} {r['target']}: {changes or 'ok'}")
        if args.dry_run or (not changes and words == json.loads(r["words"] or "[]")):
            continue
        with db.tx() as conn:
            conn.execute(
                "UPDATE mined SET lemma = ?, display = ?, gloss = ?, kasus = ?, note = ?, ai_fields = ?, words = ?"
                " WHERE id = ?",
                (new["lemma"], new["display"], new["gloss"] or "—", new["case"], new["note"], json.dumps(new["ai"]),
                 json.dumps(words, ensure_ascii=False) if words else None, r["id"]))


if __name__ == "__main__":
    main()
