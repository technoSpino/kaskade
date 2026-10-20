"""Rolling watch targets (#21): each day's part of a clip starts where Matt really is.

The plan says which clip each input/lesen block uses and in which order; its time ranges are
only the first draft. A day's range runs from his saved position over about one day's film
budget — ≈ 25 min of film in the 65-min input block (with pausing), ≈ 28 min of audio in the
35-min lesen block; once a few days are measured, his own pace — and ends in a pause between two
lines. The rest of a clip is split evenly over the days it needs. A clip that needs more days
than planned pushes the next ones back, one finished early lets them move up: nothing is
skipped. Today's range is fixed the first time it's computed (the 06:30 Materialcheck, or the
first visit to Heute), so it doesn't slide while he watches.

Audio he hears on the phone leaves no player position (#31): an audio range he rated or whose
block he ticked off counts as heard up to its end; a saved position further on still wins.
"""
import json
import re
import statistics
from datetime import date

from . import db, plan, stock

ROLLING_KINDS = {"mediathek", "podcast", "audio"}
AUDIO_KINDS = {"podcast", "audio"}  # #31: also heard outside Kaskade (on the phone): no player position
FILM = {"input": 25 * 60, "lesen": 28 * 60}                       # default seconds of film per block
FILM_RANGE = {"input": (15 * 60, 40 * 60), "lesen": (20 * 60, 35 * 60)}
MIN_SAMPLES = 3                                                    # measured days before his pace counts
MIN_SAMPLE_SECONDS = 15 * 60                                       # … each with ≥ 15 min in the block
DONE_SLACK = 10                                                    # within 10 s of the end = finished
RANGE_IN_TEXT = re.compile(r"\d+:\d{2}–\d+:\d{2}")


def seconds(value) -> float | None:
    """"30:14" → 1814, "1:00:40" → 3640, 95 → 95, None → None."""
    if value is None or isinstance(value, (int, float)):
        return value
    total = 0
    for p in str(value).split(":"):
        total = total * 60 + int(p)
    return total


def clock(sec: float) -> str:
    """Range times as minutes:seconds, also past an hour ("89:21"), like the plan texts."""
    s = int(round(sec or 0))
    return f"{s // 60}:{s % 60:02d}"


def rolls(m: dict | None) -> bool:
    """A plan material whose range rolls: a library clip, podcast episode or radio play."""
    return bool(m) and m["kind"] == "clip" and (stock.item(m["clip"]) or {}).get("kind") in ROLLING_KINDS


def slots(start: date, data: dict, block: str, pauses=()) -> list[dict]:
    """Every plan day's material for `block`, in date order: {date, m, text}. A block with two
    items (#27: audio and a text) rolls its audio item; each item has its own text ("desc").
    Weeks off (#36) have no slot: the clip goes on where he stopped on the next plan day."""
    out = []
    for wi, w in enumerate(data["weeks"]):
        for di, d in enumerate(w["days"]):
            mats = [x for x in d.get("materials", []) if x["block"] == block]
            m = next((x for x in mats if rolls(x)), mats[0] if mats else None)
            out.append({"date": plan.slot_date(start, wi, di, pauses), "m": m, "text": (m or {}).get("desc") or d.get(block, "")})
    return out


def clip_end(planned: list[dict], duration: float | None) -> float | None:
    """Where a clip ends for the plan: its last planned "to" (e.g. before the credits), else its length."""
    ends = [seconds(s["m"].get("to")) for s in planned]
    return max(ends) if ends and all(ends) else duration


def cut_near(cues: list[dict], target: float, window: float = 60.0) -> float:
    """A cut point in a pause between two lines near `target` — the longest pause, close by."""
    best, score = None, None
    for a, b in zip(cues, cues[1:]):
        if b["start"] <= a["end"]:
            continue
        cut = max(a["end"], b["start"] - 2.0)  # the line before is heard out, 2 s before the next
        if abs(cut - target) > window:
            continue
        s = (b["start"] - a["end"]) - abs(cut - target) / 20
        if score is None or s > score:
            best, score = cut, s
    return best if best is not None else target


def day_range(pos: float, end: float | None, film: float, cues: list[dict]) -> tuple[int, int | None, bool]:
    """(from, to, final) for one day of a clip: the rest split evenly over the days it needs."""
    frm = 0 if pos < 5 else int(pos)
    if end is None:
        return frm, None, True
    rest = end - frm
    n = max(1, round(rest / film))
    if rest / n > 1.3 * film:
        n += 1
    if n == 1:
        return frm, int(round(end)), True
    return frm, int(round(cut_near(cues, frm + rest / n))), False


