"""#38: Momo as a read-along book from Thu 5.11. (paper + Spotify audiobook), QualityLand after it — the book queue."""
from datetime import date, datetime, timedelta, timezone

from kaskade import books, db, plan, stock

from .test_api_materials import add_clip, at, b2, by_block  # noqa: F401  (fixture)

WED_4 = datetime(2026, 11, 4, 11, 30, tzinfo=timezone.utc)          # Mi 4.11. 12:30 Berlin, after the block
OFF = [{"from": "2026-10-19", "to": "2026-10-25"}, {"from": "2026-10-26", "to": "2026-11-01"}]   # two weeks off
HEARD = {"egp-698": 1914.93, "egp-684": 1648.46, "egp-700": 2028.56, "radio-tatort-uebertherapie": 3251.6,
         "egp-693": 1871.75, "egp-695": 1879.43}                    # the lesen audio he has heard by 4.11.
SPOTIFY = "https://open.spotify.com/show/7tJOGiVmP8dJpaLLfsGJgG"
SCHIRACH = "Schirach: nach Momo und QualityLand, weiter mit „Glück“."
MOMO_DAYS = ["2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13",
             "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19"]


def berlin(day: str, hour: int = 12) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:30:00+01:00").astimezone(timezone.utc)


def matt(client, monkeypatch, now=WED_4):
    """His state on Mi 4.11.: Schirach 60 % on Mo, 40 % on Di (parked by #24), today's block done."""
    at(monkeypatch, now)
    ids = {k: add_clip(k, seconds=s) for k, s in {**HEARD, "egp-701": 1920.0, "egp-699": 1989.0}.items()}
    with db.tx() as conn:
        for key, end in HEARD.items():
            conn.execute("INSERT INTO media_progress(media_id, position, updated_at) VALUES (?, ?, 'x')", (ids[key], end))
        for day, part, pct in (("2026-11-02", "S. 7–42: „Fähner“ und „Tanatas Teeschale“", 60),
                               ("2026-11-03", "S. 43–74: „Das Cello“ und „Der Igel“", 40)):
            conn.execute("INSERT INTO ratings(created_at, local_date, block, item, kind, label, book, pct) VALUES"
                         " (?, ?, 'lesen', ?, 'book', 'Schirach', 'schirach-verbrechen', ?)",
                         (f"{day}T10:20:00+00:00", day, f"book:schirach-verbrechen:{part}", pct))
        for day in ("2026-11-02", "2026-11-03", "2026-11-04"):
            conn.execute("INSERT INTO plan_done VALUES (?, 'lesen')", (day,))
    db.set_setting("pauses", OFF)
    db.set_setting("booksBought", ["schirach-verbrechen"])
    return ids


def lesen_on(client, day: str) -> dict:
    return by_block(client.get("/api/materials", params={"today": day}).json()["today"])["lesen"]


def rate(client, monkeypatch, day: str, pct: int | None):
    """He rates the day's book in Heute, at 12:30 that day."""
    at(monkeypatch, berlin(day))
    it = client.get("/api/today").json()["assignments"]["lesen"]
    r = client.post("/api/ratings", json={"block": "lesen", "item": it["rateItem"], "pct": pct})
    assert r.status_code == 200 and r.json()["book"] == it["bookId"], r.text
    return it


def test_thursday_is_momo_1_2_then_easy_german_701(b2, monkeypatch):
    matt(b2, monkeypatch)
    thu = lesen_on(b2, "2026-11-05")
    assert (thu["kind"], thu["bookId"], thu["part"], thu["minutes"]) == (
        "book", "momo", "Kapitel 1–2 — Papierbuch mitlesen, Hörbuch auf Spotify", 49)
    assert thu["title"] == "Michael Ende: Momo" and thu["origin"] == "real" and thu["status"] == "ready"
    assert thu["start"] == {"href": SPOTIFY, "note": "Hörbuch auf Spotify"}
    assert thu["detail"] == "dein Papierbuch · Spotify: von Anfang an (Track 1)"
    assert thu["text"].startswith("Michael Ende: Momo — Erster Teil „Momo und ihre Freunde“: Kapitel 1 „Eine große Stadt und ein kleines Mädchen“ und Kapitel 2")
    assert "bis zu 3 Wörter pro Seite nachschlagen ist in Ordnung" in thu["text"] and "nicht für einzelne Wörter anhalten" in thu["text"]
    # the rest of the 60-minute block: the rolling audio goes on with the next podcast he hasn't heard
    egp = thu["then"][0]
    assert (egp["clip"], egp["range"], egp["minutes"]) == ("egp-701", [0, 640], 11) and len(thu["then"]) == 1
    fri = lesen_on(b2, "2026-11-06")
    assert fri["part"].startswith("Kapitel 3–4") and fri["detail"] == "dein Papierbuch · Spotify: weiter, wo du aufgehört hast"
    assert "weiter, wo du aufgehört hast (nach Kapitel 2)" in fri["text"]
    assert (fri["then"][0]["clip"], fri["then"][0]["range"]) == ("egp-701", [640, 1280])
    # today (done this morning) stays as it was: nachrichtenleicht for Schirach — only the reason is new
    today = b2.get("/api/today").json()["assignments"]["lesen"]
    assert today["kind"] == "news" and today["mode"]["why"] == SCHIRACH.rstrip(".")


