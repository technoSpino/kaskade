from datetime import date, datetime, timedelta, timezone

import pytest

from kaskade import plan

MON = date(2026, 10, 12)


@pytest.mark.parametrize("today, start", [
    (date(2026, 10, 12), MON),          # Monday
    (date(2026, 10, 14), MON),          # Wednesday → this week
    (date(2026, 10, 9), MON),           # Thursday/Friday → next Monday
    (date(2026, 10, 10), MON),          # Saturday → next Monday
    (date(2026, 10, 11), MON),          # Sunday → next Monday
])
def test_default_start(today, start):
    assert plan.default_start(today) == start


def test_first_monday_is_week_1_without_an_exam_task():
    """#27: no exam date yet — no Prüfungsteil in the daily plan."""
    d = plan.plan_day(MON, MON)
    assert d["week"] == 1 and d["weekday"] == "Mo" and not d["weekend"]
    assert d["exam"] is None and d["mockExam"] is None


def test_no_exam_on_any_plan_day_but_the_16_prompts_stay():
    for phase in (None, "2B"):
        for i in range(42):
            d = plan.plan_day(MON, MON + timedelta(days=i), plan.plan(phase))
            assert d["exam"] is None and d["mockExam"] is None, (phase, i)
    prompts = plan.plan()["prompts"]
    assert len(prompts) == 16 and len({p["id"] for p in prompts}) == 16  # still on the Prüfung page


def test_weekend_and_before_start_have_no_day():
    assert plan.plan_day(MON, MON + timedelta(days=5))["weekend"] is True
    assert plan.plan_day(MON, MON + timedelta(days=5))["day"] is None
    before = plan.plan_day(MON, MON - timedelta(days=3))
    assert before["beforeStart"] is True and before["day"] is None


def test_weeks_5_and_6_repeat_the_plan_without_a_mock_exam():
    w5 = plan.plan_day(MON, MON + timedelta(days=28))
    assert w5["week"] == 5 and w5.get("repeat") and w5["day"] and w5["todos"] == []
    w6 = plan.plan_day(MON, MON + timedelta(days=35))
    assert w6["week"] == 6 and w6["mockExam"] is None and w6["exam"] is None
    assert plan.upcoming(MON, plan.plan()) == []


def test_session_seconds_caps_forgotten_timers():
    t = datetime(2026, 10, 12, 7, tzinfo=timezone.utc)
    assert plan.session_seconds(t, t + timedelta(minutes=30), t) == 1800
    assert plan.session_seconds(t, None, t + timedelta(hours=10)) == plan.MAX_SESSION
    assert plan.session_seconds(t, t - timedelta(minutes=1), t) == 0


def test_totals_by_day_includes_running_timer():
    now = datetime(2026, 10, 12, 8, tzinfo=timezone.utc)
    rows = [
        {"local_date": "2026-10-12", "started_at": "2026-10-12T07:00:00+00:00", "ended_at": "x", "seconds": 1800},
        {"local_date": "2026-10-12", "started_at": "2026-10-12T07:50:00+00:00", "ended_at": None, "seconds": 0},
        {"local_date": "2026-10-13", "started_at": "2026-10-13T07:00:00+00:00", "ended_at": "x", "seconds": 600},
    ]
    assert plan.totals_by_day(rows, now) == {"2026-10-12": 1800 + 600, "2026-10-13": 600}


def test_week_days_start_monday():
    days = plan.week_days(date(2026, 10, 15))
    assert days[0] == "2026-10-12" and days[-1] == "2026-10-18"


def test_forecast():
    assert plan.forecast(1150, 10, MON) == MON
    assert plan.forecast(1050, 10, MON) == MON + timedelta(weeks=10)
    faster = plan.forecast(420, 15.7, MON)
    slower = plan.forecast(420, 11.7, MON)
    assert faster < slower
    assert plan.forecast(0, 0, MON) is None


@pytest.mark.parametrize("hours, phase", [(0, "1"), (74.9, "1"), (75, "2"), (449, "2"), (450, "3"), (800, "4"), (1000, "5"), (5000, "5")])
def test_phase_for_hours(hours, phase):
    assert plan.phase_for_hours(hours) == phase


def test_block_hours_per_week():
    assert round(plan.BLOCK_HOURS_PER_WEEK, 1) == 11.7


def test_immersion_totals():
    i = plan.immersion(300, 3600 * 15)
    assert i["hours"] == 315 and i["target"] == 1150
    assert i["share"] == round(315 / 1150, 3)
    assert plan.immersion(2000, 0)["share"] == 1.0


def test_combine_block_and_manual():
    by_day = plan.combine({"2026-10-12": 1800}, [
        {"local_date": "2026-10-12", "minutes": 25, "kind": "passiv"},
        {"local_date": "2026-10-13", "minutes": 10, "kind": "aktiv"},
    ])
    assert by_day == {"2026-10-12": {"aktiv": 1800, "passiv": 1500}, "2026-10-13": {"aktiv": 600, "passiv": 0}}


def test_weekly_hours_last_8_weeks():
    by_day = {"2026-10-12": {"aktiv": 7200, "passiv": 3600}, "2026-10-05": {"aktiv": 3600, "passiv": 0}}
    w = plan.weekly_hours(by_day, date(2026, 10, 14))
    assert len(w) == 8 and w[-1] == {"week": "2026-10-12", "aktiv": 2.0, "passiv": 1.0}
    assert w[-2]["aktiv"] == 1.0 and w[0]["aktiv"] == 0
