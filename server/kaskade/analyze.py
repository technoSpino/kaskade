"""Reader analysis: lemma, POS, case lens (N/A/D/G noun phrases + what governs them),
word states from the learner's cards and a short gloss.

spaCy de_core_news_sm (with parser) does the linguistics; glosses come from the core
deck first, then from the Wiktionary glossary in ~/kaskade-data/dict/de-en.json.
"""
import json
import re
from functools import lru_cache

from . import config, db, srs

CASE = {"Nom": "N", "Acc": "A", "Dat": "D", "Gen": "G"}
CASE_NAME = {"N": "Nominativ", "A": "Akkusativ", "D": "Dativ", "G": "Genitiv"}
TWO_WAY = {"an", "auf", "hinter", "in", "neben", "über", "unter", "vor", "zwischen"}
CONTRACTED = {"im": "in dem", "am": "an dem", "ans": "an das", "ins": "in das", "zum": "zu dem",
              "zur": "zu der", "vom": "von dem", "beim": "bei dem", "aufs": "auf das", "fürs": "für das"}
CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV"}
ARTICLE = {"m": "der", "f": "die", "n": "das"}
# Which cases a preposition allows (contractions fix the case: im = in dem → D, ins = in das → A).
PREP_CASES = {
    **{p: {"A"} for p in ("durch", "für", "gegen", "ohne", "um", "bis", "entlang", "wider", "ins", "ans", "aufs", "fürs")},
    **{p: {"D"} for p in ("aus", "bei", "mit", "nach", "seit", "von", "zu", "gegenüber", "ab", "außer", "samt",
                          "entgegen", "im", "am", "zum", "zur", "vom", "beim")},
    **{p: {"G", "D"} for p in ("wegen", "während", "trotz", "statt", "anstatt", "laut", "dank")},
    **{p: {"G"} for p in ("außerhalb", "innerhalb", "aufgrund", "oberhalb", "unterhalb", "jenseits", "diesseits")},
    **{p: {"A", "D"} for p in TWO_WAY},
}
ROLE_CASE = {"sb": "N", "pd": "N", "oa": "A", "da": "D", "og": "G", "ag": "G"}


@lru_cache(maxsize=1)
def nlp():
    import spacy

    return spacy.load("de_core_news_sm")


