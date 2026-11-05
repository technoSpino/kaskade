"""Schauen & minen: resume positions, last clip, mining a subtitle line with an audio snippet."""
import logging
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from kaskade import config, db, snippet, srs

SRT = b"""1
00:00:00,500 --> 00:00:02,000
Wo waren Sie gestern Abend?

2
00:00:02,500 --> 00:00:04,000
[Telefon klingelt]

3
00:00:04,500 --> 00:00:06,000
Das glaube ich Ihnen nicht.
"""

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def make_clip(tmp_path):
    out = tmp_path / "clip.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=7",
                    "-c:a", "libopus", str(out)], check=True)
    return out


def upload(client, media=None, title="Krimi"):
    files = {"subtitles": ("t.srt", SRT, "application/x-subrip")}
    if media:
        files["media"] = (media.name, media.read_bytes(), "video/webm")
    r = client.post("/api/media/upload", files=files, data={"title": title})
    assert r.status_code == 200, r.text
    return r.json()


def test_snippet_window_pads_and_caps():
    assert snippet.window(10.0, 12.0) == (9.75, 12.35)
    assert snippet.window(0.1, 1.0)[0] == 0.0
    a, b = snippet.window(5.0, 60.0)
    assert b - a == snippet.MAX_SECONDS


def test_progress_and_last_clip(client):
    assert client.get("/api/media/last").json() is None
    first = upload(client, title="Ohne Video")
    assert client.get("/api/media/last").json() is None  # needs a media file
    assert client.put(f"/api/media/{first['id']}/progress", json={"position": 3.2}).json()["position"] == 3.2
    assert client.get(f"/api/media/{first['id']}").json()["position"] == 3.2
    assert client.put("/api/media/999/progress", json={"position": 1}).status_code == 404
    assert client.put(f"/api/media/{first['id']}/progress", json={"position": -1}).status_code == 422


def test_every_saved_position_is_logged_and_a_jump_back_is_a_warning(client, caplog):
    """#30: old → new at INFO; a jump back he didn't choose comes with reason + from and is a WARNING."""
    m = upload(client, title="Lang")
    with caplog.at_level(logging.INFO, logger="kaskade"):
        client.put(f"/api/media/{m['id']}/progress", json={"position": 3746})
        client.put(f"/api/media/{m['id']}/progress", json={"position": 6.854, "reason": "jump", "from": 3746})
    logged = [(r.levelname, r.getMessage()) for r in caplog.records if r.name == "kaskade.routes.media"]
    assert logged == [("INFO", f"position media {m['id']}: None → 3746.0"),
                      ("WARNING", f"position media {m['id']}: jumped back from 3746.0 to 6.85 (saved before: 3746.0)")]
    assert client.get(f"/api/media/{m['id']}").json()["position"] == 6.85
    assert client.put(f"/api/media/{m['id']}/progress", json={"position": 1, "reason": "oops"}).status_code == 422


def test_the_clip_says_how_far_its_last_plan_range_got(client):
    """#30: Starten must not trust a position that went backwards after yesterday's part was reached."""
    m = upload(client, title="Lang")
    other = upload(client, title="Ohne Plan")
    today = date.fromisoformat(srs.local_date(srs.now_utc()))
    with db.tx() as conn:
        conn.execute("UPDATE media SET key = 'e2e-lang' WHERE id = ?", (m["id"],))
        for day, start, end, reached in [(today - timedelta(days=2), 430, 2046, 2046.01), (today - timedelta(days=1), 2046, 3746, 3746.0),
                                          (today, 3746, 5361, None)]:
            conn.execute("INSERT INTO watch_ranges(local_date, block, clip, start, end, clean, reached) VALUES (?, 'input', 'e2e-lang', ?, ?, 1, ?)",
                         (day.isoformat(), start, end, reached))
    assert client.get(f"/api/media/{m['id']}").json()["rangeReached"] == 3746.0  # yesterday's, not today's (open)
    assert client.get(f"/api/media/{other['id']}").json()["rangeReached"] is None


@needs_ffmpeg
def test_last_clip_prefers_the_one_watched_most_recently(client, tmp_path):
    clip = make_clip(tmp_path)
    a = upload(client, clip, "A")
    b = upload(client, clip, "B")
    assert client.get("/api/media/last").json()["id"] == b["id"]  # newest
    client.put(f"/api/media/{a['id']}/progress", json={"position": 4.5})
    last = client.get("/api/media/last").json()
    assert last["id"] == a["id"] and last["position"] == 4.5
    assert client.get("/api/today").json()["watch"]["id"] == a["id"]


