"""#29: a "gesprochen" track per clip — what is actually said, from Whisper transcripts.

ARD/ZDF subtitles are condensed for reading speed (words and whole lines missing), so a mined card
sentence may not match its own audio. Matt's Mac transcribes the clips (tools/mac-transcribe/) into
~/kaskade-data/transcripts/<media_file stem>.whisper.json; this module turns the words into
subtitle-like lines and stores them as media.spoken_cues. Rebuilding is idempotent:

    .venv/bin/python -m kaskade.transcripts

(also run by the 06:30 Materialcheck). Transcript text is user data — never in the repo.
"""
import bisect
import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean

from . import config, db
from .satzcheck import is_non_speech

PAUSE = 0.7          # a pause this long between words ends a line
MAX_WORDS = 14       # a longer line is split …
MAX_SECONDS = 6.0    # … as is one that lasts longer
MIN_SECONDS = 0.6    # shorter lines join a neighbour, unless they are a whole sentence ("Ich?") …
JOIN_GAP = 2.0       # … but never across a longer silence (that made a 13-s line in Schweigen)
OVERLAP = 0.5        # a Whisper segment "overlaps" an ARD speech cue within this margin
MIN_P = 0.65         # mean word probability below which a segment without ARD speech is dropped
NEAR = 0.5           # ARD cue window for respelling and gap fill: [start − 0.5 s, end + 0.5 s]
SIMILAR = 0.72       # respell a misheard word when it is this close to ARD's (lowercase similarity) …
SOUND = 0.75         # … and sounds alike (Kölner Phonetik codes this similar)
NAME_COUNT = 2       # a capitalised word the dictionary doesn't know, this often in the clip's ARD cues, is a name …
NAME_OFTEN = 8       # … and so is one this often (Otto, Falke are also dictionary words). German capitalises every noun.
MAX_CHARS = 84       # #34: a line may run over 14 words / 6 s rather than break inside a phrase — up to 2 rows of 42
PAUSE_BREAK = 0.25   # a pause this long between words is a natural place for a break
BUILD = 5            # bump when the line builder changes: every track is rebuilt on the next import

# What Whisper writes into silence or music (it learnt it from subtitled videos)
HALLUCINATION = re.compile(
    r"^(?:vielen dank\W*|untertitel.*|copyright.*|.*danke fürs zuschauen.*|.*dank fürs zuschauen.*"
    r"|.*bis zum nächsten mal.*)$", re.I)
GLOSSARY = re.compile(r"^Glossar\W*$", re.I)
END = re.compile(r"[.?!…][\"“”'»«)]*$")
NO_END = re.compile(r"^(?:\d+\.|[A-ZÄÖÜ]\.|Dr\.|Prof\.|Nr\.|St\.|Hr\.|Fr\.|bzw\.|ca\.|vgl\.|evtl\.|ggf\.|z\.B\.|u\.a\.)$")


def transcripts_dir() -> Path:
    return config.DATA_DIR / "transcripts"


def path_for(media_file: str) -> Path:
    return transcripts_dir() / f"{Path(media_file).stem}.whisper.json"


def _speech(cues: list[dict]) -> list[dict]:
    return [c for c in cues if not is_non_speech(c.get("text", ""))]


def keep_segment(seg: dict, speech: list[dict]) -> bool:
    """Drop hallucinations: no ARD speech cue around it and (unsure words or a known phrase)."""
    over = any(c["start"] - OVERLAP < seg["end"] and c["end"] + OVERLAP > seg["start"] for c in speech)
    if over:
        return True
    words = seg.get("words") or []
    p = mean(w.get("p", 0) for w in words) if words else 0.0
    return not (p < MIN_P or HALLUCINATION.match(seg.get("text", "").strip()))


def lowercase_segment(seg: dict) -> bool:
    """#34: Whisper sometimes writes a fast stretch all lowercase and without punctuation — German has no such
    text. (A short clause like "und die dann gegangen sind," is lowercase too, but punctuated: left alone.)"""
    text = seg.get("text") or " ".join(w.get("w") or "" for w in seg.get("words") or [])
    return len(TOKEN.findall(text)) >= 3 and not any(ch.isupper() or ch in ".,?!;:" for ch in text)


