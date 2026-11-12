"""Check a reading text against the top-2,000 rule.

Usage: .venv/bin/python scripts/check_text.py ../data/texts/t01.json [more files…]
Prints word count, coverage and the words outside the core 2,000 (glossary terms
are listed separately; they still count as unknown for the 5 % rule).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaskade import textcov  # noqa: E402


def main() -> None:
    bad = 0
    for p in sys.argv[1:]:
        t = json.loads(Path(p).read_text(encoding="utf-8"))
        r = textcov.coverage(t["text"], extra_known=set(t.get("names", [])))
        words = len(t["text"].split())
        ok = r["coverage"] >= 0.95 and 150 <= words <= 350
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {Path(p).name}: {words} Wörter, {r['coverage']:.1%} bekannt, "
              f"außerhalb: {', '.join(sorted(set(r['unknown'])))}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
