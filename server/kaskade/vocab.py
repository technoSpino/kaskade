"""Wortschatz-Test: sampling and scoring (yes/no test with false-alarm correction)."""
import json
import random
from functools import lru_cache

from . import config

CORE_SIZE = 2000


@lru_cache(maxsize=1)
def pools() -> dict:
    return json.loads((config.CONTENT_DIR / "vocab-test/pools.json").read_text(encoding="utf-8"))


def build_test(seed: int | None = None) -> list[dict]:
    """Return shuffled items: `per_band` real words per band plus all pseudowords."""
    rng = random.Random(seed)
    data = pools()
    items = []
    for band in data["bands"]:
        for w in rng.sample(band["words"], min(data["perBand"], len(band["words"]))):
            items.append({"word": w, "band": band["id"]})
    items += [{"word": w, "band": "pseudo"} for w in data["pseudowords"]]
    rng.shuffle(items)
    return items


def corrected(hit_rate: float, fa_rate: float) -> float:
    """Correction for guessing: (H − FA) / (1 − FA), clamped to [0, 1]."""
    if fa_rate >= 1:
        return 0.0
    return max(0.0, min(1.0, (hit_rate - fa_rate) / (1 - fa_rate)))


def score(answers: list[dict], bands: list[dict] | None = None) -> dict:
    """answers: [{word, band, yes}] → per-band and total estimates.

    Each band's corrected hit rate × the band's real-lemma size gives the known
    words in that band; the sum is the vocabulary estimate (up to rank 8,000).
    """
    bands = bands if bands is not None else pools()["bands"]
    pseudo = [a for a in answers if a["band"] == "pseudo"]
    fa_rate = sum(bool(a["yes"]) for a in pseudo) / len(pseudo) if pseudo else 0.0

    out_bands, total, core_known, core_size = [], 0.0, 0.0, 0
    for band in bands:
        real = [a for a in answers if a["band"] == band["id"]]
        hit = sum(bool(a["yes"]) for a in real) / len(real) if real else 0.0
        c = corrected(hit, fa_rate)
        known = c * band["size"]
        total += known
        # Share of the band that lies inside the top 2,000 ranks.
        width = band["to"] - band["from"] + 1
        inside = max(0, min(band["to"], CORE_SIZE) - band["from"] + 1) / width
        core_known += known * inside
        core_size += band["size"] * inside
        out_bands.append({
            "id": band["id"], "from": band["from"], "to": band["to"],
            "n": len(real), "hits": round(hit, 3), "corrected": round(c, 3),
            "known": round(known),
        })

    core_share = core_known / core_size if core_size else 0.0
    return {
        "bands": out_bands,
        "falseAlarmRate": round(fa_rate, 3),
        "reliable": fa_rate <= 0.2,
        "estimate": round(total / 50) * 50,
        "coreShare": round(core_share, 3),
        # Known words of the 2,000-card core deck (= the top 2,000 real lemmas).
        "coreKnown": round(core_share * CORE_SIZE / 10) * 10,
    }
