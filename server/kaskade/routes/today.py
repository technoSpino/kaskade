import datetime as dt
import json
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import config, db, materials, plan, ratings, srs, stock, texts
from .media import last_clip
from .ratings import annotate, book_modes
from .satzcheck import mineable_lines, run_result
from .texts import read_ids

router = APIRouter(prefix="/api")


def _today() -> date:
    return srs.now_utc().astimezone(srs.TZ).date()


def plan_start(today: date) -> date:
    s = db.get_setting("planStart")
    if not s:
        s = plan.default_start(today).isoformat()
        db.set_setting("planStart", s)
    return date.fromisoformat(s)


def current_timer(conn, now: datetime):
    """The running block timer — not one forgotten for longer than a session can count (3 h): it
    stopped counting there (plan.MAX_SESSION), so it isn't shown as running any more (#36)."""
    r = conn.execute("SELECT block, started_at FROM activity WHERE ended_at IS NULL").fetchone()
    if r and (now - datetime.fromisoformat(r["started_at"])).total_seconds() >= plan.MAX_SESSION:
        return None
    return r


WEEKDAY = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _dm(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WEEKDAY[d.weekday()]} {d.day}.{d.month}."


def _resume_with(it: dict | None) -> str | None:
    """"SOKO Leipzig ab 21:54": the first thing of the day after a week off."""
    if not it or it.get("kind") == "none":
        return None
    name = (it.get("title") or "").split(":")[0].strip()
    frm = (it.get("range") or [0])[0] or 0
    return f"{name} ab {materials.clock(frm)}" if it.get("kind") in ("clip", "satzcheck") and frm > 5 else name or None


def pause_line(pause: dict, first: dict | None) -> str:
    """#36: Heute's one line in a week off."""
    weeks = (date.fromisoformat(pause["resume"]) - date.fromisoformat(pause["from"])).days // 7
    what = _resume_with(first)
    return (f"{'Freie Woche' if weeks == 1 else f'{weeks} freie Wochen'} bis {_dm(pause['to'])} — weiter am "
            f"{_dm(pause['resume'])}{f' mit {what}' if what else ''}.")


