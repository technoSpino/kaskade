"""Build the ordered German lemma frequency list used by Kaskade.

Input:  hermitdave/FrequencyWords content/2018/de/de_50k.txt (OpenSubtitles 2018,
        CC BY-SA 4.0), downloaded to ~/kaskade-data/freq/de_50k.txt.
Output: data/freq/lemmas.tsv  (rank, lemma, pos, count, top forms) — CC BY-SA 4.0.

Usage:  .venv/bin/python scripts/build_freq.py [path/to/de_50k.txt]
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

import spacy

REPO = Path(__file__).resolve().parents[2]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "kaskade-data/freq/de_50k.txt"
OUT = REPO / "data/freq/lemmas.tsv"
MAX_FORMS = 40000

WORD_RE = re.compile(r"^[a-zäöüß]+(-[a-zäöüß]+)?$")
DROP_POS = {"PROPN", "INTJ", "X", "NUM", "PUNCT", "SYM", "SPACE"}

# Frequent in subtitles but English (or not words a learner should be tested on).
# NOTE: the committed lemmas.tsv was built with an older list that also removed
# German words (man, Job, Baby, Party, Team, Show, Boss, Date, Fan); the core deck
# adds them via data/core-deck/raw/supplement.json. Rebuilding lemmas.tsv shifts
# ranks — the raw deck files and vocab-test pools are keyed on the current ranks.
ENGLISH = set("""
the you yeah hey okay ok oh sorry mr mrs ms sir yes no what is it and to of a i
me my we he she they that this are be do don't go come on hi bye wow god guys
fuck shit damn cool please thanks thank love sweetie honey sexy happy one two three
all right
""".split())

# Forms whose lemma spaCy gets wrong in isolation.
OVERRIDES = {
    "gehst": "gehen", "kommst": "kommen", "weißt": "wissen", "siehst": "sehen",
    "hast": "haben", "bist": "sein", "willst": "wollen", "kannst": "können",
    "musst": "müssen", "sollst": "sollen", "darfst": "dürfen", "magst": "mögen",
    "gibst": "geben", "nimmst": "nehmen", "machst": "machen", "sagst": "sagen",
    "brauchst": "brauchen", "denkst": "denken", "glaubst": "glauben",
    "meinst": "meinen", "redest": "reden", "isst": "essen", "liest": "lesen",
    "läufst": "laufen", "fährst": "fahren", "schläfst": "schlafen",
    "hältst": "halten", "lässt": "lassen", "triffst": "treffen", "hilfst": "helfen",
    "sprichst": "sprechen", "wirst": "werden", "tust": "tun", "verstehst": "verstehen",
    "war": "sein", "waren": "sein", "warst": "sein", "wäre": "sein", "wären": "sein",
    "gewesen": "sein", "ist": "sein", "sind": "sein", "seid": "sein",
    "hatte": "haben", "hatten": "haben", "hätte": "haben", "hätten": "haben",
    "gehabt": "haben", "wurde": "werden", "wurden": "werden", "würde": "werden",
    "würden": "werden", "worden": "werden", "geworden": "werden",
    "mir": "ich", "mich": "ich", "dir": "du", "dich": "du", "uns": "wir",
    "euch": "ihr", "ihm": "er", "ihn": "er", "ihnen": "sie",
    "den": "der", "dem": "der", "des": "der", "die": "der", "das": "der",
    "einen": "ein", "einem": "ein", "einer": "ein", "eines": "ein", "eine": "ein",
    "keinen": "kein", "keinem": "kein", "keiner": "kein", "keine": "kein",
    "meinen": "mein", "meinem": "mein", "meiner": "mein", "meine": "mein",
    "deinen": "dein", "deinem": "dein", "deiner": "dein", "deine": "dein",
    "seinen": "sein (Pron.)", "seinem": "sein (Pron.)", "seiner": "sein (Pron.)",
    "seine": "sein (Pron.)", "ihre": "ihr", "ihren": "ihr", "ihrem": "ihr",
    "ihrer": "ihr", "unsere": "unser", "unseren": "unser", "unserem": "unser",
    "unserer": "unser", "eure": "euer", "euren": "euer",
    "besser": "gut", "beste": "gut", "besten": "gut", "mehr": "viel",
    "meisten": "viel", "lieber": "gern", "am": "an", "im": "in", "zum": "zu",
    "zur": "zu", "vom": "von", "beim": "bei", "ins": "in", "ans": "an",
    # imperatives and other forms spaCy leaves unlemmatised in isolation
    "komm": "kommen", "kommt": "kommen", "mach": "machen", "sag": "sagen",
    "hör": "hören", "lass": "lassen", "lasst": "lassen", "sieh": "sehen",
    "gib": "geben", "schau": "schauen", "geh": "gehen", "bleib": "bleiben",
    "nimm": "nehmen", "hilf": "helfen", "iss": "essen", "vergiss": "vergessen",
    "sei": "sein", "seien": "sein", "wusste": "wissen", "wussten": "wissen",
    "wusstest": "wissen", "musste": "müssen", "mussten": "müssen",
    "musstest": "müssen", "konnte": "können", "konnten": "können",
    "würdest": "werden", "würdet": "werden", "ganzen": "ganz",
    "gefällt": "gefallen", "gefallen": "gefallen", "gefiel": "gefallen",
    "hause": "Haus", "auto": "Auto", "autos": "Auto", "abend": "Abend",
    "abends": "abends", "jungs": "Junge", "scheiße": "Scheiße", "leid": "leid",
    "euer": "euer", "eure": "euer", "dein": "dein", "deine": "dein",
}

# Part of speech corrections for lemmas spaCy mis-tags in isolation.
POS_FIX = {
    "dein": "DET", "euer": "DET", "Auto": "NOUN", "Abend": "NOUN", "Junge": "NOUN",
    "leid": "ADV", "bisschen": "PRON", "ach": "INTJ", "gefallen": "VERB",
}

# Subtitle English / names that slip past the tagger.
ENGLISH |= set("mom dad daddy mommy miss mister lady sergeant captain doc okay".split())


def main() -> None:
    nlp = spacy.load("de_core_news_sm", disable=["parser", "ner"])
    rows = []
    for line in SRC.read_text(encoding="utf-8").splitlines()[:MAX_FORMS]:
        form, count = line.rsplit(" ", 1)
        rows.append((form, int(count)))
    known_forms = {f for f, _ in rows}

    candidates = [(f, c) for f, c in rows if WORD_RE.match(f) and f not in ENGLISH]
    docs = nlp.pipe((f for f, _ in candidates), batch_size=2000)

    counts: dict[str, int] = defaultdict(int)
    pos_of: dict[str, str] = {}
    forms_of: dict[str, list[str]] = defaultdict(list)
    for (form, count), doc in zip(candidates, docs):
        if len(doc) != 1:
            continue
        tok = doc[0]
        if form in OVERRIDES:
            lemma, pos = OVERRIDES[form], tok.pos_ if tok.pos_ not in DROP_POS else "X"
            if lemma == "sein (Pron.)":
                lemma, pos = "sein", "DET"
        else:
            if tok.pos_ in DROP_POS:
                continue
            pos = tok.pos_
            lemma = tok.lemma_ or form
            # Only trust a lemma that itself occurs in the corpus; else keep the form.
            if lemma.lower() not in known_forms:
                lemma = form.capitalize() if pos == "NOUN" else form
            if pos == "NOUN":
                lemma = lemma[:1].upper() + lemma[1:]
            elif lemma[:1].isupper() and pos != "NOUN":
                lemma = lemma.lower()
        pos = POS_FIX.get(lemma, pos)
        if len(lemma) < 2 or pos == "INTJ":
            continue
        counts[lemma] += count
        pos_of.setdefault(lemma, pos)
        if len(forms_of[lemma]) < 4:
            forms_of[lemma].append(form)

    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        fh.write("rank\tlemma\tpos\tcount\tforms\n")
        for i, (lemma, count) in enumerate(ranked, 1):
            fh.write(f"{i}\t{lemma}\t{pos_of[lemma]}\t{count}\t{','.join(forms_of[lemma])}\n")
    print(f"{len(ranked)} lemmas -> {OUT}")


if __name__ == "__main__":
    main()