def words_of(transcript: dict, ard: list[dict]) -> list[dict]:
    """Whisper's words by time: {w, s, e, seg (segment number), lc (from an all-lowercase segment)}."""
    speech = _speech(ard)
    out = []
    for n, seg in enumerate(transcript.get("segments", [])):
        if not keep_segment(seg, speech):
            continue
        lc = lowercase_segment(seg)
        for w in seg.get("words") or []:
            text = (w.get("w") or "").strip()
            if GLOSSARY.match(text):
                continue  # the Mac's prompt ("Glossar: …") leaking into the text
            if text and w.get("e") is not None and w.get("s") is not None:
                out.append({"w": text, "s": float(w["s"]), "e": max(float(w["e"]), float(w["s"])), "seg": n, "lc": lc})
    out.sort(key=lambda w: w["s"])
    return out


# ── Respelling from ARD ──
# v2 transcripts (whole file, no prompt) catch more speech but misspell names and rare words
# (Tace → "Tatsche", Otto → "Autos", durchwühlt → "durchwählt"). ARD's subtitles spell them right.
TOKEN = re.compile(r"[\wÄÖÜäöüß'’-]*\w[\wÄÖÜäöüß'’-]*")
CORE = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)


def norm(word: str) -> str:
    return "".join(TOKEN.findall(word.lower()))


def _ard_tokens(text: str) -> list[tuple[str, bool]]:
    """ARD words (spelling as written) with "sentence-initial" flags; speaker labels "(Eve)" left out."""
    out, initial = [], True
    for raw in re.sub(r"\([^)]*\)", " ", text).split():
        core = "".join(TOKEN.findall(raw))
        if core:
            out.append((core, initial))
            initial = False
        if re.search(r"[.?!:]$", raw):
            initial = True
    return out


def koelner(word: str) -> str:
    """Kölner Phonetik: German words that sound alike get the same digits (Tace/Tatsche → 28)."""
    w = re.sub(r"[^a-z]", "", word.lower().translate(str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "s"})))
    out = []
    for i, ch in enumerate(w):
        prev, nxt = (w[i - 1] if i else ""), (w[i + 1] if i + 1 < len(w) else "")
        if ch in "aeijouy":
            c = "0"
        elif ch == "h":
            c = ""
        elif ch == "b":
            c = "1"
        elif ch == "p":
            c = "3" if nxt == "h" else "1"
        elif ch in "dt":
            c = "8" if nxt and nxt in "csz" else "2"
        elif ch in "fvw":
            c = "3"
        elif ch in "gkq":
            c = "4"
        elif ch == "c":
            if i == 0:
                c = "4" if nxt and nxt in "ahkloqrux" else "8"
            else:
                c = "4" if nxt and nxt in "ahkoqux" and prev not in ("s", "z") else "8"
        elif ch == "x":
            c = "8" if prev and prev in "ckq" else "48"
        elif ch == "l":
            c = "5"
        elif ch in "mn":
            c = "6"
        elif ch == "r":
            c = "7"
        elif ch in "sz":
            c = "8"
        else:
            c = ""
        out.append(c)
    runs = [d for i, d in enumerate("".join(out)) if i == 0 or d != "".join(out)[i - 1]]
    code = "".join(runs)
    return code[:1] + code[1:].replace("0", "")


def sounds_alike(w: str, a: str) -> bool:
    """Same first sound and Kölner codes ≥ 0.75 alike: Einzeltele/Einzeltäter yes, Bester/Letzter no."""
    kw, ka = koelner(w), koelner(a)
    return bool(kw and ka) and kw[0] == ka[0] and SequenceMatcher(None, kw, ka).ratio() >= SOUND


def misheard(w: str, a: str, name: bool, noun: bool = False) -> bool:
    """Is Whisper's `w` a mishearing of ARD's `a` (both lowercase, no punctuation)? Only if they sound
    alike. A name of the clip then always takes ARD's spelling (Autos → Otto, Falk → Falke).
    Inflection and elision ("hab"/"habe", "deinem"/"dein") are what was said: ARD tidies them up."""
    if not sounds_alike(w, a):
        return False
    if name:
        return True
    if w in a or a in w or (min(len(w), len(a)) <= 4 and not noun) or (len(w) > 4 and w[:-2] == a[:-2]):
        return False  # elision, short grammar words (ihn/ihm, denn/dann), endings (diesen/diesem): as said
    return SequenceMatcher(None, w, a).ratio() >= SIMILAR