def text_for(planned: list[dict], frm: float, to: float | None, final: bool) -> str:
    """The plan text of the planned day that overlaps the real range most, with the real range in it."""
    def overlap(s):
        a, b = seconds(s["m"].get("from")) or 0, seconds(s["m"].get("to")) or float("inf")
        return min(b, to if to is not None else float("inf")) - max(a, frm)

    text = max(planned, key=overlap)["text"]
    if to is not None:
        text = RANGE_IN_TEXT.sub(f"{clock(frm)}–{clock(to)}", text, count=1)
    return text if final else text.replace(" (Ende)", "")


def schedule(block_slots: list[dict], clips: dict[str, dict], pos: dict[str, float], film: float, today: date,
             frozen: dict | None = None, today_done: bool = False) -> dict[date, dict]:
    """date → {clip, from, to, final, text} for every rolling slot from `today` on.

    clips: key → {"end", "cues", "planned"}; pos: key → saved position. Each day is assumed to
    reach its target (except today once the block is ticked off) — tomorrow's real start is
    computed tomorrow from where he really is. A slot with its own "minutes" (the lesen block's
    audio, #27) gets that much audio instead of `film`.
    """
    rolling = [s for s in block_slots if rolls(s["m"])]
    order = list(dict.fromkeys(s["m"]["clip"] for s in rolling))
    pos = dict(pos)

    def finished(c):  # never started = not finished, however short
        end, p = clips[c]["end"], pos.get(c, 0)
        return p == float("inf") or (end is not None and p > 0 and p >= end - min(DONE_SLACK, end / 10))

    out = {}
    for s in rolling:
        if s["date"] < today:
            continue
        if s["date"] == today and (frozen or today_done):
            # today's range as fixed this morning — or, ticked off before it was fixed, as planned
            m = s["m"]
            c, frm, to = (frozen["clip"], frozen["from"], frozen["to"]) if frozen else \
                (m["clip"], seconds(m.get("from")) or 0, seconds(m.get("to")) or clips[m["clip"]]["end"])
            end = clips.get(c, {}).get("end")
            final = to is None or end is None or to >= end - DONE_SLACK
        else:
            c = next((k for k in order if not finished(k)), None)
            if c is None:
                break  # everything watched: the rest of the plan stays as written
            budget = s["m"]["minutes"] * 60 if s["m"].get("minutes") else film
            frm, to, final = day_range(pos.get(c, 0), clips[c]["end"], budget, clips[c]["cues"])
        planned = clips.get(c, {}).get("planned") or [s]
        out[s["date"]] = {"clip": c, "from": frm, "to": to, "final": final, "text": text_for(planned, frm, to, final)}
        if not (s["date"] == today and today_done):
            pos[c] = float("inf") if to is None else max(pos.get(c, 0), to)
    return out


# ── Stored state: today's fixed range, and how far he got (his pace) ──────────

def frozen(day: date, block: str) -> dict | None:
    with db.tx() as conn:
        r = conn.execute("SELECT clip, start, end FROM watch_ranges WHERE local_date = ? AND block = ?",
                         (day.isoformat(), block)).fetchone()
    return {"clip": r["clip"], "from": r["start"], "to": r["end"]} if r else None


def freeze(day: date, block: str, rng: dict, pos: dict[str, float]) -> None:
    """Fix today's range; note how far the earlier days of this block got (for his pace)."""
    with db.tx() as conn:
        secs = conn.execute("SELECT COALESCE(SUM(seconds), 0) FROM activity WHERE local_date = ? AND block = ?",
                            (day.isoformat(), block)).fetchone()[0]
        conn.execute("INSERT OR IGNORE INTO watch_ranges(local_date, block, clip, start, end, clean) VALUES (?, ?, ?, ?, ?, ?)",
                     (day.isoformat(), block, rng["clip"], rng["from"], rng["to"], 1 if secs == 0 else 0))
        for r in conn.execute("SELECT local_date, clip FROM watch_ranges WHERE block = ? AND local_date < ? AND reached IS NULL",
                              (block, day.isoformat())).fetchall():
            conn.execute("UPDATE watch_ranges SET reached = ? WHERE local_date = ? AND block = ?",
                         (pos.get(r["clip"], 0), r["local_date"], block))