def _manual_rows(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT id, local_date, minutes, kind, title FROM immersion_log")]


def combined_by_day(conn, now) -> dict[str, dict[str, int]]:
    """All immersion per local date: block timers (aktiv) + manual log (aktiv/passiv), in seconds."""
    return plan.combine(plan.totals_by_day(_activity_rows(conn), now), _manual_rows(conn))


def _activity_rows(conn, since: str | None = None):
    q = "SELECT local_date, block, started_at, ended_at, seconds FROM activity"
    rows = conn.execute(q + (" WHERE local_date >= ?" if since else ""), (since,) if since else ()).fetchall()
    return [dict(r) for r in rows]


def _todo_done(todo: dict) -> bool:
    """Ticked off by hand, or done by itself (the AI key is set → /api/health says ai: true)."""
    if todo.get("doneWhen") == "ai" and config.anthropic_key():
        return True
    return todo["id"] in db.get_setting("todosDone", [])


@router.get("/today")
def today(today: dt.date | None = None, phase: str | None = None):
    """Heute. `today`/`phase` show another day or plan (as /api/materials; drives the E2E for #20)."""
    if phase is not None and phase not in PHASES:
        raise HTTPException(422, "Unbekannte Phase")
    now = srs.now_utc()
    d = today or _today()
    data = plan.plan(phase or db.get_setting("phase"))
    pauses = plan.pauses()
    info = plan.plan_day(plan_start(d), d, data, pauses)
    if info["day"] is None:
        # Weekend, a week off (#36) or before the start: show the next plan day as a preview.
        nxt, _ = materials.next_plan_day(plan_start(d), max(plan_start(d) - timedelta(days=1), d), data, pauses)
        info["preview"] = plan.plan_day(plan_start(d), nxt, data, pauses)
    info["todos"] = [t for t in info["todos"] if not _todo_done(t)]
    # #16: the exact thing each block of the shown day (today, else the preview day) is about
    shown = info if info["day"] else info["preview"]
    ctx = materials.Ctx(d, now)
    ctx.live = today is None and phase is None
    assignments = {it["block"]: it for it in materials.day_items(shown, ctx, data, plan_start(d))}
    if info["pause"]:
        # #36: one calm line instead of the block — with what the Schauen block goes on with
        info["pause"]["line"] = pause_line(info["pause"], assignments.get("input"))
        assignments = {}
    days = plan.week_days(d)
    with db.tx() as conn:
        week_rows = _activity_rows(conn, days[0])
        by_day = combined_by_day(conn, now)
        done = {r[0] for r in conn.execute("SELECT block FROM plan_done WHERE local_date = ?", (d.isoformat(),))}
        running = current_timer(conn, now)
        placement = conn.execute(
            "SELECT result FROM placements WHERE status = 'done' ORDER BY id DESC LIMIT 1").fetchone()
        last_sc = conn.execute(
            "SELECT created_at, content_type, ratings, result FROM satzcheck_runs ORDER BY id DESC LIMIT 1").fetchone()
        vocab = conn.execute("SELECT result FROM vocab_tests ORDER BY id DESC LIMIT 1").fetchone()

    per_block: dict[str, int] = {}
    for r in week_rows:
        if r["local_date"] == d.isoformat():
            secs = r["seconds"] if r["ended_at"] else 0
            per_block[r["block"]] = per_block.get(r["block"], 0) + secs
    total = sum(v["aktiv"] + v["passiv"] for v in by_day.values())
    start_hours = db.get_setting("startHours", 150)
    p = json.loads(placement["result"]) if placement else None
    if info["day"] and d == _today():  # #23: "Wie viel hast du verstanden?" once a block is done or stopped
        worked = {r["block"] for r in week_rows if r["local_date"] == d.isoformat()}
        annotate(assignments, d, done, running["block"] if running else None, worked)

    return {
        **info,
        "name": db.get_setting("name", "Matt"),
        "phase": db.get_setting("phase"),
        "planStart": plan_start(d).isoformat(),
        "block": data["block"],
        "planPhase": data["phase"],
        "blockSeconds": per_block,
        "done": sorted(done),
        "running": {"block": running["block"], "startedAt": running["started_at"]} if running else None,
        "weekTotals": {
            "days": days,
            "seconds": [by_day.get(x, {}).get("aktiv", 0) for x in days],
            "passive": [by_day.get(x, {}).get("passiv", 0) for x in days],
            "free": plan.paused_days(days, plan_start(d), pauses),  # #36: a week off is "frei", not missed
        },
        "immersion": plan.immersion(start_hours, total),
        "placement": p,
        "satzcheck": {"createdAt": last_sc["created_at"], **run_result(last_sc)} if last_sc else None,
        "vocab": json.loads(vocab["result"]) if vocab else None,
        "cards": srs.stats(now),
        "texts": {slot: texts.next_unread(slot, set(read_ids())) for slot in ("input", "lesen")},
        "mineable": sum(1 for line in mineable_lines() if not line["mined"]),
        "watch": last_clip(),
        "assignments": assignments,
        "tooHard": [] if info["pause"] else ratings.too_hard(d, plan_start(d), data),
        "bookModes": book_modes(d, plan_start(d), data),
        "httpsUrl": config.HTTPS_URL,
    }


PHASES = {"1", "2A", "2B"}
EXAM_PAUSED = "B1-Prüfung: pausiert — kommt zurück, wenn du ein Prüfungsdatum wählst."


def _group(info: dict, kind: str, ctx, data: dict, start: date) -> dict:
    return {"date": info["date"], "weekday": info["weekday"], "week": info["week"], "kind": kind,
            "planDay": bool(info["day"]), "items": materials.day_items(info, ctx, data, start)}


@router.get("/materials")
def get_materials(today: dt.date | None = None, phase: str | None = None):
    """Material für heute und morgen (#16). `today`/`phase` preview another day or plan (and drive the E2E)."""
    if phase is not None and phase not in PHASES:
        raise HTTPException(422, "Unbekannte Phase")
    d = today or _today()
    data = plan.plan(phase or db.get_setting("phase"))
    start = plan_start(_today())
    ctx = materials.Ctx(d)
    ctx.live = today is None and phase is None
    nxt, kind = materials.next_plan_day(start, d, data, ctx.pauses)
    check = materials.read_check()
    return {
        "today": _group(plan.plan_day(start, d, data, ctx.pauses), "today", ctx, data, start),
        "next": _group(plan.plan_day(start, nxt, data, ctx.pauses), kind, ctx, data, start),
        "notices": materials.notices(start, d, data, ctx),
        "httpsUrl": config.HTTPS_URL,
        "check": {"checkedAt": check.get("checkedAt"), "gaps": check.get("gaps", [])},
    }


class TickIn(BaseModel):
    done: bool = True


def _tick(setting: str, item_id: str, done: bool) -> list[str]:
    have = set(db.get_setting(setting, []))
    have = have | {item_id} if done else have - {item_id}
    db.set_setting(setting, sorted(have))
    return sorted(have)


@router.post("/books/{book_id}/bought")
def book_bought(book_id: str, body: TickIn):
    if not stock.book(book_id):
        raise HTTPException(404, "Unbekanntes Buch")
    _tick("booksBought", book_id, body.done)
    return {"id": book_id, "bought": body.done}


@router.post("/setup/{setup_id}")
def setup_done(setup_id: str, body: TickIn):
    if setup_id not in {s["id"] for s in stock.catalog().get("setup", [])}:
        raise HTTPException(404, "Unbekannte Einrichtung")
    _tick("setupDone", setup_id, body.done)
    return {"id": setup_id, "done": body.done}


@router.get("/fahrplan")
def fahrplan():
    now = srs.now_utc()
    d = _today()
    with db.tx() as conn:
        by_day = combined_by_day(conn, now)
        placements = conn.execute(
            "SELECT id, updated_at, result FROM placements WHERE status = 'done' ORDER BY id DESC").fetchall()
        checks = conn.execute(
            "SELECT created_at, content_type, ratings, result FROM satzcheck_runs ORDER BY id DESC LIMIT 12").fetchall()
    total = sum(v["aktiv"] + v["passiv"] for v in by_day.values())
    hours = plan.immersion(db.get_setting("startHours", 150), total)["hours"]
    # measured pace over the last 28 days (only once there is some data) — a week off counts as "frei",
    # not as a week with no hours (#36)
    since = (d - timedelta(days=28)).isoformat()
    window = [(d - timedelta(days=i)).isoformat() for i in range(28)]
    pauses = plan.pauses()
    worked_weeks = sum(not f for f in plan.paused_days(window, plan_start(d), pauses)) / 7
    recent = sum(v["aktiv"] + v["passiv"] for day, v in by_day.items() if day >= since) / 3600
    measured = recent / worked_weeks if recent >= 2 and worked_weeks >= 1 else None
    last_check = checks[0]["created_at"][:10] if checks else None
    data = plan.plan(db.get_setting("phase"))
    notices = materials.notices(plan_start(d), d, data, materials.Ctx(d, now))
    return {
        "hours": hours,
        "target": plan.HOURS_TO_B2,
        "phase": db.get_setting("phase"),
        "hoursPhase": plan.phase_for_hours(hours),
        "phases": [{"name": n, "from": lo, "to": hi} for n, lo, hi in plan.PHASES],
        "forecast": {
            "block": plan.forecast(hours, plan.BLOCK_HOURS_PER_WEEK, d).isoformat(),
            "blockPassive": plan.forecast(hours, plan.BLOCK_HOURS_PER_WEEK + plan.PASSIVE_HOURS_PER_WEEK, d).isoformat(),
            "measured": plan.forecast(hours, measured, d).isoformat() if measured else None,
            "measuredPerWeek": round(measured, 1) if measured else None,
            "blockPerWeek": round(plan.BLOCK_HOURS_PER_WEEK, 1),
        },
        "placements": [{"id": r["id"], "date": r["updated_at"], **json.loads(r["result"])} for r in placements],
        "satzchecks": [{"date": r["created_at"], "contentType": r["content_type"], **run_result(r)} for r in checks],
        "nextCheck": (date.fromisoformat(last_check) + timedelta(days=28)).isoformat() if last_check else None,
        "weeks": [{**w, "free": all(plan.paused_days(plan.week_days(date.fromisoformat(w["week"])), plan_start(d), pauses))}
                  for w in plan.weekly_hours(by_day, d)],
        "upcoming": [{**u, "done": u["id"] != "mock-exam" and _todo_done(u)}
                     for u in plan.upcoming(plan_start(d), data, pauses)],
        # books to buy and setup to do ahead of their first plan day (#16)
        "notices": notices,
        # #27: no exam date yet — the exam tasks stay in the app, just not in the plan
        "exam": EXAM_PAUSED,
        "today": d.isoformat(),
    }


class ImmersionIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    minutes: int = Field(ge=1, le=600)
    kind: Literal["aktiv", "passiv"]
    date: dt.date | None = None


@router.post("/immersion")
def add_immersion(body: ImmersionIn):
    day = body.date or _today()
    if day > _today():
        raise HTTPException(422, "Das Datum liegt in der Zukunft.")
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO immersion_log(created_at, local_date, minutes, kind, title) VALUES (?, ?, ?, ?, ?)",
            (db.now_iso(), day.isoformat(), body.minutes, body.kind, body.title.strip()))
        iid = cur.lastrowid
    return {"id": iid, "date": day.isoformat(), "minutes": body.minutes, "kind": body.kind, "title": body.title.strip()}