@lru_cache(maxsize=1)
def dictionary() -> dict:
    path = config.DATA_DIR / "dict/de-en.json"
    if not path.exists():
        return {"entries": {}, "forms": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(lemma: str) -> str:
    return lemma.split(" (")[0].replace("sich ", "").strip().lower()


def _is_noun(lemma: str) -> bool:
    return lemma.split(" (")[0].replace("sich ", "").strip()[:1].isupper()


@lru_cache(maxsize=1)
def deck_by_lemma() -> dict[str, dict]:
    out = {}
    for c in srs.deck():
        out.setdefault(_norm(c["lemma"]), c)
    return out


def card_states() -> dict[str, str]:
    """card id → neu | lernend | bekannt."""
    with db.tx() as conn:
        rows = conn.execute("SELECT id, status, fsrs FROM cards").fetchall()
    out = {}
    for r in rows:
        if r["status"] == "known":
            out[r["id"]] = "bekannt"
        elif r["status"] in ("learning", "suspended"):
            stab = (json.loads(r["fsrs"]).get("stability") or 0) if r["fsrs"] else 0
            out[r["id"]] = "bekannt" if stab >= 21 else "lernend"
    return out


DEFAULT_CORE_KNOWN = 500


def core_known_estimate() -> int:
    """How many core words the learner probably knows (last vocab test), for unseen cards."""
    with db.tx() as conn:
        row = conn.execute("SELECT result FROM vocab_tests ORDER BY id DESC LIMIT 1").fetchone()
    return json.loads(row["result"]).get("coreKnown", DEFAULT_CORE_KNOWN) if row else DEFAULT_CORE_KNOWN


def word_state(card: dict | None, states: dict[str, str], estimate: int) -> str:
    """neu | lernend | bekannt. Unseen core cards inside the measured range count as known."""
    if not card:
        return "neu"
    if card["id"] in states:
        return states[card["id"]]
    return "bekannt" if (card.get("n") or 10**9) <= estimate else "neu"


def lookup(lemma: str, text: str, pos: str) -> dict | None:
    d = dictionary()
    for word in (lemma, text, d["forms"].get(text), d["forms"].get(text.lower())):
        if not word:
            continue
        items = d["entries"].get(word) or d["entries"].get(word.capitalize() if pos == "NOUN" else word.lower())
        if items:
            match = next((i for i in items if i["pos"] == pos), items[0])
            return {"word": word, **match}
    return None


# ── #40: a meaning for what the dictionary lookup misses ─────────────────────
# Inflected forms → base form, colloquial particle verbs → standard verb, compounds → known parts.
COLLOQUIAL = {"raus": ("heraus",), "rein": ("herein",), "rüber": ("herüber", "hinüber"), "runter": ("herunter",),
              "rauf": ("herauf",), "ran": ("heran",), "rum": ("herum",)}
PARTICLES = sorted({"ab", "an", "auf", "aus", "bei", "ein", "mit", "nach", "vor", "weg", "zu", "zurück", "zusammen",
                    "um", "durch", "über", "unter", "wieder", "fest", "los", "her", "hin", "heraus", "herein",
                    "herüber", "hinüber", "herunter", "herauf", "heran", "herum", "hinaus", "hinein", "weiter",
                    "fort", "vorbei", "entgegen", "gegenüber", "teil", "statt", "hoch", "nieder", "dran", "drauf"},
                   key=len, reverse=True)
NOUN_ENDINGS = ("n", "en", "s")  # the rest is in the dictionary's forms (Basser is no Bass)
VERB_ENDINGS = ("t", "et", "st", "est", "e", "te", "ten", "tet", "test", "en", "n")
ADJ_ENDINGS = ("e", "en", "er", "es", "em")
LINKS = ("", "s", "es", "n", "en", "e", "er", "ns", "ens")  # Fugenelemente: Betreuung|s|bedarf, Rente|n|kasse
NOT_HEADS = {"Schaft", "Schaften", "Ismus"}  # suffixes that are also words: Paten|schaft is no compound
COMPOUND_POS = {"NOUN", "VERB", "ADJ"}


def _items(word: str, pos: str | None = None) -> list[dict]:
    items = dictionary()["entries"].get(word) or []
    return [i for i in items if i["pos"] == pos] if pos else items


def _gloss(item: dict) -> str:
    return "; ".join(item["gl"][:2])


def _short(item: dict) -> str:
    """A part's gloss in a compound: its first meaning, without the explanation (causative of stehen: …, (…))."""
    g = item["gl"][0].split(";")[0].split(":")[-1]
    g = re.sub(r"\s*\([^)]*\)", "", g)
    return ", ".join(p.strip() for p in g.split(",")[:2] if p.strip())


def base_form(word: str, pos: str | None = None) -> tuple[str, dict] | None:
    """(headword, dictionary item) for one word form: as it is, through the dictionary's forms, or
    without an inflection ending (Stellschrauben → …schraube, umschaut → umschauen). `pos` limits it."""
    d = dictionary()
    noun = word[:1].upper() + word[1:]
    tries = [word, word.lower(), noun, d["forms"].get(word), d["forms"].get(word.lower()), d["forms"].get(noun)]
    if pos in (None, "NOUN"):
        tries += [noun[:-len(e)] for e in NOUN_ENDINGS if noun.endswith(e) and len(noun) - len(e) >= 3]
    low = word.lower()
    if pos in (None, "VERB"):
        tries += [low[:-len(e)] + inf for e in VERB_ENDINGS if low.endswith(e) and len(low) - len(e) >= 2 for inf in ("en", "n")]
    if pos in (None, "ADJ"):
        tries += [low[:-len(e)] for e in ADJ_ENDINGS if low.endswith(e) and len(low) - len(e) >= 3]
    for w in dict.fromkeys(t for t in tries if t):
        items = _items(w, pos) or ([] if pos else _items(w))
        if items and (pos != "NOUN" or w[:1].isupper()):
            return w, items[0]
    return None


def _verb(word: str) -> tuple[str, dict, str | None] | None:
    """A particle verb in any form → (infinitive, item, note): auffängt → auffangen, zurückwill → zurückwollen,
    rausbekommt → herausbekommen, rauszukriegen → herauskriegen (zu inside drops out)."""
    low = word.lower()
    starts = [(low, None)]
    for short, full in COLLOQUIAL.items():
        if low.startswith(short) and not low.startswith(full[0]):
            starts += [(f + low[len(short):], f"{short}- = {f}- (umgangssprachlich)") for f in full]
    for w, note in starts:
        if note and (hit := base_form(w, "VERB")):
            return hit[0], hit[1], note
        for p in PARTICLES:
            rest = w[len(p):]
            if not w.startswith(p) or len(rest) < 3:
                continue
            for r in (rest, rest[2:] if rest.startswith("zu") and len(rest) > 4 else None):
                root = r and base_form(r, "VERB")
                if root and (items := _items(p + root[0], "VERB")):
                    return p + root[0], items[0], note
    return None


def _modifier(part: str, depth: int, nouny: bool = True) -> list[tuple[str, str, dict]] | None:
    """The front part of a compound → [(shown, headword, item)]: a noun with a linking element (Kinder,
    Betreuungs → Betreuung, Namens → Name), another word (sozial), a verb stem (Stell → stellen) or itself a
    compound (Arbeitssozial). In a verb (pleite|gehen) only a whole word: no zuge|losen."""
    links = LINKS if nouny else ("",)
    for want in ("NOUN", None):  # Namens|änderung is Name + Änderung before it is "namens"
        for link in links:
            if link and not part.endswith(link):
                continue
            stem = part[:len(part) - len(link)] if link else part
            if len(stem) < 3:
                continue
            for w in dict.fromkeys((stem, stem.lower(), stem[:1].upper() + stem[1:].lower())):
                items = _items(w, want)
                if items and (want != "NOUN" or w[:1].isupper()):
                    shown = w if link in ("", "s", "es", "ns", "ens") else part[:1] + part[1:].lower()
                    return [(shown, w, items[0])]
    for inf in (part.lower() + "en", part.lower() + "n"):
        if nouny and len(part) >= 3 and (items := _items(inf, "VERB")):
            return [(part[:1] + part[1:].lower(), inf, items[0])]
    if nouny and depth < 1:
        split = _split(part, None, depth + 1)
        if split:
            return split[1]
    return None


def _split(word: str, pos: str | None, depth: int = 0) -> tuple[int, list[tuple[str, str, dict]]] | None:
    """Longest known head first: Kinder|zuschlag, Sozial|leistungen, Rente|n|kasse → (where the head
    starts, [(shown, headword, item)] with the head last)."""
    for k in range(3, len(word) - 2):
        head = word[k:]
        found = base_form(head[:1].upper() + head[1:] if pos == "NOUN" else head, pos)
        if not found or found[0] in NOT_HEADS or len(found[0]) < 3:
            continue
        front = _modifier(word[:k], depth, pos != "VERB")
        if front:
            return k, [*front, (found[0], found[0], found[1])]
    return None


def compound(text: str, pos: str) -> dict | None:
    """'Kinderzuschlag = Kinder + Zuschlag' with both glosses; a noun gets the head's article and plural
    (der Kinderzuschlag · die Kinderzuschläge). Same shape as a dictionary item, plus `compound`."""
    found = _split(text, pos)
    if not found:
        return None
    k, parts = found
    head, item = parts[-1][1], parts[-1][2]
    front = text[:k]
    word = front + (head.lower() if pos == "NOUN" else head)
    out = {"word": word, "pos": pos, "gl": [" + ".join(_short(p[2]) for p in parts)],
           "compound": {"text": f"{word} = {' + '.join(p[0] for p in parts)}",
                        "parts": [{"text": p[0], "lemma": p[1], "gloss": _short(p[2])} for p in parts]}}
    if pos == "NOUN" and item.get("g"):
        out["g"] = item["g"]
        if item.get("pl"):
            out["pl"] = front + item["pl"].lower()
    return out


def derive(text: str, pos: str, tag: str = "") -> dict | None:
    """#40: a meaning the plain lookup missed — base form, particle verb, compound — as a dictionary item
    with `word` (its headword) and maybe `note` (raus- = heraus-) or `compound`."""
    kind = "ADJ" if tag == "ADJD" else pos
    if kind == "NOUN":
        hit = base_form(text, "NOUN")
        return {"word": hit[0], **hit[1]} if hit else compound(text, "NOUN")
    if kind in ("ADJ", "ADV") and (hit := base_form(text, kind)):
        return {"word": hit[0], **hit[1]}
    if text[:1].islower() or kind == "VERB":
        if hit := base_form(text, "VERB"):
            return {"word": hit[0], **hit[1]}
        if hit := _verb(text):
            return {"word": hit[0], **hit[1], **({"note": hit[2]} if hit[2] else {})}
    return compound(text, kind) if kind in COMPOUND_POS else None


def derived_lemma(lemma: str) -> bool:
    """#40: a lemma the lookup chain explains (a compound like Kinderzuschlag, a particle verb)."""
    kinds = ("NOUN",) if lemma[:1].isupper() else ("VERB", "ADJ")
    return any(derive(lemma, k) for k in kinds)


def known_lemma(lemma: str) -> bool:
    """Whether a lemma is a headword of the core deck or the dictionary."""
    entries = dictionary()["entries"]
    return _norm(lemma) in deck_by_lemma() or any(w in entries for w in (lemma, lemma.lower(), lemma.capitalize()))


def explain(case: str, gov: dict | None) -> str:
    name = CASE_NAME[case]
    if not gov:
        return name
    if gov["kind"] == "prep":
        p = gov["word"]
        base = CONTRACTED.get(p, p).split()[0]
        txt = f"{p} ({CONTRACTED[p]}) + {name}" if p in CONTRACTED else f"{p} + {name}"
        if base in TWO_WAY:
            txt += " · Wechselpräposition: Wo? → Dativ, Wohin? → Akkusativ"
        return txt
    labels = {"sb": f"Subjekt → {name}", "oa": f"Akkusativobjekt von „{gov['word']}“",
              "da": f"Dativobjekt von „{gov['word']}“", "og": f"Genitivobjekt von „{gov['word']}“",
              "ag": "Genitivattribut (wessen?)", "pd": f"Prädikativ → {name}"}
    return labels.get(gov["role"], name)


def sure_case(ch) -> tuple[str, dict] | None:
    """The case of a noun phrase — only when the parser is sure (#19), else None (no badge).

    Sure means: every case-marked word of the phrase has the same case, and something in the
    sentence demands exactly that case — the preposition before it (mit → D, in → A or D …) or
    its role (subject → N, accusative object → A …; in "das Reich und die Herrlichkeit" the
    second phrase takes the role of the first). Morphology and syntax disagree → None.
    """
    cases = {CASE[c] for t in ch for c in t.morph.get("Case") if c in CASE}
    if len(cases) != 1:
        return None
    case = cases.pop()
    root = ch.root
    while root.dep_ in ("cj", "cd") and root.head is not root:
        root = root.head  # coordination: the first conjunct carries the role
    head = root.head
    if head.pos_ == "ADP" and root.dep_ == "nk":
        word = head.text.lower()
        if case not in PREP_CASES.get(word, ()):
            return None
        return case, {"kind": "prep", "word": word, "role": "prep", "i": head.i}
    if ROLE_CASE.get(root.dep_) == case:
        return case, {"kind": "verb" if head.pos_ in ("VERB", "AUX") else "word", "word": head.lemma_,
                      "role": root.dep_, "i": head.i}
    return None


def card_entry(card: dict) -> dict:
    return {"gloss": card["gloss"], "display": card["display"], "cardId": card["id"], "lemma": card["lemma"]}


def separable(doc) -> dict[int, dict]:
    """#34: a split-off prefix and its verb (fällt … ein) → the particle verb (einfallen) for both tokens.

    Only a real particle (tag PTKVZ, dep svp, head a verb) — on a cut line "… lag ein" spaCy makes the
    article `ein` an svp too. Joined only when the particle verb is a core card or a dictionary verb:
    the parser's false pairs ("trainierst … wieder", "Blut dran") are no headwords and stay as they were.
    Returns token i → {entry (with the verb form `target` and `split` "fällt … ein"), card, lemma, pair}.
    """
    d = dictionary()
    by_lemma = deck_by_lemma()
    out = {}
    for t in doc:
        verb = t.head
        if t.tag_ != "PTKVZ" or t.dep_ != "svp" or verb is t or verb.pos_ not in ("VERB", "AUX"):
            continue
        for base in dict.fromkeys(b for b in (verb.lemma_, d["forms"].get(verb.text), d["forms"].get(verb.text.lower())) if b):
            lemma = t.text.lower() + base.lower()
            card = by_lemma.get(lemma)
            verbs = [e for e in d["entries"].get(lemma, []) if e["pos"] == "VERB"]
            if card or verbs:
                entry = card_entry(card) if card else {"gloss": "; ".join(verbs[0]["gl"][:2]), "display": lemma,
                                                       "cardId": None, "lemma": lemma}
                entry["target"] = verb.text  # Satz minen on either word marks the verb in the card
                entry["split"] = f"{verb.text} … {t.text}"
                for a, b in ((t, verb), (verb, t)):
                    out[a.i] = {"entry": entry, "card": card, "lemma": lemma, "pair": b.i}
                break
    return out


def analyze(text: str, focus: tuple[int, int] | None = None, missing: list | None = None,
            glossed: set[str] | frozenset = frozenset()) -> dict:
    """The analysis of `text`. With `focus` (character range), only the tokens there are returned —
    parsed with the whole text around them (#34: a subtitle line inside its sentence).
    #40: `missing` collects (word, sentence) of the words that would be highlighted but have no meaning
    and weren't asked yet — for meanings.fill, which asks the KI ahead of time. `glossed`: words the
    page itself explains (a Lesen text's glossary), highlighted without a dictionary meaning."""
    doc = nlp()(text)
    unglossed = []
    states = card_states()
    by_lemma = deck_by_lemma()
    estimate = core_known_estimate()
    joined = separable(doc)

    chunks = []
    for ch in doc.noun_chunks:
        sure = sure_case(ch)
        if not sure:
            continue
        case, gov = sure
        text = explain(case, gov)
        if "Yes" in ch.root.morph.get("Reflex"):
            text = f"Reflexivpronomen → {CASE_NAME[case]}"
        chunks.append({"start": ch.start, "end": ch.end, "case": case, "gov": gov, "explain": text})

    chunk_of = {}
    for n, ch in enumerate(chunks):
        for i in range(ch["start"], ch["end"]):
            chunk_of[i] = n

    tokens = []
    for t in doc:
        if focus and not focus[0] <= t.idx < focus[1]:
            continue
        if t.i in joined:
            j = joined[t.i]
            tokens.append({
                "i": t.i, "text": t.text, "ws": t.whitespace_, "lemma": j["lemma"], "pos": t.pos_,
                "state": word_state(j["card"], states, estimate), "chunk": chunk_of.get(t.i), "entry": j["entry"],
                "sent": t.sent.start, "pair": j["pair"],
            })
            continue
        lemma = t.lemma_ if t.pos_ != "NOUN" else t.lemma_[:1].upper() + t.lemma_[1:]
        card = by_lemma.get(_norm(lemma)) if t.is_alpha else None
        if card and _is_noun(card["lemma"]) != (t.pos_ == "NOUN"):
            card = None  # the noun "Reich" is not the adjective card "reich"
        state = None
        if t.is_alpha and t.pos_ in CONTENT_POS:
            state = word_state(card, states, estimate)
        entry = None
        if t.is_alpha and t.pos_ not in ("PUNCT", "PROPN", "NUM"):
            entry = card_entry(card) if card else None
            if not entry:
                d = lookup(lemma, t.text, t.pos_) or derive(t.text, t.pos_, t.tag_)
                if d:
                    entry = dict_entry(d)
        tokens.append({
            "i": t.i, "text": t.text, "ws": t.whitespace_, "lemma": lemma, "pos": t.pos_,
            "state": state, "chunk": chunk_of.get(t.i), "entry": entry, "sent": t.sent.start,
        })
        if state in HIGHLIGHT and not (entry or {}).get("gloss") and t.text not in glossed:
            unglossed.append((tokens[-1], t.text, t.sent.text.strip()))
    # #40: a highlighted word has a meaning — the KI's (asked beforehand, cached), else no highlight
    ki = ki_cached({(w, s) for _, w, s in unglossed})
    for tok, w, s in unglossed:
        got = ki.get((w, s))
        if got and got["gloss"]:
            tok["entry"] = ki_entry(got)
        else:
            tok["state"] = None
            if got is None and missing is not None:
                missing.append((w, s))
    sentences = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in doc.sents]
    return {"tokens": tokens, "chunks": chunks, "sentences": sentences}


