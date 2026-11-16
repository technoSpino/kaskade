"""Validate raw core-deck files and merge them into numbered batches of 100.

Usage:
  .venv/bin/python scripts/merge_deck.py --check data/core-deck/raw/r0001-0100.json
  .venv/bin/python scripts/merge_deck.py          # validate all raw files, write NNNN.json
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DECK = REPO / "data/core-deck"
RAW = DECK / "raw"
REQUIRED = ("rank", "lemma", "pos", "display", "gloss", "sentence", "target", "en")
ARTICLE_RE = re.compile(r"^(der|die|das) ")
CASES = {None, "N", "A", "D", "G"}
ORIGINS = {"ai", "real"}


def norm(lemma: str) -> str:
    # Case-sensitive on purpose: "Leben" (noun) and "leben" (verb) are different cards.
    return lemma.strip()


def check_card(c: dict) -> list[str]:
    errs = []
    if "skip" in c:
        if not isinstance(c.get("rank"), int) or not str(c["skip"]).strip():
            errs.append("skip entry needs rank and reason")
        return errs
    for k in REQUIRED:
        if not str(c.get(k, "")).strip():
            errs.append(f"missing {k}")
    if errs:
        return errs
    if c["target"] not in c["sentence"]:
        errs.append(f"target {c['target']!r} not in sentence")
    if c.get("case") not in CASES:
        errs.append(f"bad case {c.get('case')!r}")
    if c.get("origin", "ai") not in ORIGINS or (c.get("origin") == "real" and not c.get("source")):
        errs.append("origin must be ai, or real with a source")
    if c["pos"] == "NOUN" and not ARTICLE_RE.match(c["display"]) and "Plural" not in c["display"]:
        errs.append("noun display needs der/die/das")
    if c["pos"] == "NOUN" and not c["lemma"][:1].isupper():
        errs.append("noun lemma must be capitalised")
    s = c["sentence"]
    if not s[:1].isupper() and not s[:1] in "„\"":
        errs.append("sentence must start with a capital")
    if s[-1] not in ".!?…“\"":
        errs.append("sentence must end with punctuation")
    if "  " in s:
        errs.append("double space in sentence")
    return errs


def load(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: top level must be a list")
    return data


def check_file(path: Path) -> int:
    n_err = 0
    for c in load(path):
        for e in check_card(c):
            n_err += 1
            print(f"{path.name} rank {c.get('rank')}: {e}")
    return n_err


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        errors = sum(check_file(Path(p)) for p in sys.argv[2:])
        print("OK" if not errors else f"{errors} problem(s)")
        sys.exit(1 if errors else 0)

    cards, seen, errors, skipped = [], set(), 0, 0
    # supplement.json: words the automatic list dropped by mistake. They carry their
    # corpus count and are slotted in where that count belongs in the frequency order.
    counts = [int(l.split("\t")[3]) for l in (REPO / "data/freq/lemmas.tsv").read_text(encoding="utf-8").splitlines()[1:]]
    for path in [*sorted(RAW.glob("r*.json")), RAW / "supplement.json"]:
        if not path.exists():
            continue
        for c in load(path):
            errs = check_card(c)
            if errs:
                errors += len(errs)
                for e in errs:
                    print(f"{path.name} rank {c.get('rank')}: {e}")
                continue
            if "skip" in c:
                skipped += 1
                continue
            key = norm(c["lemma"])
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            c["order"] = c["rank"] if "count" not in c else sum(n > c["count"] for n in counts) + 0.5
            cards.append(c)
    cards.sort(key=lambda c: c["order"])
    if errors:
        print(f"{errors} problem(s) — fix before merging")
        sys.exit(1)

    for old in DECK.glob("[0-9][0-9][0-9][0-9].json"):
        old.unlink()
    for start in range(0, len(cards), 100):
        batch = []
        for i, c in enumerate(cards[start:start + 100], start + 1):
            # id is tied to the frequency rank, so it stays stable when cards are
            # added or removed later (review history in the DB keys on it).
            out = {"id": f"core:r{c['rank']:05d}", "n": i}
            out.update({k: c.get(k) for k in (*REQUIRED, "note", "case")})
            out["order"] = c["order"]
            # The example sentences are written for Kaskade (AI); a card from real input
            # would carry origin "real" and its source in the raw file.
            out["origin"] = c.get("origin", "ai")
            if c.get("source"):
                out["source"] = c["source"]
            batch.append(out)
        name = DECK / f"{start // 100 + 1:04d}.json"
        name.write_text(json.dumps(batch, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(cards)} cards in {(len(cards) + 99) // 100} batches, {skipped} skipped/duplicates")


if __name__ == "__main__":
    main()