def test_momo_runs_in_chapter_order_then_qualityland(b2, monkeypatch):
    matt(b2, monkeypatch)
    seen = []
    for day in MOMO_DAYS:
        it = lesen_on(b2, day)
        assert it["bookId"] == "momo", day
        seen.append(it["chapters"])
    assert seen == [[f"Kapitel {n}" for n in pair] for pair in
                    ([1, 2], [3, 4], [5, 6], [7, 8], [9, 10], [11, 12], [13, 14], [15, 16], [17, 18], [19, 20], [21])]
    last = lesen_on(b2, "2026-11-19")
    assert last["part"] == "Kapitel 21 und Nachwort — Papierbuch mitlesen, Hörbuch auf Spotify" and last["minutes"] == 24
    assert last["text"].endswith("Danach ist das Buch zu Ende.")
    ql = lesen_on(b2, "2026-11-20")
    assert (ql["bookId"], ql["part"], ql["minutes"]) == ("kling-qualityland", "Vom Anfang bis „QualityLand Reiseführer: Ohrwürmer“", 40)
    assert ql["detail"] == "Kaufen bis 18.11." and ql["then"][0]["kind"] == "clip"   # audio for the other 20 min
    # nothing says "Statt Schirach" any more, from Thursday on
    for i in range(45):
        day = (date(2026, 11, 5) + timedelta(days=i)).isoformat()
        g = b2.get("/api/materials", params={"today": day}).json()["today"]
        for it in g["items"]:
            for x in [it, *it["then"]]:
                assert "Statt Schirach" not in (x.get("text") or "") and "kommt nach Woche" not in str(x.get("mode")), day


def test_qualityland_is_due_two_days_before_its_first_day_and_books_say_where_they_are(b2, monkeypatch):
    matt(b2, monkeypatch)
    m = b2.get("/api/materials").json()
    assert [(n["id"], n["by"], n["firstDay"], n["week"]) for n in m["notices"] if n["type"] == "book"] == [
        ("kling-qualityland", "2026-11-18", "2026-11-20", 4)]          # Momo and Die unendliche Geschichte: his own
    assert [b["why"] for b in b2.get("/api/ratings").json()["books"]] == [
        "Momo: mitlesen, zwei Kapitel am Tag — ab Do 5.11.",
        "QualityLand: nach Momo, ab Fr 20.11.",
        SCHIRACH,
        "Die unendliche Geschichte: nach Momo, QualityLand und Schirach."]
    hard = b2.get("/api/today").json()["tooHard"]
    assert {x["action"] for x in hard if x["book"] == "schirach-verbrechen"} == {SCHIRACH}   # 40 % and 60 %


def test_a_day_he_didnt_do_brings_the_same_chapters_again(b2, monkeypatch):
    matt(b2, monkeypatch, berlin("2026-11-06", 8))                 # Fr 08:30: Thursday not rated, not ticked off
    assert lesen_on(b2, "2026-11-06")["part"].startswith("Kapitel 1–2")
    assert lesen_on(b2, "2026-11-09")["part"].startswith("Kapitel 3–4")
    ql = next(n for n in b2.get("/api/materials").json()["notices"] if n["id"] == "kling-qualityland")
    assert (ql["firstDay"], ql["by"]) == ("2026-11-23", "2026-11-21")
    with db.tx() as conn:                                            # ticked off counts as done, without a rating
        conn.execute("INSERT INTO plan_done VALUES ('2026-11-05', 'lesen')")
    assert lesen_on(b2, "2026-11-06")["part"].startswith("Kapitel 3–4")