def is_name(tok: str, count: int) -> bool:
    """A name of the clip: capitalised (not all caps) and unknown to the dictionary — also without a plural
    ending (Ermittlungen → Ermittlung) — or very frequent."""
    from .analyze import known_lemma
    if not tok[:1].isupper() or tok.isupper():
        return False
    if count >= NAME_OFTEN:
        return True
    return count >= NAME_COUNT and not any(known_lemma(x) for x in (tok, tok[:-1], tok[:-2]) if len(x) > 2)


def respell(words: list[dict], ard: list[dict]) -> None:
    """Per ARD speech cue: align its words with Whisper's (midpoint in the cue ± 0.5 s) and, in a
    replace block of equal length, take ARD's spelling where Whisper misheard (see `misheard`): close
    (≥ 0.72) and sounding alike (Kölner Phonetik), or a name of the clip (`is_name`) that sounds alike. Whisper's punctuation and times stay; no word is ever
    added or removed."""
    speech = _speech(ard)
    counts = Counter(t for c in speech for t, initial in _ard_tokens(c["text"]) if not initial)
    names: dict[str, bool] = {}
    mids = [(w["s"] + w["e"]) / 2 for w in words]
    for c in speech:
        lo = bisect.bisect_left(mids, c["start"] - NEAR)
        hi = bisect.bisect_right(mids, c["end"] + NEAR)
        idx = [i for i in range(lo, hi) if norm(words[i]["w"])]
        toks = _ard_tokens(c["text"])
        if not idx or not toks:
            continue
        wn = [norm(words[i]["w"]) for i in idx]
        an = [t.lower() for t, _ in toks]
        for op, i1, i2, j1, j2 in SequenceMatcher(None, wn, an, autojunk=False).get_opcodes():
            if op == "equal":
                for k in range(i2 - i1):  # #34: a lowercase stretch takes ARD's capitals (nouns, names)
                    (tok, initial), w = toks[j1 + k], words[idx[i1 + k]]
                    if w.get("lc") and tok[:1].isupper() and not initial:
                        w["w"] = _capitalise(w["w"])
                continue
            if op != "replace" or i2 - i1 != j2 - j1:
                continue
            for k in range(i2 - i1):
                (tok, initial), w = toks[j1 + k], words[idx[i1 + k]]
                if tok not in names:
                    names[tok] = is_name(tok, counts[tok])
                name = not initial and names[tok]
                if misheard(wn[i1 + k], an[j1 + k], name, noun=tok[:1].isupper()):
                    pre, core, post = CORE.match(w["w"]).groups()
                    if core[:1].isupper() and tok[:1].islower():
                        tok = tok[:1].upper() + tok[1:]  # it starts Whisper's sentence
                    w["w"] = pre + tok + post


def _capitalise(word: str) -> str:
    pre, core, post = CORE.match(word).groups()
    return pre + core[:1].upper() + core[1:] + post


def recase(words: list[dict]) -> None:
    """#34: nouns in an all-lowercase stretch get their capital back (rechnung → Rechnung), from the
    dictionary: the capitalised word is a noun there, and the lowercase one is no word of its own — or the
    parser reads it as a noun, or it follows an article (unserer ehe → Ehe; ehe/ich/hast stay). A stretch
    after a sentence end starts with a capital. ARD's own capitals came first (`respell`)."""
    from spacy.tokens import Doc

    from .analyze import dictionary, nlp
    d = dictionary()

    def noun(w):
        return any(e["pos"] == "NOUN" for e in d["entries"].get(w, []))

    runs: dict[int, list[int]] = {}
    for i, w in enumerate(words):
        if w.get("lc"):
            runs.setdefault(w["seg"], []).append(i)
    for idx in runs.values():
        cores = [CORE.match(words[i]["w"]).group(2) for i in idx]
        keep = [k for k, c in enumerate(cores) if c]
        if not keep:
            continue
        doc = nlp()(Doc(nlp().vocab, words=[cores[k] for k in keep]))
        for n, k in enumerate(keep):
            w, core = words[idx[k]], cores[k]
            if not core.islower():
                continue
            cap = core[:1].upper() + core[1:]
            known_lower = core in d["entries"] or core in d["forms"]
            if noun(cap) and (not known_lower or doc[n].pos_ == "NOUN" or (n and doc[n - 1].pos_ == "DET")):
                w["w"] = _capitalise(w["w"])
        first = idx[0]
        if first and ends_sentence(words[first - 1]["w"]):
            words[first]["w"] = _capitalise(words[first]["w"])


