"""#42: a part he watched stays watched — his place in a clip is the furthest point he played."""
from datetime import date, timedelta
from types import SimpleNamespace

from kaskade import db, plan, rolling, stock, transcripts
from kaskade.routes.media import furthest_after

MON = date(2026, 10, 12)  # plan 2B: Quarks on Thu 29.10. and Fri 30.10., Wunderschön! Nordeifel from Mon 2.11.
QUARKS_END = 2675.86  # the video's real length (the plan says 44:36 = 2676)
SRT = b"1\n00:00:01,000 --> 00:00:03,000\nGuten Abend.\n\n2\n00:44:30,000 --> 00:44:35,000\nBis zum n\xc3\xa4chsten Mal.\n"


def quarks(client) -> int:
    r = client.post("/api/media/upload", files={"subtitles": ("q.srt", SRT, "application/x-subrip")}, data={"title": "Quarks (Test)"})
    assert r.status_code == 200, r.text
    mid = r.json()["id"]
    with db.tx() as conn:
        conn.execute("UPDATE media SET key = 'quarks-schlaf', duration = ? WHERE id = ?", (QUARKS_END, mid))
    return mid


def save(client, mid, *positions, **kw):
    for p in positions:
        assert client.put(f"/api/media/{mid}/progress", json={"position": p, **kw}).status_code == 200


def furthest(mid):
    with db.tx() as conn:
        return conn.execute("SELECT furthest FROM media_progress WHERE media_id = ?", (mid,)).fetchone()[0]


def ctx(today, mid, live=False):
    """Every input clip before Quarks watched to its end; Quarks is the uploaded clip."""
    keys = [s["m"]["clip"] for s in rolling.slots(MON, plan.plan("2B"), "input") if rolling.rolls(s["m"])]
    lib, positions = {}, {}
    for i, k in enumerate(dict.fromkeys(keys), 1000):
        if k == "quarks-schlaf":
            lib[k] = {"id": mid, "duration": QUARKS_END}
            continue
        lib[k] = {"id": i, "duration": (stock.item(k) or {}).get("duration") or 3000}
        if keys.index(k) < keys.index("quarks-schlaf"):
            positions[i] = float("inf")
    positions.update({k: v for k, v in rolling.positions().items() if k == mid})
    return SimpleNamespace(today=today, real_today=today, live=live, lib=lib, positions=positions)


def test_the_last_part_ends_at_the_clips_real_end_never_after_it():
    frm, to, final = rolling.day_range(1329, QUARKS_END, 2059, [])
    assert final and to <= QUARKS_END and (frm, to) == (1329, 2675)  # Friday's was 2676: never "reached"
    assert rolling.day_range(0, 1800, 1500, []) == (0, 1800, True)


def test_fridays_saves_leave_quarks_finished_and_the_next_day_is_the_next_clip(client):
    """Fr 13.11.: 22:09 → the end, then play on the ended video (3.56), 8.0, "Zurück zu 22:09" (1329.0)."""
    mid = quarks(client)
    save(client, mid, 1329.01, *range(1339, 2675, 10), 2675.84)  # watched to the end, a save every 10 s
    save(client, mid, 3.56, reason="jump", **{"from": 2675.84})
    save(client, mid, 8.0, 1329.0)
    assert client.get(f"/api/media/{mid}").json()["position"] == 1329.0  # where he last was (Schauen resumes there)
    assert furthest(mid) == 2675.84 and rolling.positions()[mid] == 2675.84  # how far he got
    assert not transcripts.in_progress(mid)  # finished: #35 no longer holds its lines

    # Friday's range, then Monday: the next clip from its start, and Friday's pace sample is what he watched
    fri, mon = date(2026, 10, 30), date(2026, 11, 2)
    with db.tx() as conn:
        conn.execute("INSERT INTO watch_ranges(local_date, block, clip, start, end, clean) VALUES (?, 'input', 'quarks-schlaf', 1329, 2675, 1)",
                     (fri.isoformat(),))
    out = rolling.plan_block("input", plan.plan("2B"), MON, ctx(mon, mid, live=True))
    assert (out[mon]["clip"], out[mon]["from"]) == ("wunderschoen-nordeifel", 0)
    with db.tx() as conn:
        assert conn.execute("SELECT reached FROM watch_ranges WHERE local_date = ?", (fri.isoformat(),)).fetchone()[0] == 2675.84


def test_without_furthest_the_last_save_would_have_sent_him_back(client):
    """The same day computed from the last save alone (before #42): Quarks 22:09 again."""
    mid = quarks(client)
    mon = date(2026, 11, 2)
    c = ctx(mon, mid)
    c.positions[mid] = 1329.0
    assert (lambda r: (r["clip"], r["from"]))(rolling.plan_block("input", plan.plan("2B"), MON, c)[mon]) == ("quarks-schlaf", 1329)


def test_a_forward_seek_alone_doesnt_raise_furthest(client):
    mid = quarks(client)
    save(client, mid, 0.5, 10, 20, *range(30, 301, 10))  # played to 5:00
    assert furthest(mid) == 300
    save(client, mid, 2000)  # a seek to 33:20, no play after it
    assert furthest(mid) == 300
    assert rolling.positions()[mid] == 2000  # where he is now still counts while he stays there …
    save(client, mid, 120, reason="jump", **{"from": 2000})
    assert rolling.positions()[mid] == 300  # … but going back from it never pulls the plan before 5:00


def test_a_save_600_s_back_leaves_furthest_and_playing_on_past_it_raises_it(client):
    mid = quarks(client)
    save(client, mid, *range(10, 1201, 10))
    save(client, mid, 600, 610, 620)  # back 10 minutes to watch a scene again
    assert furthest(mid) == 1200 and rolling.positions()[mid] == 1200
    save(client, mid, *range(630, 1231, 10))
    assert furthest(mid) == 1230


def test_furthest_after():
    assert furthest_after(None, None, 8.0) == 8.0          # the first save, from the start
    assert furthest_after(None, None, 1329.0) == 0          # the first save after a seek: not played
    assert furthest_after(2665.0, 2665.0, 2675.84) == 2675.84
    assert furthest_after(2675.84, 2675.84, 3.56) == 2675.84
    assert furthest_after(3.56, 2675.84, 8.0) == 2675.84
    assert furthest_after(500.0, None, 510.0) == 510.0      # a row from before #42 (no furthest yet): its position
    assert furthest_after(500.0, None, 100.0) == 500.0


def test_rows_from_before_42_start_with_their_position(client):
    with db.tx() as conn:
        conn.execute("INSERT INTO media_progress(media_id, position, updated_at) VALUES (77, 1482.22, '2026-11-05')")
    db.init()
    assert furthest(77) == 1482.22
    assert rolling.positions()[77] == 1482.22
