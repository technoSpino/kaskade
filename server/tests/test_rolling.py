"""#21: clip ranges roll from Matt's real position; later days and clips shift; nothing is skipped."""
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from kaskade import db, plan, rolling

MON = date(2026, 10, 12)
TATORT_END = 5361  # 89:21, the plan's last Tatort cut (before the credits)


def plan_slots():
    return rolling.slots(MON, plan.plan("2B"), "input")


def clips_for(block_slots, cues=None, durations=None):
    out = {}
    for s in block_slots:
        if rolling.rolls(s["m"]):
            out.setdefault(s["m"]["clip"], {"planned": [], "cues": cues or [], "end": None})["planned"].append(s)
    for key, c in out.items():
        c["end"] = rolling.clip_end(c["planned"], (durations or {}).get(key, 2400))
    return out


def test_day_range_splits_the_rest_evenly():
    assert rolling.day_range(430, TATORT_END, 1500, []) == (430, 430 + round((TATORT_END - 430) / 3), False)
    assert rolling.day_range(0, 1800, 1500, []) == (0, 1800, True)          # 1.2 days' worth → one day
    assert rolling.day_range(0, 2220, 1500, []) == (0, 1110, False)          # 1.48 → two even days, not 25 + 12
    assert rolling.day_range(3, 900, 1500, []) == (0, 900, True)             # a few seconds in = from the start
    assert rolling.day_range(100, None, 1500, []) == (100, None, True)       # unknown length: the rest


def test_cuts_land_in_a_pause_between_lines():
    cues = [{"start": t, "end": t + 3.9, "text": "…"} for t in range(0, 3000, 4)]   # 0.1 s gaps
    cues.append({"start": 3000, "end": 3002, "text": "…"})
    cues = sorted(cues, key=lambda c: c["start"])
    cues.insert(0, {"start": -10, "end": -9, "text": ""})
    # a real pause: nothing from 1495.9 to 1504
    cues = [c for c in cues if not 1496 <= c["start"] < 1504]
    assert rolling.cut_near(cues, 1500) == 1502.0          # in the pause, 2 s before the next line
    assert rolling.cut_near([], 1500) == 1500


def test_tatort_rolls_from_7_10_and_soko_moves_back():
    s = plan_slots()
    clips = clips_for(s)
    out = rolling.schedule(s, clips, {"tatort-schweigen": 430}, 1500, MON + timedelta(days=1))
    tue, wed, thu, fri = (out[MON + timedelta(days=d)] for d in (1, 2, 3, 4))
    assert tue["clip"] == "tatort-schweigen" and tue["from"] == 430 and not tue["final"]
    assert wed["from"] == tue["to"] and thu["from"] == wed["to"] and thu["to"] == TATORT_END and thu["final"]
    assert fri["clip"] == "soko-leipzig-das-auge" and fri["from"] == 0   # SOKO a day later, from its start
    assert out[MON + timedelta(days=7)]["clip"] == "soko-leipzig-das-auge"  # … its second half on Monday
    assert out[MON + timedelta(days=8)]["clip"] == "merz-gegen-merz-1"     # and everything after one slot later
    # the day text names the computed range; "(Ende)" only on the clip's last day
    assert f"7:10–{rolling.clock(tue['to'])}" in tue["text"] and "0:00–30:14" not in tue["text"]
    assert wed["text"].startswith("Tatort: Schweigen, 34:") and "(Ende)" not in wed["text"]
    assert f"–89:21 (Ende)" in thu["text"]
    assert fri["text"].startswith("Neuer Krimi: SOKO")           # SOKO's first day keeps its intro …
    assert out[MON + timedelta(days=7)]["text"].startswith("SOKO Leipzig „Das Auge“, 21:")  # … the second half its own


