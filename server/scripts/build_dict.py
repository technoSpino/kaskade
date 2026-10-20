"""Build a compact German→English glossary from the kaikki.org Wiktionary extract.

Source: https://kaikki.org/dictionary/German/ (Wiktionary, CC BY-SA 4.0 / GFDL).
Input:  ~/kaskade-data/dict/kaikki-German.jsonl.gz
Output: ~/kaskade-data/dict/de-en.json  (not in git — see docs/kaskade/PROGRESS.md)
  {"entries": {word: [{"pos", "g"?, "pl"?, "gl": [..]}]}, "forms": {form: lemma}}
"""
import gzip
import json
import re
import sys
from pathlib import Path

DICT = Path.home() / "kaskade-data/dict"
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else DICT / "kaikki-German.jsonl.gz"
OUT = DICT / "de-en.json"
POS = {"noun": "NOUN", "verb": "VERB", "adj": "ADJ", "adv": "ADV", "prep": "ADP", "pron": "PRON",
       "det": "DET", "conj": "CONJ", "particle": "PART", "num": "NUM", "intj": "INTJ", "name": "PROPN",
       "article": "DET", "postp": "ADP", "contraction": "ADP"}
GLOSS_MAX = 3


def clean(g: str) -> str:
    g = re.sub(r"\s+", " ", g).strip()
    return g[:120]


def main() -> None:
    entries: dict[str, list] = {}
    forms: dict[str, str] = {}
    with gzip.open(SRC, "rt", encoding="utf-8") as fh:
        for line in fh:
            e = json.loads(line)
            word, pos = e.get("word"), POS.get(e.get("pos"))
            if not word or not pos or " " in word:
                continue
            glosses, base = [], None
            for s in e.get("senses", []):
                if "form_of" in s or "alt_of" in s:
                    target = (s.get("form_of") or s.get("alt_of"))[0].get("word")
                    base = base or target
                    continue
                for g in s.get("glosses", [])[:1]:
                    if g and clean(g) not in glosses:
                        glosses.append(clean(g))
            if not glosses:
                if base and word not in forms and base != word:
                    forms[word] = base
                continue
            item = {"pos": pos, "gl": glosses[:GLOSS_MAX]}
            if pos == "NOUN":
                for t in e.get("head_templates", []):
                    g = str(t.get("args", {}).get("1", ""))[:1]
                    if g in ("m", "f", "n"):
                        item["g"] = g
                        break
                pl = next((f["form"] for f in e.get("forms", [])
                           if "plural" in f.get("tags", []) and "nominative" in f.get("tags", [])
                           and f.get("form") not in ("-", "")), None)
                if pl:
                    item["pl"] = pl.split()[-1]
            entries.setdefault(word, []).append(item)
    OUT.write_text(json.dumps({"entries": entries, "forms": forms}, ensure_ascii=False), encoding="utf-8")
    print(f"{len(entries)} words, {len(forms)} forms -> {OUT} ({OUT.stat().st_size // 1_000_000} MB)")


if __name__ == "__main__":
    main()