def ends_sentence(word: str) -> bool:
    return bool(END.search(word)) and not NO_END.match(word)


def _dur(ws: list[dict]) -> float:
    return ws[-1]["e"] - ws[0]["s"]


def _too_long(ws: list[dict]) -> bool:
    return len(ws) > MAX_WORDS or _dur(ws) > MAX_SECONDS or len(join_words(ws)) > MAX_CHARS


# ── #34: where a line may break ──
# A line never ends on an article, a preposition or a prefix-like word (… stand ein | Karton) unless a
# conjunction follows, and never splits a noun or prepositional phrase (spaCy: an arc inside the phrase
# would cross the break). The verb ↔ prefix bracket may span two lines.
ARTICLES = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einem", "einer", "eines",
            "kein", "keine", "keinen", "keinem", "keiner", "keines", "mein", "meine", "meinen", "meinem", "meiner",
            "dein", "deine", "deinen", "deinem", "deiner", "sein", "seine", "seinen", "seinem", "seiner",
            "ihr", "ihre", "ihren", "ihrem", "ihrer", "unser", "unsere", "unseren", "unserem", "unserer",
            "euer", "eure", "euren", "eurem", "eurer", "dieser", "diese", "diesen", "diesem", "dieses",
            "jeder", "jede", "jeden", "jedem", "jedes", "welche", "welcher", "welchen", "welchem", "welches"}
PREPOSITIONS = {"an", "auf", "aus", "bei", "mit", "nach", "von", "vor", "zu", "in", "im", "am", "zum", "zur", "vom",
                "beim", "ins", "ans", "aufs", "für", "fürs", "über", "unter", "um", "durch", "gegen", "ohne", "seit",
                "bis", "hinter", "neben", "zwischen", "wegen", "trotz", "während", "statt", "außer", "gegenüber", "ab"}
PREFIXES = {"zurück", "weg", "los", "her", "hin", "fest", "weiter", "heraus", "hinaus", "herum", "vorbei", "zusammen",
            "fort", "raus", "rein", "rüber", "runter", "hoch", "dran", "drauf", "mit", "ein", "an", "auf", "aus", "vor",
            "zu", "nach", "ab", "um", "durch"}
OPENERS = ARTICLES | PREPOSITIONS | PREFIXES
CONJUNCTIONS = {"und", "aber", "oder", "dass", "weil", "wenn", "als", "denn", "sondern", "ob", "obwohl", "damit",
                "bevor", "nachdem", "sodass", "falls", "sobald", "solange"}
PHRASE_DEPS = {"nk", "ag", "pg", "pnc", "nmc", "adc", "uc", "mnr"}  # TIGER arcs inside a noun / prepositional phrase


def _core(word: str) -> str:
    return CORE.match(word).group(2)


def _bare(word: str) -> bool:
    """No punctuation after the word."""
    return not CORE.match(word).group(3)


def opener_breaks(ws: list[dict]) -> set[int]:
    """Breaks k (between ws[k-1] and ws[k]) that would end a line on an article, preposition or prefix."""
    return {k for k in range(1, len(ws))
            if _bare(ws[k - 1]["w"]) and _core(ws[k - 1]["w"]).lower() in OPENERS
            and _core(ws[k]["w"]).lower() not in CONJUNCTIONS}


def phrase_breaks(ws: list[dict]) -> set[int]:
    """Breaks k that would split a noun or prepositional phrase (by the parse of the whole line)."""
    bad = set()
    from .analyze import nlp
    text, starts, at = "", [], 0
    for w in ws:
        starts.append(at)
        text += w["w"] + " "
        at = len(text)
    doc = nlp()(text)
    word = [bisect.bisect_right(starts, t.idx) - 1 for t in doc]
    for t in doc:
        if t.dep_ in PHRASE_DEPS and t.head is not t:
            a, b = sorted((word[t.i], word[t.head.i]))
            bad.update(range(a + 1, b + 1))
    return bad


def break_rank(ws: list[dict], k: int) -> int:
    """0 sentence end · 1 comma, colon, dash · 2 before a conjunction · 3 a pause · 4 anywhere else."""
    before = ws[k - 1]["w"]
    if ends_sentence(before):
        return 0
    if before.endswith((",", ";", ":", "–", "-")):
        return 1
    if _core(ws[k]["w"]).lower() in CONJUNCTIONS:
        return 2
    if ws[k]["s"] - ws[k - 1]["e"] >= PAUSE_BREAK:
        return 3
    return 4


