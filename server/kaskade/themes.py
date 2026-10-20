"""#33: no crime story where child sexual abuse is the case or a main thread.

Before a crime item goes into the plan, its synopsis is read by hand. Once its subtitles or transcript
are in, they are searched for ABUSE, and the result goes into stock.json as "themeCheck"
("2026-10-16: Synopsis + UT geprüft, kein Kindesmissbrauch"). The daily Materialcheck repeats the search
on every library clip, so a crime clip imported later (its themeCheck says "UT folgt") is flagged for a look.
"""
import json
import logging
import re

from . import db, stock

log = logging.getLogger(__name__)

ABUSE = re.compile(r"Missbrauch|missbraucht|pädophil|Pädo|kinderporno|Kinderschänder|minderjährig", re.I)
MAX_HITS = 2       # one or two passing mentions are fine; more and the case is probably about it
CLEAN = "kein Kindesmissbrauch"
PENDING = "UT folgt"


def hits(cues: list[dict]) -> list[dict]:
    return [{"at": round(c["start"], 1), "text": c["text"]} for c in cues if ABUSE.search(c.get("text") or "")]


def scan() -> list[dict]:
    """Library clips worth a look: any with a hit, and crime clips whose subtitles arrived after their
    themeCheck (or that have none). `review` says why one needs a decision before it is planned."""
    items = {i["key"]: i for i in stock.catalog().get("items", [])}
    with db.tx() as conn:
        rows = conn.execute("SELECT id, key, tag, title, cues, spoken_cues FROM media ORDER BY id").fetchall()
    out = []
    for r in rows:
        found = {name: hits(json.loads(r[name] or "[]")) for name in ("cues", "spoken_cues")}
        n = max(len(v) for v in found.values())
        has_text = bool(json.loads(r["cues"] or "[]") or json.loads(r["spoken_cues"] or "[]"))
        it = items.get(r["key"]) or {}
        check = it.get("themeCheck")
        review = None
        if n > MAX_HITS and (check is None or CLEAN in check):
            review = f"{n} Treffer zu Kindesmissbrauch — Synopsis lesen, bevor es geplant wird"
        elif has_text and (it.get("tag") or r["tag"]) == "krimi" and (check is None or PENDING in check):
            review = f"UT sind da ({n} Treffer) — themeCheck in stock.json nachtragen"
        if n or review:
            out.append({"mediaId": r["id"], "key": r["key"], "title": r["title"], "hits": n,
                        "at": [h["at"] for h in max(found.values(), key=len)][:12], "themeCheck": check, "review": review})
            if review:
                log.warning("themeCheck media %s (%s): %s", r["id"], r["key"], review)
    return out