@router.get("/immersion")
def list_immersion(days: int = 30):
    since = (_today() - timedelta(days=days)).isoformat()
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT id, local_date, minutes, kind, title FROM immersion_log WHERE local_date >= ? ORDER BY local_date DESC, id DESC",
            (since,)).fetchall()
        by_day = combined_by_day(conn, srs.now_utc())
    return {
        "entries": [{"id": r["id"], "date": r["local_date"], "minutes": r["minutes"], "kind": r["kind"], "title": r["title"]} for r in rows],
        "weeks": plan.weekly_hours(by_day, _today()),
    }


@router.delete("/immersion/{iid}")
def delete_immersion(iid: int):
    with db.tx() as conn:
        n = conn.execute("DELETE FROM immersion_log WHERE id = ?", (iid,)).rowcount
    if not n:
        raise HTTPException(404, "Eintrag nicht gefunden")
    return {"ok": True}


class BlockIn(BaseModel):
    block: str


def _check_block(block: str):
    if block not in plan.block_ids() | {"extra"}:
        raise HTTPException(422, "Unbekannter Block")


def _stop_running(conn, now):
    for r in conn.execute("SELECT id, started_at FROM activity WHERE ended_at IS NULL").fetchall():
        secs = plan.session_seconds(datetime.fromisoformat(r["started_at"]), now, now)
        conn.execute("UPDATE activity SET ended_at = ?, seconds = ? WHERE id = ?", (now.isoformat(), secs, r["id"]))