def _split_long(ws: list[dict]) -> list[list[dict]]:
    """A line over 14 words / 6 s / 84 characters breaks at punctuation, before a conjunction or at a pause
    — the most even such place, never inside a phrase and never leaving a piece under MIN_SECONDS. No such
    place: the line stays whole up to MAX_CHARS; beyond that it breaks between two phrases, and if the
    parse sees one long phrase, at least not after an article, preposition or prefix."""
    if not _too_long(ws) or len(ws) < 2:
        return [ws]
    ok = [k for k in range(1, len(ws)) if _dur(ws[:k]) >= MIN_SECONDS and _dur(ws[k:]) >= MIN_SECONDS]
    if not ok:
        return [ws]
    openers, phrases = opener_breaks(ws), phrase_breaks(ws)
    good = [k for k in ok if k not in openers and k not in phrases]
    n = len(ws)

    def cost(k):
        return break_rank(ws, k) + 2 * abs(2 * k - n) / n

    natural = [k for k in good if break_rank(ws, k) <= 3]
    if natural:
        k = min(natural, key=cost)
    elif len(join_words(ws)) <= MAX_CHARS:
        return [ws]
    else:
        k = min(good or [k for k in ok if k not in openers] or ok, key=cost)
    return _split_long(ws[:k]) + _split_long(ws[k:])


FORMAL = {"Sie", "Ihnen", "Ihr", "Ihre", "Ihren", "Ihrem", "Ihrer", "Ihres"}
STARTERS = {"ich", "du", "er", "es", "wir", "man"}  # pronouns that are also nouns in the dictionary (das Ich)


def new_sentence(prev: dict, w: dict) -> bool:
    """#34: a capitalised sentence start in a new Whisper segment after a line that didn't end one —
    a new speaker ("… für das Auto von meinem Konto für" | "Ich nehme zwei Brötchen."). A sentence start
    is a pronoun or a word that is no noun (not Sie); after an article, preposition or prefix only a pronoun
    ("Lust zum | Tanzen" stays). After an all-lowercase stretch (no capitals of its own) any capital."""
    if w.get("seg") == prev.get("seg") or ends_sentence(prev["w"]):
        return False
    core = _core(w["w"])
    if not core[:1].isupper() or core.isupper() or core in FORMAL:
        return False
    from .analyze import dictionary
    d = dictionary()
    low = core.lower()
    if _bare(prev["w"]) and _core(prev["w"]).lower() in OPENERS:
        return low in STARTERS
    starter = low in STARTERS or ((low in d["entries"] or low in d["forms"])
                                  and not any(e["pos"] == "NOUN" for e in d["entries"].get(core, [])))
    return starter or (bool(prev.get("lc")) and not w.get("lc"))


def build_lines(words: list[dict]) -> list[list[dict]]:
    """Words → lines: after . ? !, at a pause ≥ 0.7 s, at a new speaker's sentence; long lines split
    (`_split_long`); short fragments joined — but never onto another speaker's sentence."""
    lines, hard = [], []  # hard: the line starts another speaker's sentence
    cur, cur_hard = [], False
    for w in words:
        if cur:
            starts = new_sentence(cur[-1], w)
            if starts or w["s"] - cur[-1]["e"] >= PAUSE:
                lines.append(cur)
                hard.append(cur_hard)
                cur, cur_hard = [], starts
        cur.append(w)
        if ends_sentence(w["w"]):
            lines.append(cur)
            hard.append(cur_hard)
            cur, cur_hard = [], False
    if cur:
        lines.append(cur)
        hard.append(cur_hard)
    pieces, flags = [], []
    for ln, h in zip(lines, hard):
        for n, piece in enumerate(_split_long(ln)):
            pieces.append(piece)
            flags.append(h and n == 0)
    lines, hard = pieces, flags

    def whole(i):  # a sentence on its own: it ends one, and the line before ended one too
        return ends_sentence(lines[i][-1]["w"]) and (i == 0 or ends_sentence(lines[i - 1][-1]["w"]))

    def gap(a, b):
        return lines[b][0]["s"] - lines[a][-1]["e"] if 0 <= a and b < len(lines) else float("inf")

    def joinable(side, i):
        if side == "prev":
            return not hard[i] and gap(i - 1, i) <= JOIN_GAP
        return i + 1 < len(lines) and not hard[i + 1] and gap(i, i + 1) <= JOIN_GAP

    i = 0
    while i < len(lines):
        if _dur(lines[i]) < MIN_SECONDS and not whole(i):
            # the end of a sentence goes with the line before, a beginning with the line after
            sides = ["prev", "next"] if ends_sentence(lines[i][-1]["w"]) else ["next", "prev"]
            side = next((s for s in sides if joinable(s, i)), None)
            if side == "prev":
                lines[i - 1] += lines.pop(i)
                hard.pop(i)
                i -= 1
                continue
            if side == "next":
                frag = lines.pop(i)
                hard[i] = hard.pop(i)
                lines[i] = frag + lines[i]
                continue
        i += 1
    return lines