def test_on_track_follows_the_plan_order_and_ahead_moves_up():
    s = plan_slots()
    clips = clips_for(s)
    done = {"tatort-schweigen": TATORT_END}
    out = rolling.schedule(s, clips, done, 1500, MON + timedelta(days=2))   # Tatort finished by Wednesday
    assert out[MON + timedelta(days=2)]["clip"] == "soko-leipzig-das-auge"  # SOKO moves up a day


def test_today_is_fixed_and_a_ticked_off_block_doesnt_count_as_reached():
    s = plan_slots()
    clips = clips_for(s)
    frozen = {"clip": "tatort-schweigen", "from": 0, "to": 1814}
    out = rolling.schedule(s, clips, {"tatort-schweigen": 430}, 1500, MON, frozen=frozen, today_done=True)
    assert (out[MON]["from"], out[MON]["to"]) == (0, 1814)
    assert out[MON + timedelta(days=1)]["from"] == 430           # tomorrow from where he really is
    out = rolling.schedule(s, clips, {"tatort-schweigen": 430}, 1500, MON, frozen=frozen)
    assert out[MON + timedelta(days=1)]["from"] == 1814          # not ticked off yet: assume he gets there
    # ticked off before anything was fixed (the day this shipped): today shows what was planned
    out = rolling.schedule(s, clips, {"tatort-schweigen": 430}, 1500, MON, today_done=True)
    assert (out[MON]["clip"], out[MON]["from"], out[MON]["to"]) == ("tatort-schweigen", 0, 1814)
    assert out[MON + timedelta(days=1)]["from"] == 430


def test_a_short_clip_never_started_is_not_finished():
    s = plan_slots()
    clips = clips_for(s, durations={"tatort-schweigen": 9})
    clips["tatort-schweigen"]["end"] = 9
    out = rolling.schedule(s, clips, {}, 1500, MON)
    assert out[MON]["clip"] == "tatort-schweigen" and (out[MON]["from"], out[MON]["to"]) == (0, 9)


def test_film_budget_default_then_his_pace(client):
    assert rolling.film_budget("input", 65) == 25 * 60
    with db.tx() as conn:
        for i, (start, reached, secs) in enumerate([(0, 1200, 3600), (1200, 2400, 3600), (2400, 3700, 3900)]):
            d = f"2026-10-{12 + i}"
            conn.execute("INSERT INTO watch_ranges(local_date, block, clip, start, end, clean, reached) VALUES (?, 'input', 'x', ?, ?, 1, ?)",
                         (d, start, start + 1500, reached))
            conn.execute("INSERT INTO activity(local_date, block, started_at, ended_at, seconds) VALUES (?, 'input', ?, ?, ?)",
                         (d, d, d, secs))
    assert rolling.film_budget("input", 65) == pytest.approx(1200 / 3600 * 65 * 60)   # median pace × 65 min


# ── #31: audio heard on the phone ──

TUE, WED, THU, FRI = (MON + timedelta(days=d) for d in (1, 2, 3, 4))
ENDS = {"egp-698": 1914, "egp-684": 1648, "egp-700": 2029, "radio-tatort-uebertherapie": 3300, "tatort-schweigen": TATORT_END}


def ctx(today, positions=None, live=False):
    """His library (no files needed) and player positions by key."""
    lib = {k: {"id": i, "duration": d} for i, (k, d) in enumerate(ENDS.items(), 1)}
    return SimpleNamespace(today=today, real_today=today, live=live, lib=lib,
                           positions={lib[k]["id"]: p for k, p in (positions or {}).items()})


def block(name, today, **kw):
    return rolling.plan_block(name, plan.plan("2B"), MON, ctx(today, **kw))


def sql(query, *args):
    with db.tx() as conn:
        conn.execute(query, args)


def put_range(day, blk, clip, start, end):
    sql("INSERT INTO watch_ranges(local_date, block, clip, start, end, clean) VALUES (?, ?, ?, ?, ?, 1)", day.isoformat(), blk, clip, start, end)