@router.post("/activity/start")
def start(body: BlockIn):
    _check_block(body.block)
    now = srs.now_utc()
    with db.tx() as conn:
        _stop_running(conn, now)
        conn.execute("INSERT INTO activity(local_date, block, started_at) VALUES (?, ?, ?)",
                     (srs.local_date(now), body.block, now.isoformat()))
    return {"block": body.block, "startedAt": now.isoformat()}


@router.post("/activity/stop")
def stop():
    now = srs.now_utc()
    with db.tx() as conn:
        _stop_running(conn, now)
    return {"ok": True}


class DoneIn(BaseModel):
    block: str
    done: bool = True


@router.post("/plan/done")
def mark_done(body: DoneIn):
    _check_block(body.block)
    d = _today().isoformat()
    with db.tx() as conn:
        if body.done:
            conn.execute("INSERT OR IGNORE INTO plan_done(local_date, block) VALUES (?, ?)", (d, body.block))
        else:
            conn.execute("DELETE FROM plan_done WHERE local_date = ? AND block = ?", (d, body.block))
    return {"block": body.block, "done": body.done}


@router.get("/plan")
def full_plan():
    d = _today()
    data = plan.plan(db.get_setting("phase"))
    return {**data, "planStart": plan_start(d).isoformat(), "pauses": plan.pauses(),
            "today": plan.plan_day(plan_start(d), d, data, plan.pauses())}


@router.get("/plan/prompt/{prompt_id}")
def prompt(prompt_id: str):
    p = next((p for p in plan.plan()["prompts"] if p["id"] == prompt_id), None)
    if not p:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    return p


class StartIn(BaseModel):
    planStart: date


@router.put("/plan/start")
def set_start(body: StartIn):
    if body.planStart.weekday() != 0:
        raise HTTPException(422, "Der Plan beginnt immer an einem Montag.")
    db.set_setting("planStart", body.planStart.isoformat())
    return {"planStart": body.planStart.isoformat()}


class TodoIn(BaseModel):
    done: bool = True


@router.post("/todos/{todo_id}")
def tick_todo(todo_id: str, body: TodoIn):
    known = {t["id"] for t in plan.plan().get("week5", {}).get("todos", [])}
    if todo_id not in known:
        raise HTTPException(404, "Unbekannte Aufgabe")
    done = set(db.get_setting("todosDone", []))
    done = done | {todo_id} if body.done else done - {todo_id}
    db.set_setting("todosDone", sorted(done))
    return {"id": todo_id, "done": body.done}



# ── Weeks off (#36): "Woche frei nehmen" on the Fahrplan ─────────────────────

PAUSE_AHEAD = 8  # weeks offered, this one included


def _week_started(mon: date, d: date) -> bool:
    """Something of the plan done in that week up to today: a block timer, a ticked-off block, a rating.
    (Karten don't count — they stay open in a week off.)"""
    lo, hi = mon.isoformat(), min(d, mon + timedelta(days=6)).isoformat()
    with db.tx() as conn:
        return any(conn.execute(f"SELECT 1 FROM {t} WHERE local_date BETWEEN ? AND ? LIMIT 1", (lo, hi)).fetchone()
                   for t in ("activity", "plan_done", "ratings"))