ATTACHED = re.compile(r"^[-.,]\w")  # Whisper's ",50" after "2", ".500" after "3", "-Quiz" after "ARD"


def join_words(ws: list[dict]) -> str:
    out = ""
    for w in ws:
        sep = "" if not out or (ATTACHED.match(w["w"]) and out[-1].isalnum()) else " "
        out += sep + w["w"]
    return out


def spoken_cues(transcript: dict, ard: list[dict]) -> list[dict]:
    """The "gesprochen" track: spoken lines (respelled from ARD), ARD's line where Whisper heard nothing,
    and ARD's sound cues (♪ …, * Glockenläuten *), by time."""
    words = words_of(transcript, ard)
    respell(words, ard)
    recase(words)
    out = [{"start": round(ln[0]["s"], 2), "end": round(ln[-1]["e"], 2), "text": join_words(ln)}
           for ln in build_lines(words)]
    # gap fill: an ARD speech cue with no Whisper word in it (± 0.5 s) goes in as it is, marked
    mids = [(w["s"] + w["e"]) / 2 for w in words]
    out += [{"start": c["start"], "end": c["end"], "text": c["text"], "src": "ard"} for c in _speech(ard)
            if bisect.bisect_right(mids, c["end"] + NEAR) == bisect.bisect_left(mids, c["start"] - NEAR)]
    out.sort(key=lambda c: (c["start"], c["end"]))
    # never overlapping (Whisper's words can, across segments): a line ends where the next begins,
    # so Schauen never switches the text before the pause (#18)
    for a, b in zip(out, out[1:]):
        if a["end"] > b["start"]:
            a["end"] = max(b["start"], round(a["start"] + 0.05, 2))
            b["start"] = max(b["start"], a["end"])
    out += [{"start": c["start"], "end": c["end"], "text": c["text"]} for c in ard
            if c.get("text", "").strip() and is_non_speech(c["text"])]
    out.sort(key=lambda c: (c["start"], c["end"]))
    return out


def stamp(p: Path) -> str:
    """What the stored track was built from: file mtime + size, and the builder version."""
    st = p.stat()
    return f"{st.st_mtime_ns}:{st.st_size}:{BUILD}"


STARTED = 2.0  # s: a saved position past this = he has started the clip (Schauen says "Weiterschauen")


def clip_end(media_id: int) -> float | None:
    """Where the clip ends for him: the plan's last "to" (before the credits), else its length or last cue."""
    from . import plan, rolling, stock
    with db.tx() as conn:
        r = conn.execute("SELECT key, duration, cues FROM media WHERE id = ?", (media_id,)).fetchone()
    if not r:
        return None
    cues = json.loads(r["cues"] or "[]")
    length = r["duration"] or (cues[-1]["end"] if cues else None) or (stock.item(r["key"]) or {}).get("duration")
    if not r["key"]:
        return length
    data = plan.plan(db.get_setting("phase"))
    planned = [s for b in plan.block_ids() for s in rolling.slots(date(2026, 1, 5), data, b)
               if rolling.rolls(s["m"]) and s["m"]["clip"] == r["key"]]
    return rolling.clip_end(planned, length) if planned else length


def in_progress(media_id: int) -> bool:
    """#35: started but not finished — then its lines stay exactly as they are until he is through.
    Finished = his position within 10 s of the end (#21's rule), the end being the plan's last "to"."""
    with db.tx() as conn:
        r = conn.execute("SELECT position FROM media_progress WHERE media_id = ?", (media_id,)).fetchone()
    if not r or r["position"] <= STARTED:
        return False
    end = clip_end(media_id)
    if end is None:
        return True  # length unknown: rather keep it
    from .rolling import DONE_SLACK
    return r["position"] < end - min(DONE_SLACK, end / 10)