@needs_ffmpeg
def test_mine_a_line_with_audio_snippet(client, tmp_path):
    m = upload(client, make_clip(tmp_path))
    r = client.post("/api/mined", json={
        "sentence": "Das glaube ich Ihnen nicht.", "target": "glaube", "lemma": "glauben", "gloss": "believe",
        "source": "Schauen · Krimi", "mediaId": m["id"], "start": 4.5, "end": 6.0}).json()
    assert r["audio"] is True and r["duplicate"] is False
    assert (config.SNIPPETS_DIR / "mine-1.m4a").stat().st_size > 0
    audio = client.get(f"/api/cards/{r['id']}/audio")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mp4"
    card = next(c for c in client.get("/api/mined").json() if c["id"] == r["id"])
    assert card["mediaId"] == m["id"] and card["clipStart"] == 4.5
    # it is a new card in Karten, mined cards first
    assert client.get("/api/cards/next").json()["card"]["id"] == r["id"]


def test_mine_rejects_a_bad_time_range(client):
    m = upload(client)
    r = client.post("/api/mined", json={"sentence": "Wo waren Sie?", "target": "waren", "lemma": "sein",
                                        "mediaId": m["id"], "start": 5, "end": 4})
    assert r.status_code == 422


def test_mine_without_media_file_still_creates_the_card(client):
    m = upload(client)
    r = client.post("/api/mined", json={"sentence": "Wo waren Sie gestern Abend?", "target": "Abend", "lemma": "Abend",
                                        "mediaId": m["id"], "start": 0.5, "end": 2.0}).json()
    assert r["audio"] is False and r["id"].startswith("mine:")


# ── #29: the spoken (Whisper) track ──

def test_snippet_of_a_spoken_line_pads_0_15_s():
    assert snippet.window(10.0, 12.0, (snippet.SPOKEN_PAD, snippet.SPOKEN_PAD)) == (9.85, 12.15)


@needs_ffmpeg
def test_mine_a_spoken_line_keeps_its_text_times_and_says_ki_transkript(client, tmp_path, monkeypatch):
    m = upload(client, make_clip(tmp_path))
    cuts = []
    real = snippet.cut
    monkeypatch.setattr(snippet, "cut", lambda src, a, b, out, pad: cuts.append((a, b, pad)) or real(src, a, b, out, pad))
    r = client.post("/api/mined", json={
        "sentence": "Das glaube ich Ihnen aber wirklich nicht.", "target": "glaube", "lemma": "glauben", "gloss": "believe",
        "source": "Schauen · Krimi", "mediaId": m["id"], "start": 4.62, "end": 6.31, "track": "spoken"}).json()
    assert r["audio"] is True and cuts == [(4.62, 6.31, (0.15, 0.15))]
    card = next(c for c in client.get("/api/mined").json() if c["id"] == r["id"])
    assert (card["sentence"], card["clipStart"], card["clipEnd"], card["transcript"]) == (
        "Das glaube ich Ihnen aber wirklich nicht.", 4.62, 6.31, True)
    # an ARD line as before: subtitle padding, no transcript mark
    r2 = client.post("/api/mined", json={
        "sentence": "Wo waren Sie gestern Abend?", "target": "Abend", "lemma": "Abend", "gloss": "evening",
        "source": "Schauen · Krimi", "mediaId": m["id"], "start": 0.5, "end": 2.0}).json()
    assert cuts[-1][2] == (snippet.PAD_BEFORE, snippet.PAD_AFTER)
    assert next(c for c in client.get("/api/mined").json() if c["id"] == r2["id"])["transcript"] is False


def test_zu_schwer_on_the_spoken_track_counts_its_lines(client, monkeypatch):
    """Heute's share counts the lines of the track he marked on (#23 + #29)."""
    import json
    from datetime import date

    from kaskade import db, ratings
    from kaskade.routes import ratings as rr
    m = upload(client)
    spoken = [{"start": 0.5, "end": 1.2, "text": "Wo waren Sie?"}, {"start": 1.3, "end": 2.0, "text": "Gestern Abend."},
              {"start": 4.5, "end": 6.0, "text": "Das glaube ich Ihnen nicht."}]
    with db.tx() as conn:
        conn.execute("UPDATE media SET spoken_cues = ? WHERE id = ?", (json.dumps(spoken), m["id"]))
    day = date(2026, 10, 13)
    monkeypatch.setattr(rr, "_today", lambda: day)
    it = {"kind": "clip", "mediaId": m["id"], "range": [0, 7], "position": 7}
    assert rr.share_for(it, day) == {"marked": 0, "lines": 3, "pct": 0}  # the spoken track is the default
    assert client.post(f"/api/media/{m['id']}/hard", json={"start": 1.3, "end": 2.0, "text": "Gestern Abend.", "track": "spoken"}).status_code == 200
    assert ratings.hard_marks(day, m["id"])[0]["track"] == "spoken"
    assert rr.share_for(it, day) == {"marked": 1, "lines": 3, "pct": 33}
    client.post(f"/api/media/{m['id']}/hard", json={"start": 4.5, "end": 6.0, "text": "Das glaube ich Ihnen nicht."})
    assert rr.share_for(it, day)["lines"] == 2  # last mark on ARD's lines: count those
    assert client.post(f"/api/media/{m['id']}/hard", json={"start": 1, "text": "x", "track": "whisper"}).status_code == 422
