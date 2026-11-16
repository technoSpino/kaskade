"""ARD/ZDF Mediathek import as a background job (follow-up #8); yt-dlp is replaced by a fake."""
import time

import pytest

from kaskade import config, mediathek

SRT = "1\n00:00:01,000 --> 00:00:02,500\nGuten Abend, meine Damen und Herren.\n\n2\n00:00:03,000 --> 00:00:04,000\n♪ Musik ♪\n"
URL = "https://www.ardmediathek.de/video/tatort/schweigen/das-erste/Y3JpZDovL2Rlc"


def wait(client, job_id, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/media/jobs/{job_id}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


@pytest.fixture()
def fake_fetch(monkeypatch):
    def fetch(url, dest, stem, hook, subs=True):
        hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100, "speed": 8e6})
        (dest / f"{stem}.mp4").write_bytes(b"\x00" * 100)
        if "ohne-ut" not in url:
            (dest / f"{stem}.deu.srt").write_text(SRT, encoding="utf-8")
        return {"title": "Schweigen", "series": "Tatort"}
    monkeypatch.setattr(mediathek, "fetch", fetch)
    monkeypatch.setenv("KASKADE_TRANSCODE", "0")


def test_only_mediathek_links(client):
    for url in ["https://www.youtube.com/watch?v=x", "ftp://zdf.de/x", "hallo"]:
        assert client.post("/api/media/mediathek", json={"url": url}).status_code == 422


def test_job_downloads_and_registers_a_clip(client, fake_fetch):
    r = client.post("/api/media/mediathek", json={"url": URL})
    assert r.status_code == 202
    j = wait(client, r.json()["jobId"])
    assert j["status"] == "done" and j["progress"] == 1.0 and j["mediaId"]
    m = client.get(f"/api/media/{j['mediaId']}").json()
    assert m["title"] == "Tatort: Schweigen" and m["kind"] == "mediathek" and m["sourceUrl"] == URL
    assert m["hasMedia"] and m["cueCount"] == 2
    # no subtitle files are kept, only the clip
    assert [f.suffix for f in config.MEDIA_DIR.iterdir()] == [".mp4"]


def test_job_without_german_subtitles_fails_cleanly(client, fake_fetch):
    j = wait(client, client.post("/api/media/mediathek", json={"url": URL + "/ohne-ut"}).json()["jobId"])
    assert j["status"] == "error" and "Untertitel" in j["message"]
    assert list(config.MEDIA_DIR.iterdir()) == []
    assert client.get("/api/media").json() == []


def test_download_error_is_reported(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("HTTP Error 404")
    monkeypatch.setattr(mediathek, "fetch", boom)
    j = wait(client, client.post("/api/media/mediathek", json={"url": URL}).json()["jobId"])
    assert j["status"] == "error" and "fehlgeschlagen" in j["message"]


def test_unknown_job(client):
    assert client.get("/api/media/jobs/nope").status_code == 404


def test_progress_hook_reads_bytes_or_fragments():
    job = mediathek.start("x", lambda *_: None)
    hook = mediathek.progress_hook(job)
    hook({"status": "downloading", "downloaded_bytes": 30, "total_bytes_estimate": 120})
    assert mediathek.get(job)["progress"] == 0.25
    hook({"status": "downloading", "downloaded_bytes": 0, "fragment_index": 9, "fragment_count": 10})
    assert mediathek.get(job)["progress"] == 0.9
