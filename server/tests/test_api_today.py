from datetime import datetime, timedelta, timezone

from kaskade import srs

FIXED = datetime(2026, 10, 13, 7, 30, tzinfo=timezone.utc)  # Tuesday 09:30 Berlin


def at(monkeypatch, when):
    monkeypatch.setattr(srs, "now_utc", lambda: when)


def test_today_sets_plan_start_and_returns_day(client, monkeypatch):
    at(monkeypatch, FIXED)
    t = client.get("/api/today").json()
    assert t["planStart"] == "2026-10-12"
    assert t["week"] == 1 and t["weekday"] == "Di" and t["exam"] is None  # #27: no exam block
    assert [b["id"] for b in t["block"]] == ["karten", "input", "pause", "lesen"]
    assert t["running"] is None and t["immersion"]["hours"] == 150
    assert t["cards"]["new"] == 20


def test_weekend_shows_preview_of_monday(client, monkeypatch):
    at(monkeypatch, datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc))  # Saturday
    t = client.get("/api/today").json()
    assert t["weekend"] and t["day"] is None
    assert t["planStart"] == "2026-10-12"
    assert t["preview"]["date"] == "2026-10-12" and t["preview"]["day"]["day"] == "Mo"
    # Saturday before the start: both flags, so Heute can name the start date in its hint.
    assert t["beforeStart"] is True


def test_weekend_after_start_is_a_preview_of_next_monday(client, monkeypatch):
    client.put("/api/plan/start", json={"planStart": "2026-10-12"})
    at(monkeypatch, datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc))  # Saturday of week 1
    t = client.get("/api/today").json()
    assert t["weekend"] and not t["beforeStart"] and t["day"] is None
    assert t["preview"]["date"] == "2026-10-19" and t["preview"]["week"] == 2


def test_status_reports_running_timer(client, monkeypatch):
    at(monkeypatch, FIXED)
    client.post("/api/activity/start", json={"block": "lesen"})
    assert client.get("/api/status").json()["running"]["block"] == "lesen"
    client.post("/api/activity/stop")
    assert client.get("/api/status").json()["running"] is None


def test_timer_start_stop_counts_minutes(client, monkeypatch):
    at(monkeypatch, FIXED)
    assert client.post("/api/activity/start", json={"block": "input"}).status_code == 200
    assert client.get("/api/today").json()["running"]["block"] == "input"
    at(monkeypatch, FIXED + timedelta(minutes=25))
    client.post("/api/activity/stop")
    t = client.get("/api/today").json()
    assert t["blockSeconds"]["input"] == 1500
    assert t["weekTotals"]["seconds"][1] == 1500  # Tuesday
    assert t["immersion"]["hours"] == round(150 + 1500 / 3600, 1)


def test_starting_a_block_stops_the_running_one(client, monkeypatch):
    at(monkeypatch, FIXED)
    client.post("/api/activity/start", json={"block": "karten"})
    at(monkeypatch, FIXED + timedelta(minutes=10))
    client.post("/api/activity/start", json={"block": "input"})
    t = client.get("/api/today").json()
    assert t["blockSeconds"]["karten"] == 600 and t["running"]["block"] == "input"


def test_unknown_block_rejected(client):
    assert client.post("/api/activity/start", json={"block": "schlafen"}).status_code == 422
    assert client.post("/api/plan/done", json={"block": "schlafen"}).status_code == 422


def test_mark_done_and_undo(client, monkeypatch):
    at(monkeypatch, FIXED)
    client.post("/api/plan/done", json={"block": "karten"})
    assert client.get("/api/today").json()["done"] == ["karten"]
    client.post("/api/plan/done", json={"block": "karten", "done": False})
    assert client.get("/api/today").json()["done"] == []


def test_fahrplan(client, monkeypatch):
    at(monkeypatch, FIXED)
    f = client.get("/api/fahrplan").json()
    assert f["hours"] == 150 and f["target"] == 1150 and f["hoursPhase"] == "2"
    assert f["forecast"]["blockPassive"] < f["forecast"]["block"]
    assert f["forecast"]["measured"] is None  # no data yet
    assert f["placements"] == [] and f["nextCheck"] is None
    ratings = [{"cue": i, "text": "x", "rating": "v"} for i in range(5)]
    client.post("/api/satzcheck", json={"contentType": "adult", "windowStart": 0, "windowEnd": 180, "ratings": ratings})
    f = client.get("/api/fahrplan").json()
    assert f["satzchecks"][0]["coverage"] == 100 and f["nextCheck"]


def test_plan_and_prompt(client):
    p = client.get("/api/plan").json()
    assert len(p["weeks"]) == 4 and len(p["prompts"]) == 16
    assert client.get("/api/plan/prompt/s01").json()["skill"] == "schreiben"
    assert client.get("/api/plan/prompt/zz").status_code == 404


def test_set_plan_start_must_be_monday(client):
    assert client.put("/api/plan/start", json={"planStart": "2026-10-19"}).json()["planStart"] == "2026-10-19"
    assert client.put("/api/plan/start", json={"planStart": "2026-10-20"}).status_code == 422


def test_plan_prompt_writing_can_be_saved(client):
    r = client.post("/api/writing", json={"context": "plan:2026-10-12", "promptId": "s01", "text": "Liebe Lea, …"})
    assert r.status_code == 200 and r.json()["grade"] is None