HIGHLIGHT = ("neu", "lernend")


def dict_entry(d: dict) -> dict:
    display = d["word"]
    if d.get("g"):
        display = f"{ARTICLE[d['g']]} {d['word']}" + (f" · die {d['pl']}" if d.get("pl") else "")
    # the dictionary's headword beats spaCy's guess (versaust → versauen, not "versausen")
    entry = {"gloss": "; ".join(d["gl"][:2]), "display": display, "cardId": None, "lemma": d["word"]}
    if d.get("compound"):
        entry["compound"] = d["compound"]
    if d.get("note"):
        entry["note"] = d["note"]
    return entry


def ki_cached(pairs: set[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    """#40: the KI's answers for (word, sentence) pairs asked before (gloss NULL = not a real word)."""
    if not pairs:
        return {}
    out = {}
    with db.tx() as conn:
        for w in {w for w, _ in pairs}:
            for r in conn.execute("SELECT * FROM ki_meanings WHERE word = ?", (w,)):
                if (w, r["sentence"]) in pairs:
                    out[(w, r["sentence"])] = dict(r)
    return out


def ki_entry(r: dict) -> dict:
    display = r["lemma"]
    if r["article"]:
        display = f"{r['article']} {r['lemma']}" + (f" · die {r['plural']}" if r["plural"] else "")
    entry = {"gloss": r["gloss"], "display": display, "cardId": None, "lemma": r["lemma"], "ai": ["lemma", "gloss"]}
    if r["kasus"]:  # mined, the card gets the KI's case too — like a mined word the dictionary didn't know (#19)
        entry.update(case=r["kasus"], caseReason=r["case_reason"])
        entry["ai"].append("case")
    return entry