def import_all(media_id: int | None = None, force: bool = False) -> dict:
    """(Re)build media.spoken_cues where a transcript file is new or changed (mtime/size) or the builder
    is newer; a clip whose file is gone loses its track. A file still being copied (bad JSON) keeps the
    last good track and is tried again next time.

    #35: a clip he has started and not finished keeps its track as it is (`kept`) — also with `force`,
    unless the operator names it (`media_id` and `force`). Once he is through, the next import rebuilds it."""
    changed, have, errors, kept = [], [], [], []
    with db.tx() as conn:
        q = "SELECT id, media_file, cues, spoken_cues, spoken_stamp FROM media WHERE media_file IS NOT NULL"
        rows = conn.execute(q + (" AND id = ?" if media_id is not None else ""),
                            (media_id,) if media_id is not None else ()).fetchall()
    named = force and media_id is not None
    for r in rows:
        p = path_for(r["media_file"])
        new = mark = None
        if p.exists():
            have.append(r["id"])
            mark = stamp(p)
            if mark == r["spoken_stamp"] and not force:
                continue
        elif r["spoken_stamp"] is None:
            continue  # no file and no track: nothing to do
        if not named and in_progress(r["id"]):
            kept.append(r["id"])
            continue
        if p.exists():
            try:
                new = json.dumps(spoken_cues(json.loads(p.read_text(encoding="utf-8")), json.loads(r["cues"])),
                                 ensure_ascii=False)
            except (ValueError, KeyError, TypeError) as e:
                errors.append({"mediaId": r["id"], "file": p.name, "error": str(e)})
                continue
        if new != r["spoken_cues"] or mark != r["spoken_stamp"]:
            with db.tx() as conn:
                conn.execute("UPDATE media SET spoken_cues = ?, spoken_stamp = ? WHERE id = ?", (new, mark, r["id"]))
            if new != r["spoken_cues"]:
                changed.append(r["id"])
    return {"withTranscript": have, "changed": changed, "errors": errors, "kept": kept}


def missing(today: date, start: date, data: dict, days: int = 14) -> list[dict]:
    """Planned clips (with picture and subtitles) of the next `days` days without a spoken track — for
    the operator (PROGRESS.md), never a to-do for Matt. cheqs-mac-mini transcribes them nightly at 01:30
    (Whisper large-v3, "version": 2) through ~/bin/transcribe-gate (todo · audio <id> · put <stem>), which
    writes transcripts/<stem>.whisper.json; the next import or opening the clip picks it up."""
    from . import materials, plan
    ctx = materials.Ctx(today)
    out, seen = [], set()
    for i in range(days):
        day = today + timedelta(days=i)
        for it in materials.flat(materials.day_items(plan.plan_day(start, day, data, ctx.pauses), ctx, data, start)):
            mid = it.get("mediaId")
            if it["kind"] in ("clip", "satzcheck") and mid and not it.get("audio") and mid not in seen:
                seen.add(mid)
                if load(mid) is None:
                    with db.tx() as conn:
                        f = conn.execute("SELECT media_file FROM media WHERE id = ?", (mid,)).fetchone()["media_file"]
                    out.append({"date": day.isoformat(), "mediaId": mid, "title": it["title"],
                                "hint": f"Transkript fehlt — der Mac mini holt es um 01:30 (transcripts/{Path(f).stem}.whisper.json)"})
    return out


def load(media_id: int) -> list[dict] | None:
    with db.tx() as conn:
        r = conn.execute("SELECT spoken_cues FROM media WHERE id = ?", (media_id,)).fetchone()
    return json.loads(r["spoken_cues"]) if r and r["spoken_cues"] else None


if __name__ == "__main__":
    # --force rebuilds every track (not the ones he is in the middle of); --force <id> also that one (#35)
    db.init()
    ids = [int(a) for a in sys.argv[1:] if a.isdigit()]
    force = "--force" in sys.argv
    out = [import_all(i, force=force) for i in ids] if ids else [import_all(force=force)]
    print(json.dumps(out[0] if len(out) == 1 else out, indent=2))
