"""Vocabulary coverage of a German text against the core deck (top 2,000).

Needs spaCy + de_core_news_sm (requirements-tools.txt). Proper nouns, numbers and
punctuation don't count. A token is "known" if its lemma (or the surface form)
is one of the first 2,000 core-deck lemmas or one of their listed forms.
"""
import json
import re
from functools import lru_cache

from . import config, srs

CORE = 2000
ENDINGS = ("e", "en", "er", "es", "em", "n", "s", "st", "t", "te", "ten")
IRREGULAR = """
dem den des der die das einem einen einer eines ihm ihn ihr ihre ihnen mir mich dir dich uns euch
bin bist ist sind seid war warst waren wart wäre wärst wären gewesen
habe hast hat habt hatte hattest hatten hättest hätte hätten gehabt
werde wirst wird werdet wurde wurdest wurden würde würdest würden geworden
muss musst müsst musste musstest mussten müsste müssten kann kannst könnt konnte konntest konnten könnte könnten
will willst wollt wollte wolltest wollten darf darfst dürft durfte durften dürfte soll sollst sollt sollte sollten
mag magst mochte mochten möchte möchtest möchten weiß weißt wisst wusste wussten gewusst
gibt gibst gab gaben nimmt nimmst nahm nahmen sieht siehst sah sahen liest las isst aß fährt fährst fuhr fuhren
läuft läufst lief liefen hält hältst hielt lässt ließ trifft triffst traf hilft hilfst half spricht sprichst sprach
schläft schlief gefällt gefiel fällt fiel trägt trug wäscht ging gingen kam kamen stand standen saß lag fand fanden
montag dienstag mittwoch donnerstag freitag samstag sonntag januar februar märz april mai juni juli
august september oktober november dezember
dachte dachten brachte brachten kannte nannte rief schrieb blieb blieben trank aß wusch zog zogen bot verlor vergaß
"""
SKIP_POS = {"PROPN", "NUM", "PUNCT", "SYM", "SPACE", "X"}


@lru_cache(maxsize=1)
def nlp():
    import spacy

    return spacy.load("de_core_news_sm", disable=["ner", "parser"])


def _norm(word: str) -> str:
    return re.sub(r"\s*\(.*\)$", "", word).replace("sich ", "").strip().lower()


@lru_cache(maxsize=1)
def known_forms() -> frozenset[str]:
    cards = [c for c in srs.deck() if c["n"] <= CORE]
    known = {_norm(c["lemma"]) for c in cards}
    ranks = {c["rank"] for c in cards}
    # Ranks skipped as "Duplikat" are inflected forms of known words: their forms count too.
    max_rank = max(ranks)
    for f in sorted((config.CONTENT_DIR / "core-deck/raw").glob("r*.json")):
        for e in json.loads(f.read_text(encoding="utf-8")):
            if "skip" in e and str(e["skip"]).startswith("Duplikat") and e["rank"] <= max_rank:
                ranks.add(e["rank"])
    tsv = (config.CONTENT_DIR / "freq/lemmas.tsv").read_text(encoding="utf-8").splitlines()[1:]
    for line in tsv:
        rank, lemma, _pos, _count, forms = line.split("\t")
        if int(rank) in ranks or lemma.lower() in known:
            known.add(lemma.lower())
            known.update(f.lower() for f in forms.split(",") if f)
    # Inflections spaCy sometimes leaves as-is: determiners, pronouns and the
    # irregular present/past forms of core verbs (lemmas.tsv keeps only 4 forms each).
    known.update(IRREGULAR.split())
    return frozenset(known)


def coverage(text: str, extra_known: set[str] | None = None) -> dict:
    """Share of countable tokens covered by the top 2,000 (plus `extra_known` lemmas)."""
    known = known_forms() | {w.lower() for w in (extra_known or set())}
    total, unknown = 0, []
    for tok in nlp()(text):
        if tok.pos_ in SKIP_POS or not tok.is_alpha:
            continue
        total += 1
        lemma, form = tok.lemma_.lower(), tok.text.lower()
        if lemma in known or form in known:
            continue
        # inflected forms spaCy didn't lemmatise: viele → viel, allen → alle
        if any(form.endswith(e) and form[: -len(e)] in known for e in ENDINGS):
            continue
        # regular verb forms: passt → pass + en = passen, wartete → wart + en
        if any(form.endswith(e) and form[: -len(e)] + "en" in known for e in ("st", "t", "te", "ten", "e", "est", "et")):
            continue
        # compounds of two known words (Haus+tür) count as known
        if any(form[:i] in known and form[i:] in known for i in range(3, len(form) - 2)):
            continue
        unknown.append(tok.text)
    share = 1 - len(unknown) / total if total else 1.0
    return {"tokens": total, "unknown": unknown, "coverage": round(share, 4)}
