"""Fill a THROWAWAY Kaskade data dir with a realistic demo profile (for screenshots/QA).

    KASKADE_DATA_DIR=/path/to/throwaway KASKADE_NOW=2026-10-13T07:30:00+00:00 \\
        .venv/bin/python scripts/seed_demo.py

Profile: placement done → phase 2B, ~50 cards learned + 30 sorted out with K, a week of
block time and some logged series/podcasts, one Satz-Check, a few practice attempts.
All text is original. Refuses to touch the real ~/kaskade-data.
"""
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaskade import config, db, srs  # noqa: E402

if config.DATA_DIR.resolve() == (Path.home() / "kaskade-data").resolve():
    sys.exit("seed_demo.py only runs on a throwaway KASKADE_DATA_DIR, never on ~/kaskade-data.")

config.ensure_dirs()
db.init()
now = srs.now_utc()
today = now.astimezone(srs.TZ).date()
monday = today - timedelta(days=today.weekday())
iso = lambda d: d.isoformat()  # noqa: E731

VOCAB = {"bands": [
    {"id": "b1", "from": 1, "to": 500, "n": 20, "hits": 1.0, "corrected": 1.0, "known": 485},
    {"id": "b2", "from": 501, "to": 1000, "n": 20, "hits": 0.9, "corrected": 0.88, "known": 440},
    {"id": "b3", "from": 1001, "to": 2000, "n": 20, "hits": 0.8, "corrected": 0.78, "known": 780},
    {"id": "b4", "from": 2001, "to": 4000, "n": 20, "hits": 0.55, "corrected": 0.52, "known": 1040},
    {"id": "b5", "from": 4001, "to": 8000, "n": 20, "hits": 0.25, "corrected": 0.2, "known": 800}],
    "falseAlarmRate": 0.05, "reliable": True, "estimate": 3550, "coreShare": 0.85, "coreKnown": 1700}
VERDICT = {"phase": "2B", "key": "ready-2b", "title": "Bereit für Phase 2B",
           "advice": "Ab jetzt Sätze aus echten Serien minen. Die Kernwörter laufen nur noch nebenbei."}
PLACEMENT = {"phase": "2B", "words": 3550, "coreKnown": 1700, "coreShare": 0.85,
             "satzcheck": {"coverage": 82, "verdict": VERDICT}, "startHours": 350,
             "skills": {"lesen": "B1", "hoeren": "B1", "schreiben": "A2+", "sprechen": "A2"}, "notes": {}}
# Original demo lines (not from any series).
LINES = [("Wo waren Sie gestern zwischen acht und zehn?", "v"), ("Zu Hause. Allein.", "v"),
         ("Das kann ja jeder sagen.", "h"), ("Na und?", "s"), ("Ich hab doch nichts gemacht!", "v"),
         ("Kommen Sie mal mit aufs Revier.", "h"), ("Jetzt mal ganz ruhig.", "v"), ("Wer's glaubt …", "s"),
         ("Wir haben Ihre Fingerabdrücke auf dem Glas gefunden.", "h"), ("Das war vorher!", "v")]

with db.tx() as conn:
    conn.execute("INSERT INTO vocab_tests(created_at, answers, result) VALUES (?, '[]', ?)",
                 (iso(now - timedelta(days=4)), json.dumps(VOCAB)))
    conn.execute("INSERT INTO placements(created_at, updated_at, status, state, result) VALUES (?, ?, 'done', '{}', ?)",
                 (iso(now - timedelta(days=4)), iso(now - timedelta(days=4)), json.dumps(PLACEMENT, ensure_ascii=False)))
    ratings = [{"cue": i + 1, "text": t, "rating": r} for i, (t, r) in enumerate(LINES)]
    v, h, s = (sum(1 for _, r in LINES if r == x) for x in "vhs")
    conn.execute(
        "INSERT INTO satzcheck_runs(created_at, media_id, content_type, window_start, window_end, ratings, result)"
        " VALUES (?, NULL, 'adult', 0, 180, ?, ?)",
        (iso(now - timedelta(days=4)), json.dumps(ratings, ensure_ascii=False),
         json.dumps({"v": v, "h": h, "s": s, "rated": len(LINES), "coverage": round((v + h) / len(LINES) * 100),
                     "words": 3550, "verdict": VERDICT}, ensure_ascii=False)))

    # Block time: all of Monday, Karten done today; last week a bit less.
    blocks = [("karten", 15), ("input", 65), ("lesen", 35), ("pruefung", 25)]
    days = [(monday, blocks, True), (today, blocks[:1], True)]
    days += [(monday - timedelta(days=7 - i), blocks[: 2 + i % 3], False) for i in range(5)]
    for d, bl, done in days:
        if d > today:
            continue
        for b, mins in bl:
            start = f"{iso(d)}T07:00:00+00:00"
            conn.execute("INSERT INTO activity(local_date, block, started_at, ended_at, seconds) VALUES (?, ?, ?, ?, ?)",
                         (iso(d), b, start, start, mins * 60))
            if done:
                conn.execute("INSERT OR IGNORE INTO plan_done(local_date, block) VALUES (?, ?)", (iso(d), b))
    for d, mins, kind, title in [(monday - timedelta(days=2), 90, "passiv", "Tatort am Sonntagabend"),
                                 (monday - timedelta(days=5), 40, "passiv", "Easy German Podcast"),
                                 (monday, 30, "passiv", "Podcast beim Spazierengehen"),
                                 (monday - timedelta(days=3), 45, "aktiv", "Babylon Berlin mit Untertiteln")]:
        conn.execute("INSERT INTO immersion_log(created_at, local_date, minutes, kind, title) VALUES (?, ?, ?, ?, ?)",
                     (iso(now), iso(d), mins, kind, title))
    for module, item, pts, total in [("lesen", "l1", 7, 10), ("hoeren", "h1", 4, 6), ("lesen", "l2", 5, 8)]:
        conn.execute("INSERT INTO practice_attempts(created_at, module, item_id, points, total, timed) VALUES (?, ?, ?, ?, ?, 0)",
                     (iso(now - timedelta(days=1)), module, item, pts, total))

db.set_setting("phase", "2B")
db.set_setting("startHours", 350)

# Cards: 30 sorted out with K, 50 learned over the last days (a few due today).
ids = [c["id"] for c in srs.deck()]
for cid in ids[:30]:
    srs.mark_known(cid, now - timedelta(days=3))
for n, cid in enumerate(ids[30:80]):
    srs.review(cid, 3 if n % 5 else 2, now - timedelta(days=1 + n % 4, hours=1))

print(f"seeded demo profile in {config.DATA_DIR}")
