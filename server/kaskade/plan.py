"""Daily plan (weeks 1–4 for Phase 2A), block timer totals and immersion hours."""
import json
from datetime import date, datetime, timedelta
from functools import lru_cache

from . import config

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
HOURS_TO_B2 = 1150          # Refold estimate
MAX_SESSION = 3 * 3600      # a forgotten timer counts at most 3 h


# Phase-specific plans; anything else (1, 2A, unknown) uses weeks 1–4.
PHASE_FILES = {"2B": "plan/phase-2b.json"}


def _load(name: str) -> dict:
    return json.loads((config.CONTENT_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def plan(phase: str | None = None) -> dict:
    """The plan for `phase`. Exam prompts and week 6 are shared, so a phase file only
    brings its own block and weeks."""
    base = _load("plan/weeks-1-4.json")
    name = PHASE_FILES.get(phase or "")
    if not name:
        return base
    return {"prompts": base["prompts"], **_load(name)}


def block_ids() -> set[str]:
    return {b["id"] for p in (None, *PHASE_FILES) for b in plan(p)["block"]}


def default_start(today: date) -> date:
    """Monday of this week if it's Mon–Wed, otherwise next Monday (don't start a plan on a Friday)."""
    monday = today - timedelta(days=today.weekday())
    return monday if today.weekday() <= 2 else monday + timedelta(days=7)


# ── Weeks off (#36) ──────────────────────────────────────────────────────────
# A pause is a run of whole Mon–Sun weeks ({"from": Monday, "to": Sunday}, setting `pauses`). The
# plan doesn't happen in them: every date derived from the plan start skips them, so the week after
# a pause is the plan week that would have been in it.

def pauses() -> list[dict]:
    """The weeks off as stored (the plan functions below take them as an argument)."""
    from . import db
    return db.get_setting("pauses", [])


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weeks_off(start: date, pauses=()) -> list[int]:
    """The calendar weeks he took off, counted from the week of `start` (0), sorted."""
    off = set()
    for p in pauses or ():
        a, b = monday(date.fromisoformat(p["from"])), date.fromisoformat(p["to"])
        while a <= b:
            if a >= start:
                off.add((a - start).days // 7)
            a += timedelta(weeks=1)
    return sorted(off)


def slot_date(start: date, week: int, weekday: int, pauses=()) -> date:
    """The calendar date of plan week `week` (0-based), weekday `weekday` — after the weeks off."""
    k = week
    for p in weeks_off(start, pauses):
        if p <= k:
            k += 1
    return start + timedelta(weeks=k, days=weekday)


def plan_index(start: date, day: date, pauses=()) -> tuple[int, bool]:
    """(plan week of `day`, 0-based; paused?). In a week off: the plan week that comes after it."""
    k = (day - start).days // 7
    off = weeks_off(start, pauses)
    return k - sum(p < k for p in off), k in off


def pause_around(start: date, day: date, pauses=()) -> dict | None:
    """The run of weeks off `day` lies in: {from, to, resume} (ISO dates), else None."""
    off = set(weeks_off(start, pauses))
    k = (day - start).days // 7
    if k not in off:
        return None
    a = k
    while a - 1 in off:
        a -= 1
    b = k
    while b + 1 in off:
        b += 1
    first, resume = start + timedelta(weeks=a), start + timedelta(weeks=b + 1)
    return {"from": first.isoformat(), "to": (resume - timedelta(days=1)).isoformat(), "resume": resume.isoformat()}


def paused_days(days: list[str], start: date, pauses=()) -> list[bool]:
    """For each ISO date: in a week off? (the hours chart shows those days as "frei")."""
    off = set(weeks_off(start, pauses))
    return [(date.fromisoformat(d) - start).days // 7 in off and date.fromisoformat(d) >= start for d in days]


def plan_day(start: date, today: date, data: dict | None = None, pauses=()) -> dict:
    """Which plan week/day `today` is, relative to the Monday `start` and the weeks off (#36)."""
    data = data or plan()
    offset = (today - start).days
    index, paused = plan_index(start, today, pauses)
    week = index + 1 if offset >= 0 else 0
    weekday = today.weekday()
    out = {"date": today.isoformat(), "weekday": WEEKDAYS[weekday], "week": week,
           "weekend": weekday >= 5, "beforeStart": offset < 0, "day": None, "theme": None,
           "goal": None, "exam": None, "mockExam": None, "pause": None,
           # week 5 to-dos (e.g. set up the AI key before the week-6 mock exam), also on its weekend
           "todos": data.get(f"week{week}", {}).get("todos", []) if week == 5 and not paused else []}
    if paused:  # a week off: no block, the next plan week comes after it
        out["pause"] = pause_around(start, today, pauses)
        return out
    if offset < 0 or weekday >= 5:
        return out
    weeks = data["weeks"]
    w = weeks[(week - 1) % len(weeks)]  # after week 4 the cycle repeats
    day = w["days"][weekday]
    out.update(day=day, theme=w["theme"], goal=w["goal"])
    if week == 6 and data.get("week6"):  # #27: no mock exam while there is no exam date
        out["mockExam"] = data["week6"]
    elif day.get("exam"):
        out["exam"] = next(p for p in data["prompts"] if p["id"] == day["exam"])
    if week > len(weeks):
        out["repeat"] = True
    return out


def upcoming(start: date, data: dict, pauses=()) -> list[dict]:
    """Fahrplan "next steps": week-5 to-dos and the week-6 mock exam, with their dates."""
    out = [{"week": 5, "date": slot_date(start, 4, 0, pauses).isoformat(), "id": t["id"], "title": t["title"],
            "text": t["text"], "doneWhen": t.get("doneWhen")} for t in data.get("week5", {}).get("todos", [])]
    if data.get("week6"):
        out.append({"week": 6, "date": slot_date(start, 5, 0, pauses).isoformat(), "id": "mock-exam",
                    "title": data["week6"]["title"], "text": data["week6"]["note"], "doneWhen": None})
    return out


def session_seconds(started: datetime, ended: datetime | None, now: datetime) -> int:
    end = ended or now
    return int(max(0, min(MAX_SESSION, (end - started).total_seconds())))


def totals_by_day(rows: list[dict], now: datetime) -> dict[str, int]:
    """rows: [{local_date, started_at, ended_at, seconds}] → seconds per local date."""
    out: dict[str, int] = {}
    for r in rows:
        secs = r["seconds"] if r.get("ended_at") else session_seconds(
            datetime.fromisoformat(r["started_at"]), None, now)
        out[r["local_date"]] = out.get(r["local_date"], 0) + secs
    return out


def combine(block_by_day: dict[str, int], manual: list[dict]) -> dict[str, dict[str, int]]:
    """Block-timer seconds (always active) + manual log entries → {date: {aktiv, passiv}} in seconds."""
    out: dict[str, dict[str, int]] = {}
    for day, secs in block_by_day.items():
        out.setdefault(day, {"aktiv": 0, "passiv": 0})["aktiv"] += secs
    for m in manual:
        out.setdefault(m["local_date"], {"aktiv": 0, "passiv": 0})[m["kind"]] += m["minutes"] * 60
    return out


def weekly_hours(by_day: dict[str, dict[str, int]], today: date, weeks: int = 8) -> list[dict]:
    """Active/passive hours per ISO week for the last `weeks` weeks (oldest first)."""
    monday = today - timedelta(days=today.weekday())
    out = []
    for w in range(weeks - 1, -1, -1):
        start = monday - timedelta(weeks=w)
        days = [(start + timedelta(days=i)).isoformat() for i in range(7)]
        a = sum(by_day.get(d, {}).get("aktiv", 0) for d in days) / 3600
        p = sum(by_day.get(d, {}).get("passiv", 0) for d in days) / 3600
        out.append({"week": start.isoformat(), "aktiv": round(a, 2), "passiv": round(p, 2)})
    return out


def week_days(today: date) -> list[str]:
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=i)).isoformat() for i in range(7)]


BLOCK_HOURS_PER_WEEK = 5 * 140 / 60          # 2 h 20 min active, Mo–Fr = 11.7 h
PASSIVE_HOURS_PER_WEEK = 5 * 48 / 60         # + 48 min passive listening, Mo–Fr
PHASES = [("1", 0, 75), ("2", 75, 450), ("3", 450, 750), ("4", 750, 900), ("5", 900, HOURS_TO_B2)]


def forecast(hours: float, per_week: float, today: date) -> date | None:
    """Date when `hours` reaches the B2 estimate at `per_week` hours per week."""
    if per_week <= 0:
        return None
    left = max(0.0, HOURS_TO_B2 - hours)
    return today + timedelta(weeks=left / per_week)


def phase_for_hours(hours: float) -> str:
    for name, lo, hi in PHASES:
        if lo <= hours < hi:
            return name
    return "5"


def immersion(start_hours: float, logged_seconds: int) -> dict:
    hours = start_hours + logged_seconds / 3600
    return {"hours": round(hours, 1), "target": HOURS_TO_B2, "share": round(min(1.0, hours / HOURS_TO_B2), 3)}