def test_manual_immersion_counts_into_today_and_fahrplan(client, monkeypatch):
    at(monkeypatch, FIXED)
    r = client.post("/api/immersion", json={"title": "Checker Tobi", "minutes": 30, "kind": "passiv"})
    assert r.status_code == 200 and r.json()["date"] == "2026-10-13"
    client.post("/api/immersion", json={"title": "Serie", "minutes": 60, "kind": "aktiv", "date": "2026-10-12"})
    t = client.get("/api/today").json()
    assert t["weekTotals"]["passive"][1] == 1800 and t["weekTotals"]["seconds"][0] == 3600
    assert t["immersion"]["hours"] == 151.5
    f = client.get("/api/fahrplan").json()
    assert f["hours"] == 151.5 and f["weeks"][-1] == {"week": "2026-10-12", "aktiv": 1.0, "passiv": 0.5, "free": False}
    lst = client.get("/api/immersion").json()
    assert [e["title"] for e in lst["entries"]] == ["Checker Tobi", "Serie"]
    assert client.delete(f"/api/immersion/{r.json()['id']}").json() == {"ok": True}
    assert client.get("/api/today").json()["immersion"]["hours"] == 151.0


def test_immersion_validation(client, monkeypatch):
    at(monkeypatch, FIXED)
    assert client.post("/api/immersion", json={"title": "x", "minutes": 0, "kind": "aktiv"}).status_code == 422
    assert client.post("/api/immersion", json={"title": "x", "minutes": 5, "kind": "halb"}).status_code == 422
    assert client.post("/api/immersion", json={"title": "x", "minutes": 5, "kind": "aktiv", "date": "2030-01-01"}).status_code == 422
    assert client.delete("/api/immersion/999").status_code == 404


MONDAY_0900 = datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)  # Mon 12 Oct, 09:00 Berlin


def test_phase_2b_switches_to_the_2b_block(client, monkeypatch):
    from kaskade import db
    db.set_setting("phase", "2B")
    at(monkeypatch, MONDAY_0900)
    t = client.get("/api/today").json()
    assert t["planPhase"] == "2B" and t["week"] == 1 and t["weekday"] == "Mo"
    assert [(b["id"], b["minutes"]) for b in t["block"]] == [
        ("karten", 15), ("input", 65), ("pause", 10), ("lesen", 60)]
    assert "Tatort" in t["day"]["input"]
    assert t["exam"] is None and "pruefung" not in t["assignments"]  # #27: the time went to lesen/hören
    # timers and "Fertig" work with the 2B block
    assert client.post("/api/activity/start", json={"block": "input"}).status_code == 200
    assert client.post("/api/plan/done", json={"block": "input"}).json()["done"] is True
    assert client.get("/api/plan").json()["phase"] == "2B"


def test_phase_2a_keeps_the_2a_block(client, monkeypatch):
    from kaskade import db
    db.set_setting("phase", "2A")
    at(monkeypatch, MONDAY_0900)
    t = client.get("/api/today").json()
    assert t["planPhase"] == "2A" and t["block"][0]["minutes"] == 30


def test_satzcheck_lines_can_be_mined_as_cards(client, monkeypatch):
    at(monkeypatch, MONDAY_0900)
    ratings = [
        {"cue": 1, "text": "Na?", "rating": "s"},
        {"cue": 2, "text": "* Musik spielt *", "rating": "h"},
        {"cue": 3, "text": "Glaubst du mir nicht?", "rating": "h"},
        {"cue": 4, "text": "Ich bin seit 'ner Stunde hier.", "rating": "v"},
        {"cue": 5, "text": "♪ La la la ♪", "rating": "s"},
    ]
    client.post("/api/satzcheck", json={"contentType": "adult", "windowStart": 0, "windowEnd": 180, "ratings": ratings})
    lines = client.get("/api/satzcheck/lines").json()
    assert [(x["text"], x["rating"], x["mined"]) for x in lines] == [("Na?", "s", False), ("Glaubst du mir nicht?", "h", False)]
    assert client.get("/api/today").json()["mineable"] == 2
    client.post("/api/mined", json={"sentence": "Glaubst du mir nicht?", "target": "Glaubst", "lemma": "glauben", "source": "Satz-Check"})
    assert [x["mined"] for x in client.get("/api/satzcheck/lines").json()] == [False, True]
    assert client.get("/api/today").json()["mineable"] == 1


WEEK5_MONDAY = datetime(2026, 11, 9, 8, 0, tzinfo=timezone.utc)  # Mon 9 Nov 2026, plan week 5


def test_week5_has_no_todo_and_fahrplan_says_the_exam_is_paused(client, monkeypatch):
    """#27: the week-5 "KI-Schlüssel vor dem Probetest" to-do and the week-6 mock exam are parked."""
    client.put("/api/plan/start", json={"planStart": "2026-10-12"})
    at(monkeypatch, WEEK5_MONDAY)
    t = client.get("/api/today").json()
    assert t["week"] == 5 and t["todos"] == []
    assert client.post("/api/todos/ai-key", json={"done": True}).status_code == 404
    f = client.get("/api/fahrplan").json()
    assert f["upcoming"] == [] and f["exam"] == "B1-Prüfung: pausiert — kommt zurück, wenn du ein Prüfungsdatum wählst."