def _pause_problem(mon: date, d: date, pauses: list[dict]) -> str | None:
    if mon.weekday() != 0:
        return "Eine freie Woche geht von Montag bis Sonntag."
    if mon < plan.monday(d):
        return "Diese Woche ist schon vorbei."
    if mon > plan.monday(d) + timedelta(weeks=PAUSE_AHEAD - 1):
        return f"Höchstens {PAUSE_AHEAD - 1} Wochen im Voraus."
    if any(p["from"] <= mon.isoformat() <= p["to"] for p in pauses):
        return "Diese Woche ist schon frei."
    if mon < plan_start(d):
        return f"Der Plan beginnt erst am {_dm(plan_start(d).isoformat())}."
    if mon <= d and _week_started(mon, d):
        return "In dieser Woche hast du schon gelernt — nimm eine spätere frei."
    return None


def _week(mon: date) -> dict:
    return {"from": mon.isoformat(), "to": (mon + timedelta(days=6)).isoformat()}


def _pauses_view(d: date) -> dict:
    pauses = plan.pauses()
    first = plan.monday(d)
    return {
        "pauses": [{**p, "canUndo": p["from"] > d.isoformat()} for p in sorted(pauses, key=lambda p: p["from"])],
        "options": [{**_week(m), "problem": _pause_problem(m, d, pauses)}
                    for m in (first + timedelta(weeks=i) for i in range(PAUSE_AHEAD))],
        "today": d.isoformat(),
    }


@router.get("/pauses")
def list_pauses():
    return _pauses_view(_today())


@router.get("/pauses/preview")
def pause_preview(monday: dt.date):
    """What a week off moves: the plan week in it and everything after, the due dates, where he goes on."""
    d = _today()
    current = plan.pauses()
    problem = _pause_problem(monday, d, current)
    if problem:
        raise HTTPException(422, problem)
    data = plan.plan(db.get_setting("phase"))
    start = plan_start(d)
    after = [*current, _week(monday)]
    k, _ = plan.plan_index(start, monday, current)
    resume = plan.slot_date(start, k, 0, after)
    ctx = materials.Ctx(d)
    ctx.live = False  # a preview never fixes a day's range
    before = {n["id"]: n for n in materials.notices(start, d, data, ctx)}
    ctx.pauses = after
    moved = materials.notices(start, d, data, ctx)
    resume_day = plan.plan_day(start, resume, data, after)
    first = next((it for it in materials.day_items(resume_day, ctx, data, start) if it["block"] == "input"), None)
    w = data["weeks"][k % len(data["weeks"])]
    return {
        "from": monday.isoformat(), "to": (monday + timedelta(days=6)).isoformat(), "resume": resume.isoformat(),
        "week": {"n": k + 1, "theme": w["theme"], "was": monday.isoformat(), "now": resume.isoformat()},
        "line": pause_line({"from": monday.isoformat(), "to": (resume - timedelta(days=1)).isoformat(),
                            "resume": resume.isoformat()}, first),
        "due": [{"id": n["id"], "title": n["title"], "was": before[n["id"]]["by"], "now": n["by"]}
                for n in moved if n["id"] in before and before[n["id"]]["by"] != n["by"]],
    }


class PauseIn(BaseModel):
    monday: date


@router.post("/pauses")
def add_pause(body: PauseIn):
    """Take a Mon–Sun week off. The ranges Heute fixed for its days (before anything was done) go away."""
    d = _today()
    pauses = plan.pauses()
    problem = _pause_problem(body.monday, d, pauses)
    if problem:
        raise HTTPException(422, problem)
    week = _week(body.monday)
    db.set_setting("pauses", sorted([*pauses, week], key=lambda p: p["from"]))
    with db.tx() as conn:
        conn.execute("DELETE FROM watch_ranges WHERE local_date BETWEEN ? AND ? AND NOT EXISTS (SELECT 1 FROM activity a"
                     " WHERE a.local_date = watch_ranges.local_date AND a.block = watch_ranges.block)",
                     (week["from"], week["to"]))
    return _pauses_view(d)


@router.delete("/pauses/{monday}")
def undo_pause(monday: dt.date):
    """Undo a week off — only while it hasn't started."""
    d = _today()
    pauses = plan.pauses()
    if not any(p["from"] == monday.isoformat() for p in pauses):
        raise HTTPException(404, "Keine freie Woche ab diesem Tag")
    if monday <= d:
        raise HTTPException(409, "Die freie Woche hat schon begonnen.")
    db.set_setting("pauses", [p for p in pauses if p["from"] != monday.isoformat()])
    return _pauses_view(d)