def test_40_percent_means_each_chapter_twice_and_60_ends_it(b2, monkeypatch):
    matt(b2, monkeypatch)
    rate(b2, monkeypatch, "2026-11-05", 40)
    assert b2.get("/api/today").json()["assignments"]["lesen"]["part"].startswith("Kapitel 1–2")   # today stays
    fri = lesen_on(b2, "2026-11-06")
    assert (fri["part"], fri["minutes"], fri["repeat"]) == ("Kapitel 1 zweimal — erst nur hören, dann mitlesen", 49, True)
    assert fri["detail"] == "dein Papierbuch · Spotify: zurück an den Anfang von Kapitel 1"
    assert "zweimal: erst nur hören (Buch zu), dann noch einmal von vorn und im Papierbuch mitlesen" in fri["text"]
    why = "Momo: 40 % am Do 5.11. → Kapitel zweimal hören: erst nur hören, dann mitlesen (ein Kapitel am Tag)"
    assert fri["mode"]["why"] == why
    assert [x["action"] for x in b2.get("/api/today").json()["tooHard"] if x["book"] == "momo"] == [why + "."]
    assert lesen_on(b2, "2026-11-09")["part"].startswith("Kapitel 2 zweimal")
    new = lesen_on(b2, "2026-11-10")                                  # still too hard: a new chapter, also twice
    assert new["part"].startswith("Kapitel 3 zweimal") and new["detail"] == "dein Papierbuch · Spotify: weiter, wo du aufgehört hast"
    # 60 % on the first repeat day: chapter 2 still gets its second go, then two chapters a day again
    rate(b2, monkeypatch, "2026-11-06", 60)
    at(monkeypatch, berlin("2026-11-06", 13))
    second = lesen_on(b2, "2026-11-09")
    assert second["part"].startswith("Kapitel 2 zweimal")
    assert second["mode"]["why"] == "Momo: 60 % am Fr 6.11. → noch Kapitel 2 zweimal, danach wieder mitlesen, zwei Kapitel am Tag"
    back = lesen_on(b2, "2026-11-10")
    assert back["part"].startswith("Kapitel 3–4") and back["mode"]["why"] == "Momo: 60 % am Fr 6.11. → weiter mitlesen, zwei Kapitel am Tag"


def test_parked_only_after_two_ratings_of_20_40_while_repeating(b2, monkeypatch):
    matt(b2, monkeypatch)
    rate(b2, monkeypatch, "2026-11-05", 40)                          # → repeat mode
    rate(b2, monkeypatch, "2026-11-06", 40)                          # one while repeating: not yet
    at(monkeypatch, berlin("2026-11-06", 13))
    assert lesen_on(b2, "2026-11-09")["bookId"] == "momo"
    rate(b2, monkeypatch, "2026-11-09", 20)                          # two in a row → parked
    at(monkeypatch, berlin("2026-11-09", 13))
    tue = lesen_on(b2, "2026-11-10")
    assert tue["bookId"] == "kling-qualityland" and tue["part"].startswith("Vom Anfang")
    lines = {b["book"]: b["why"] for b in b2.get("/api/ratings").json()["books"]}
    assert lines["momo"] == ("Momo: 40 % am Fr 6.11. und 20 % am Mo 9.11. → pausiert, kommt nach QualityLand, Schirach "
                             "und Die unendliche Geschichte wieder.")


def test_schirach_comes_back_after_qualityland_with_a_lesetest_on_glueck(b2, monkeypatch):
    matt(b2, monkeypatch)
    sched = books.schedule(plan.plan("2B"), date(2026, 10, 12), OFF, date(2026, 11, 4))
    first = books.first_days(sched)
    assert {k: v.isoformat() for k, v in first.items()} == {
        "momo": "2026-11-05", "kling-qualityland": "2026-11-20", "schirach-verbrechen": "2026-12-15",
        "ende-unendliche-geschichte": "2026-12-23"}
    test = lesen_on(b2, "2026-12-15")
    assert test["kind"] == "lesetest" and test["title"] == "Lesetest: Schirach, Verbrechen — die ersten zwei Seiten von „Glück“"
    assert test["part"] == "S. 75–76" and test["detail"] == "im Buch, S. 75–76 · ohne Wörterbuch lesen, dann einschätzen"
    assert "start" not in test or test["start"] is None                # the Leseprobe ends at S. 20: his paper book
    glueck = lesen_on(b2, "2026-12-16")
    assert (glueck["bookId"], glueck["part"]) == ("schirach-verbrechen", "S. 75–88: „Glück“")


def test_the_plan_text_is_the_queues_first_draft(b2, monkeypatch):
    """The book items written into the plan from week 2 Thursday are what the queue gives with no ratings."""
    matt(b2, monkeypatch)
    data = plan.plan("2B")
    sched = books.schedule(data, date(2026, 10, 12), OFF, date(2026, 11, 4))["days"]
    for day in MOMO_DAYS + ["2026-11-20"]:
        d = plan.plan_day(date(2026, 10, 12), date.fromisoformat(day), data, OFF)["day"]
        written = next(m for m in d["materials"] if m["block"] == "lesen")
        got = sched[date.fromisoformat(day)]
        assert (written["book"], written["part"], written["minutes"], written["desc"]) == (
            got["book"], got["part"], got["minutes"], got["desc"]), day
    assert stock.book("momo")["owned"] and stock.book("ende-unendliche-geschichte")["owned"]
