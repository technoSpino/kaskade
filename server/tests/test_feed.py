import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from kaskade import feed, srs, tts


def fake_audio(monkeypatch):
    def fake(text, synthesize=None, fmt="ogg"):
        p = tts.cache_path(text, fmt)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"ID3" + b"\0" * 8000)  # ≈ 1 s at 64 kbit/s
        return p
    monkeypatch.setattr(tts, "audio_for", fake)


def test_week_key():
    assert feed.week_key(datetime(2026, 10, 13, 8, tzinfo=timezone.utc)) == "2026-W42"


def test_week_script_repeats_each_sentence():
    assert feed.week_script(["Eins.", "Zwei."]) == "Eins.\nEins.\nZwei.\nZwei."


def test_no_episodes_without_activity(client):
    assert feed.episodes() == []
    assert client.get("/api/feed/info").json()["episodes"] == []


def test_episodes_from_reading_and_reviews(client, monkeypatch):
    fake_audio(monkeypatch)
    client.post("/api/texts/t01/read")
    card = srs.deck()[0]
    srs.review(card["id"], 3)
    srs.mark_known(srs.deck()[1]["id"])  # "kenne ich" isn't a review → not in the episode
    eps = feed.episodes()
    assert [e["key"].split("-")[0] for e in eps] == ["week", "text"]
    assert card["sentence"] in eps[0]["text"]
    assert srs.deck()[1]["sentence"] not in eps[0]["text"]

    r = client.get("/api/feed.xml")
    assert r.status_code == 200 and "rss" in r.headers["content-type"]
    root = ET.fromstring(r.text)
    items = root.findall("./channel/item")
    assert len(items) == 2
    enc = items[1].find("enclosure")
    assert enc.get("url").endswith("/api/feed/audio/text-t01.mp3") and int(enc.get("length")) > 0
    assert items[1].find("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration").text == "0:01"

    a = client.get("/api/feed/audio/text-t01.mp3")
    assert a.status_code == 200 and a.headers["content-type"] == "audio/mpeg"


def test_feed_without_tts_lists_nothing_and_audio_404(client):
    client.post("/api/texts/t01/read")
    root = ET.fromstring(client.get("/api/feed.xml").text)
    assert root.findall("./channel/item") == []  # no Piper in tests → no playable episodes
    assert client.get("/api/feed/audio/text-t01.mp3").status_code == 404
    assert client.get("/api/feed/audio/nope.mp3").status_code == 404