def pace_samples(block: str) -> list[float]:
    """Seconds of film per second in the block, for each measured day (oldest first)."""
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT w.start, w.reached, (SELECT COALESCE(SUM(a.seconds), 0) FROM activity a"
            " WHERE a.local_date = w.local_date AND a.block = w.block) AS secs"
            " FROM watch_ranges w WHERE w.block = ? AND w.clean = 1 AND w.reached IS NOT NULL ORDER BY w.local_date",
            (block,)).fetchall()
    return [(r["reached"] - r["start"]) / r["secs"] for r in rows
            if r["secs"] >= MIN_SAMPLE_SECONDS and r["reached"] >= r["start"]]


def film_budget(block: str, minutes: int) -> float:
    """Film seconds for one block: the default until a few days are measured, then his own pace."""
    samples = pace_samples(block)
    if len(samples) < MIN_SAMPLES:
        return FILM.get(block, minutes * 60 * 0.4)
    lo, hi = FILM_RANGE.get(block, (10 * 60, minutes * 60))
    return min(hi, max(lo, statistics.median(samples[-5:]) * minutes * 60))


def heard(block: str, upto: date) -> dict[str, float]:
    """#31: audio key → the furthest end of a range of this block he rated (any %, #23) or whose block he
    ticked off, up to `upto`. Audio heard on the phone leaves no player position, but it was heard."""
    with db.tx() as conn:
        done = {r[0] for r in conn.execute("SELECT local_date FROM plan_done WHERE block = ? AND local_date <= ?",
                                           (block, upto.isoformat()))}
        ranges = conn.execute("SELECT local_date, clip, end FROM watch_ranges WHERE block = ? AND local_date <= ?",
                              (block, upto.isoformat())).fetchall()
        rated = conn.execute("SELECT local_date, item, pct, detail FROM ratings WHERE block = ? AND local_date <= ?"
                             " AND item LIKE 'clip:%'", (block, upto.isoformat())).fetchall()
    out: dict[str, float] = {}
    for r in ranges:
        if r["local_date"] in done and r["end"]:
            out[r["clip"]] = max(out.get(r["clip"], 0), r["end"])
    for r in rated:  # also a day whose range wasn't fixed (before #21 reached the block)
        _, key, rng = r["item"].split(":", 2)
        to = (json.loads(r["detail"]) if r["detail"] else {}).get("to") or float(rng.split("-")[-1] or 0)
        if to and (r["pct"] is not None or r["local_date"] in done):
            out[key] = max(out.get(key, 0), to)
    return {k: v for k, v in out.items() if (stock.item(k) or {}).get("kind") in AUDIO_KINDS}


def load_cues(media_id: int) -> list[dict]:
    with db.tx() as conn:
        r = conn.execute("SELECT cues FROM media WHERE id = ?", (media_id,)).fetchone()
    return json.loads(r["cues"] or "[]") if r else []


def plan_block(block: str, data: dict, start: date, ctx) -> dict[date, dict]:
    """The rolling ranges of one block from ctx.today on, fixing today's on its first computation."""
    block_slots = slots(start, data, block, getattr(ctx, "pauses", ()))
    planned: dict[str, list[dict]] = {}
    for s in block_slots:
        if rolls(s["m"]):
            planned.setdefault(s["m"]["clip"], []).append(s)
    # Roll from the real today even when a later day is previewed (the days between count too)
    day = min(ctx.today, ctx.real_today)
    on_phone = heard(block, day)
    clips, pos = {}, {}
    for key, ps in planned.items():
        row = ctx.lib.get(key)
        cues = load_cues(row["id"]) if row else []
        duration = (row and row["duration"]) or (cues[-1]["end"] if cues else None) or (stock.item(key) or {}).get("duration")
        clips[key] = {"end": clip_end(ps, duration), "cues": cues, "planned": ps}
        # his player position — or, for audio, how far a range he rated or ticked off went (#31), whichever is further
        pos[key] = max((ctx.positions.get(row["id"]) or 0) if row else 0, on_phone.get(key, 0))
    minutes = next((b["minutes"] for b in data["block"] if b["id"] == block), 60)
    fixed = frozen(day, block)
    with db.tx() as conn:
        done = conn.execute("SELECT 1 FROM plan_done WHERE local_date = ? AND block = ?", (day.isoformat(), block)).fetchone()
    out = schedule(block_slots, clips, pos, film_budget(block, minutes), day, fixed, bool(done))
    if ctx.live and day == ctx.real_today and not fixed and not done and day in out:  # the real today only
        freeze(day, block, out[day], pos)
    return out
