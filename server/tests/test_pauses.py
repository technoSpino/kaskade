"""#36: a week off (Mo 19.10.–So 25.10.) moves the whole plan back one week."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fsrs import Card, State

from kaskade import db, plan, rolling, srs

from .test_api_materials import add_clip, at, b2, by_block  # noqa: F401  (fixture)
from .test_rolling import ENDS, TATORT_END, clips_for

MON = date(2026, 10, 12)
OFF = [{"from": "2026-10-19", "to": "2026-10-25"}]
TUE_20 = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)        # Di 20.10. 14:00 Berlin, in the week off
MON_26 = datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)         # Mo 26.10. 09:00 Berlin (CET), week 2
SOKO_AT = 1314.02                                                   # 21:54, where he stopped on Fr 16.10.
RADIO_AT = 1626                                                     # 27:06, the end of Friday's range


# ── The plan dates ───────────────────────────────────────────────────────────

def test_plan_day_skips_the_week_off():
    data = plan.plan("2B")
    tue = plan.plan_day(MON, date(2026, 10, 20), data, OFF)
    assert tue["day"] is None and tue["pause"] == {"from": "2026-10-19", "to": "2026-10-25", "resume": "2026-10-26"}
    assert tue["week"] == 2 and tue["todos"] == []           # the plan week that comes after it
    assert plan.plan_day(MON, date(2026, 10, 25), data, OFF)["pause"]   # its Sunday too
    mo = plan.plan_day(MON, date(2026, 10, 26), data, OFF)
    assert (mo["week"], mo["weekday"], mo["pause"]) == (2, "Mo", None) and mo["day"] == data["weeks"][1]["days"][0]
    w3 = plan.plan_day(MON, date(2026, 11, 2), data, OFF)
    assert w3["week"] == 3 and w3["day"] == data["weeks"][2]["days"][0]
    w4 = plan.plan_day(MON, date(2026, 11, 9), data, OFF)
    assert w4["week"] == 4 and w4["day"] == data["weeks"][3]["days"][0]
    fri = plan.plan_day(MON, date(2026, 10, 16), data, OFF)  # week 1 stays as it was
    assert fri["week"] == 1 and fri["day"] == data["weeks"][0]["days"][4]
    assert plan.plan_day(MON, date(2026, 11, 16), data, OFF)["week"] == 5   # the week-5/6 dates move along
    assert plan.plan_day(MON, date(2026, 10, 20), data)["week"] == 2 and plan.plan_day(MON, date(2026, 10, 26), data)["week"] == 3


def test_upcoming_and_slot_dates_move_along():
    data = {"week5": {"todos": [{"id": "x", "title": "Vorher", "text": "…"}]}, "week6": {"title": "Probe", "note": "…"}}
    assert [u["date"] for u in plan.upcoming(MON, data, OFF)] == ["2026-11-16", "2026-11-23"]
    assert [u["date"] for u in plan.upcoming(MON, data)] == ["2026-11-09", "2026-11-16"]
    assert plan.slot_date(MON, 0, 4, OFF) == date(2026, 10, 16) and plan.slot_date(MON, 1, 0, OFF) == date(2026, 10, 26)
    two = OFF + [{"from": "2026-11-02", "to": "2026-11-08"}]       # two weeks off, one plan week apart
    assert plan.slot_date(MON, 2, 0, two) == date(2026, 11, 9) and plan.plan_index(MON, date(2026, 11, 4), two) == (2, True)
    assert plan.pause_around(MON, date(2026, 10, 19), OFF + [{"from": "2026-10-26", "to": "2026-11-01"}])["to"] == "2026-11-01"
    assert plan.paused_days(["2026-10-18", "2026-10-19", "2026-10-25", "2026-10-26"], MON, OFF) == [False, True, True, False]


# ── Rolling ranges: he goes on where he stopped ──────────────────────────────

def test_no_slot_in_the_week_off_and_soko_resumes_at_21_54():
    s = rolling.slots(MON, plan.plan("2B"), "input", OFF)
    assert not any(date(2026, 10, 19) <= x["date"] <= date(2026, 10, 25) for x in s)
    out = rolling.schedule(s, clips_for(s), {"tatort-schweigen": TATORT_END, "soko-leipzig-das-auge": SOKO_AT}, 1500,
                           date(2026, 10, 20))
    assert min(out) == date(2026, 10, 26)
    mo = out[date(2026, 10, 26)]
    assert (mo["clip"], mo["from"], mo["to"], mo["final"]) == ("soko-leipzig-das-auge", 1314, 2611, True)
    assert out[date(2026, 10, 27)]["clip"] == "merz-gegen-merz-1"   # then week 2 rolls on as before


def test_radio_tatort_resumes_at_27_06():
    s = rolling.slots(MON, plan.plan("2B"), "lesen", OFF)
    heard = {k: v for k, v in ENDS.items() if k.startswith("egp-")} | {"radio-tatort-uebertherapie": RADIO_AT}
    out = rolling.schedule(s, clips_for(s, durations=ENDS), heard, 1680, date(2026, 10, 20))
    mo = out[date(2026, 10, 26)]
    assert (mo["clip"], mo["from"]) == ("radio-tatort-uebertherapie", 1626) and mo["to"] == 3300


# ── Heute, Material, notices ─────────────────────────────────────────────────

def matt(b2, monkeypatch, when=TUE_20):
    """His state on Di 20.10.: week 1 done, SOKO at 21:54, Radio Tatort rated 0–27:06, the week off set."""
    at(monkeypatch, when)
    tatort = add_clip("tatort-schweigen")
    soko = add_clip("soko-leipzig-das-auge", seconds=2611.0)
    add_clip("radio-tatort-uebertherapie", seconds=3252.0)
    heard = {add_clip(k, seconds=float(ENDS[k])): ENDS[k] for k in ("egp-698", "egp-684", "egp-700")}  # week 1's podcasts
    with db.tx() as conn:
        for mid, pos in {tatort: 5359.6, soko: SOKO_AT, **heard}.items():
            conn.execute("INSERT INTO media_progress(media_id, position, updated_at) VALUES (?, ?, 'x')", (mid, pos))
        conn.execute("INSERT INTO ratings(created_at, local_date, block, item, kind, label, pct, detail) VALUES"
                     " ('2026-10-16T09:22:39+00:00', '2026-10-16', 'lesen', 'clip:radio-tatort-uebertherapie:0-1626',"
                     " 'audio', 'Radio Tatort', 60, ?)", (json.dumps({"from": 0, "to": RADIO_AT}),))
        conn.execute("INSERT INTO ratings(created_at, local_date, block, item, kind, label, pct, detail) VALUES"
                     " ('2026-10-16T08:55:13+00:00', '2026-10-16', 'input', 'clip:soko-leipzig-das-auge:0-1314',"
                     " 'clip', 'SOKO', 60, NULL)")
    db.set_setting("pauses", OFF)
    return soko


def test_heute_in_the_week_off_is_one_calm_line(b2, monkeypatch):
    matt(b2, monkeypatch)
    t = b2.get("/api/today").json()
    assert t["day"] is None and t["assignments"] == {} and t["tooHard"] == []   # no blocks, no "Zu schwer"
    assert t["pause"]["line"] == "Freie Woche bis So 25.10. — weiter am Mo 26.10. mit SOKO Leipzig ab 21:54."
    assert t["preview"]["date"] == "2026-10-26" and t["preview"]["week"] == 2
    assert t["weekTotals"]["free"] == [True] * 7                # the hours chart says "frei", not missed
    assert t["cards"]["due"] == 0 and t["running"] is None
    # no rating prompts for 19.–25.10.
    r = b2.post("/api/ratings", json={"block": "input", "pct": 60})
    assert r.status_code == 422
    assert b2.get("/api/ratings/today").json() == []
    # no range is fixed for a paused day
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM watch_ranges WHERE local_date >= '2026-10-19'").fetchone()[0] == 0


def test_materials_and_notices_follow_the_shifted_plan(b2, monkeypatch):
    matt(b2, monkeypatch)
    m = b2.get("/api/materials").json()
    assert not m["today"]["planDay"] and m["today"]["items"] == []
    assert (m["next"]["date"], m["next"]["kind"], m["next"]["week"]) == ("2026-10-26", "next", 2)
    nxt = by_block(m["next"])
    assert nxt["input"]["clip"] == "soko-leipzig-das-auge" and nxt["input"]["part"] == "21:54–43:31"
    ql = next(n for n in m["notices"] if n["id"] == "kling-qualityland")
    assert (ql["by"], ql["firstDay"], ql["week"]) == ("2026-11-07", "2026-11-09", 4)   # Kindle: 2 days ahead
    # on the day itself, Radio Tatort goes on at 27:06 after the Schirach pages, which stay as they were
    at(monkeypatch, MON_26)
    lesen = by_block(b2.get("/api/materials").json()["today"])["lesen"]
    assert lesen["kind"] == "book" and lesen["part"] == "S. 7–42: „Fähner“ und „Tanatas Teeschale“"
    assert lesen["mode"]["mode"] == "nachschlagen" and lesen["mode"]["assumed"]
    radio = lesen["then"][0]
    assert radio["clip"] == "radio-tatort-uebertherapie" and radio["range"] == [RADIO_AT, 3252]


def test_the_unrated_lesetest_is_decided_in_the_week_off(b2, monkeypatch):
    matt(b2, monkeypatch)
    books = b2.get("/api/ratings").json()["books"]
    assert books[0]["why"] == "Schirach: kein Lesetest am Fr 16.10. → wie 60 % → bis zu 3 Wörter pro Seite nachschlagen"


def test_monday_after_the_week_off_fixes_soko_from_21_54(b2, monkeypatch):
    matt(b2, monkeypatch, MON_26)
    inp = b2.get("/api/today").json()["assignments"]["input"]
    assert inp["clip"] == "soko-leipzig-das-auge" and inp["range"] == [1314, 2611]
    with db.tx() as conn:
        rows = conn.execute("SELECT local_date, block, clip, start FROM watch_ranges ORDER BY block").fetchall()
    assert [tuple(r) for r in rows] == [("2026-10-26", "input", "soko-leipzig-das-auge", 1314.0),
                                        ("2026-10-26", "lesen", "radio-tatort-uebertherapie", 1626.0)]


# ── A forgotten timer ────────────────────────────────────────────────────────

def test_a_timer_forgotten_on_friday_is_not_running(b2, monkeypatch):
    at(monkeypatch, TUE_20)
    with db.tx() as conn:
        conn.execute("INSERT INTO activity(local_date, block, started_at) VALUES ('2026-10-16', 'lesen', '2026-10-16T08:55:27+00:00')")
    assert b2.get("/api/status").json()["running"] is None
    assert b2.get("/api/today").json()["running"] is None
    at(monkeypatch, datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc))   # an hour in, it still runs
    assert b2.get("/api/status").json()["running"]["block"] == "lesen"


# ── Karten: due dates stay, new cards wait for the backlog ───────────────────

def due(n, when, skip=0):
    with db.tx() as conn:
        for c in srs.deck()[skip:skip + n]:
            card = Card()
            card.state, card.stability, card.difficulty = State.Review, 5.0, 5.0
            card.due, card.last_review = when, when - timedelta(days=5)
            conn.execute("INSERT INTO cards(id, status, fsrs, due, introduced_on, lapses, updated_at)"
                         " VALUES (?, 'learning', ?, ?, '2026-10-12', 0, ?)",
                         (c["id"], json.dumps(card.to_dict()), when.isoformat(), when.isoformat()))


def test_no_new_cards_after_the_week_off_until_fewer_than_20_are_due(b2, monkeypatch):
    db.set_setting("pauses", OFF)
    due(25, datetime(2026, 10, 21, 6, 0, tzinfo=timezone.utc))
    at(monkeypatch, TUE_20)   # in the week off, only 0 due today: new cards as usual
    with db.tx() as conn:
        assert srs.counts(conn, TUE_20)["new"] == 20
    at(monkeypatch, MON_26)
    c = b2.get("/api/cards/next").json()
    assert c["counts"]["due"] == 25 and c["counts"]["new"] == 0 and c["counts"]["newHeld"] and c["counts"]["left"] == 25
    assert not c["card"]["isNew"]                              # reviews first
    t = b2.get("/api/today").json()
    assert t["cards"]["left"] == 25                            # the bar shows the real count (#25)
    for _ in range(6):                                         # 19 left → new cards again
        cid = b2.get("/api/cards/next").json()["card"]["id"]
        b2.post(f"/api/cards/{cid}/review", json={"rating": 3})
    c = b2.get("/api/cards/next").json()["counts"]
    assert c["due"] == 19 and c["new"] == 20 and not c["newHeld"]
    assert db.get_setting("cardsCaughtUp") == ["2026-10-19"]
    # once caught up, a busy day later is a normal day
    due(40, datetime(2026, 10, 27, 6, 0, tzinfo=timezone.utc), skip=25)
    at(monkeypatch, MON_26 + timedelta(days=1))
    assert not b2.get("/api/cards/next").json()["counts"]["newHeld"]


def test_cards_tile_in_the_preview_counts_no_new_ones_while_held(b2, monkeypatch):
    matt(b2, monkeypatch)
    due(30, datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc))
    nxt = by_block(b2.get("/api/materials").json()["next"])
    assert nxt["karten"]["part"] == "30 fällig + 0 neu"


# ── "Woche frei nehmen" ─────────────────────────────────────────────────────

def test_take_this_week_off_drops_its_fixed_ranges(b2, monkeypatch):
    at(monkeypatch, TUE_20)
    with db.tx() as conn:
        for d in ("2026-10-16", "2026-10-19", "2026-10-20"):
            for blk in ("input", "lesen"):
                conn.execute("INSERT INTO watch_ranges(local_date, block, clip, start, end, clean) VALUES (?, ?, 'x', 0, 1, 1)", (d, blk))
    opts = b2.get("/api/pauses").json()["options"]
    assert opts[0] == {"from": "2026-10-19", "to": "2026-10-25", "problem": None} and len(opts) == 8
    r = b2.post("/api/pauses", json={"monday": "2026-10-19"})
    assert r.status_code == 200 and r.json()["pauses"] == [{"from": "2026-10-19", "to": "2026-10-25", "canUndo": False}]
    assert db.get_setting("pauses") == OFF
    with db.tx() as conn:
        assert [r[0] for r in conn.execute("SELECT DISTINCT local_date FROM watch_ranges")] == ["2026-10-16"]
    assert b2.delete("/api/pauses/2026-10-19").status_code == 409        # it has started
    assert b2.post("/api/pauses", json={"monday": "2026-10-19"}).json()["detail"] == "Diese Woche ist schon frei."


def test_a_week_already_worked_in_cant_be_taken_off(b2, monkeypatch):
    at(monkeypatch, TUE_20)
    with db.tx() as conn:
        conn.execute("INSERT INTO plan_done(local_date, block) VALUES ('2026-10-19', 'karten')")
    r = b2.post("/api/pauses", json={"monday": "2026-10-19"})
    assert r.status_code == 422 and "schon gelernt" in r.json()["detail"]
    assert b2.post("/api/pauses", json={"monday": "2026-10-21"}).status_code == 422   # not a Monday
    assert b2.post("/api/pauses", json={"monday": "2026-10-12"}).json()["detail"] == "Diese Woche ist schon vorbei."


def test_preview_then_take_a_later_week_off_and_undo_it(b2, monkeypatch):
    matt(b2, monkeypatch)
    p = b2.get("/api/pauses/preview", params={"monday": "2026-11-02"}).json()
    assert p["week"] == {"n": 3, "theme": plan.plan("2B")["weeks"][2]["theme"], "was": "2026-11-02", "now": "2026-11-09"}
    assert {"id": "kling-qualityland", "title": "Marc-Uwe Kling: QualityLand", "was": "2026-11-07", "now": "2026-11-14"} in p["due"]
    assert p["line"].startswith("Freie Woche bis So 8.11. — weiter am Mo 9.11. mit ")
    assert b2.post("/api/pauses", json={"monday": "2026-11-02"}).status_code == 200
    ql = next(n for n in b2.get("/api/materials").json()["notices"] if n["id"] == "kling-qualityland")
    assert ql["by"] == "2026-11-14"
    view = b2.delete("/api/pauses/2026-11-02").json()
    assert [x["from"] for x in view["pauses"]] == ["2026-10-19"] and db.get_setting("pauses") == OFF


def test_fahrplan_counts_the_week_off_as_frei(b2, monkeypatch):
    matt(b2, monkeypatch, datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc))
    with db.tx() as conn:   # 3 h in week 1, nothing in the week off
        conn.execute("INSERT INTO activity(local_date, block, started_at, ended_at, seconds) VALUES"
                     " ('2026-10-13', 'input', '2026-10-13T07:00:00+00:00', '2026-10-13T10:00:00+00:00', 10800)")
    f = b2.get("/api/fahrplan").json()
    weeks = {w["week"]: w["free"] for w in f["weeks"]}
    assert weeks["2026-10-19"] and not weeks["2026-10-12"] and not weeks["2026-10-26"]
    assert f["forecast"]["measuredPerWeek"] == pytest.approx(3 / 3, abs=0.05)   # over 3 weeks, not 4


def test_a_preview_of_a_later_day_doesnt_pick_its_articles(b2, monkeypatch):
    """Found while checking #36: /api/materials?today=<later day> fixed that day's nachrichtenleicht links early."""
    at(monkeypatch, TUE_20)
    picked = []
    monkeypatch.setattr("kaskade.materials.fetch_feed", lambda url: picked.append(url) or b"")
    b2.get("/api/materials", params={"today": "2026-10-29"})    # W2 Do: nachrichtenleicht in the old plan
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM news_picks").fetchone()[0] == 0
    assert picked == []