def rate(day, blk, clip, start, end, pct):
    sql("INSERT INTO ratings(created_at, local_date, block, item, kind, label, pct, detail) VALUES (?, ?, ?, ?, 'audio', '', ?, ?)",
        day.isoformat(), day.isoformat(), blk, f"clip:{clip}:{start}-{end}", pct, json.dumps({"from": start, "to": end}))


def tick(day, blk):
    sql("INSERT INTO plan_done(local_date, block) VALUES (?, ?)", day.isoformat(), blk)


MONDAY_HEARD = {"egp-698": 1914}  # Monday's episode, played in Kaskade


def test_audio_rated_after_hearing_it_on_the_phone_moves_on(client):
    """Tuesday's EGP 684, heard on the phone: no player position. Rated (any %) → Wednesday is EGP 700."""
    put_range(TUE, "lesen", "egp-684", 0, 1648)
    assert block("lesen", WED, positions=MONDAY_HEARD)[WED]["clip"] == "egp-684"  # Thursday's bug: it rolls on
    rate(TUE, "lesen", "egp-684", 0, 1648, 20)  # understood little: still heard (#23 changes nothing here)
    out = block("lesen", WED, positions=MONDAY_HEARD)
    assert (out[WED]["clip"], out[WED]["from"]) == ("egp-700", 0)
    assert out[THU]["clip"] == "radio-tatort-uebertherapie"  # and everything after it moves up again


def test_audio_whose_block_he_ticked_off_moves_on(client):
    put_range(TUE, "lesen", "egp-684", 0, 1648)
    tick(TUE, "lesen")
    assert block("lesen", WED, positions=MONDAY_HEARD)[WED]["clip"] == "egp-700"


def test_a_skipped_rating_alone_is_not_heard_but_with_the_block_ticked_off_it_is(client):
    """Tuesday 13.10 had no fixed lesen range yet: the rating's own range tells which audio it was."""
    rate(TUE, "lesen", "egp-684", 0, 1648, None)
    assert block("lesen", WED, positions=MONDAY_HEARD)[WED]["clip"] == "egp-684"
    tick(TUE, "lesen")
    assert block("lesen", WED, positions=MONDAY_HEARD)[WED]["clip"] == "egp-700"


def test_a_saved_position_beyond_the_heard_range_still_wins(client):
    done = {"egp-698": 1914, "egp-684": 1648, "egp-700": 2029}
    put_range(THU, "lesen", "radio-tatort-uebertherapie", 0, 1620)
    rate(THU, "lesen", "radio-tatort-uebertherapie", 0, 1620, 80)
    assert block("lesen", FRI, positions=done)[FRI]["from"] == 1620                      # phone only: from the range's end
    assert block("lesen", FRI, positions={**done, "radio-tatort-uebertherapie": 1800})[FRI]["from"] == 1800  # later in Kaskade


def test_the_input_block_stays_with_his_position(client):
    """Schauen saves where he is: a ticked-off Tatort day he stopped early still continues from there."""
    put_range(TUE, "input", "tatort-schweigen", 430, 2046)
    tick(TUE, "input")
    rate(TUE, "input", "tatort-schweigen", 430, 2046, 80)
    assert block("input", WED, positions={"tatort-schweigen": 1500})[WED]["from"] == 1500
    assert rolling.heard("input", WED) == {}


def test_fixing_the_next_range_notes_the_heard_end_as_reached(client):
    put_range(TUE, "lesen", "egp-684", 0, 1648)
    rate(TUE, "lesen", "egp-684", 0, 1648, 80)
    rolling.plan_block("lesen", plan.plan("2B"), MON, ctx(WED, positions=MONDAY_HEARD, live=True))
    with db.tx() as conn:
        rows = {r["local_date"]: (r["clip"], r["reached"]) for r in conn.execute("SELECT * FROM watch_ranges WHERE block = 'lesen'")}
    assert rows == {TUE.isoformat(): ("egp-684", 1648), WED.isoformat(): ("egp-700", None)}
