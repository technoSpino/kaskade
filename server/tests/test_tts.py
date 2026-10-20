from kaskade import srs, tts


def test_cache_path_is_stable_and_text_specific(client):
    a = tts.cache_path("Hallo zusammen!")
    assert a == tts.cache_path("  Hallo zusammen!  ")
    assert a != tts.cache_path("Hallo!")
    assert a.suffix == ".ogg" and a.parent == tts.audio_dir()


def test_audio_for_uses_cache(client):
    calls = []

    def fake(text, out):
        calls.append(text)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"OggS")

    p1 = tts.audio_for("Guten Tag.", synthesize=fake)
    p2 = tts.audio_for("Guten Tag.", synthesize=fake)
    assert p1 == p2 and p1.read_bytes() == b"OggS"
    assert calls == ["Guten Tag."]


def test_unavailable_without_voice(client):
    # the test data dir has no voice file
    assert tts.available() is False
    assert tts.audio_for("Ohne Stimme.") is None


def test_card_audio_endpoint(client, monkeypatch):
    card = srs.deck()[0]
    assert client.get(f"/api/cards/{card['id']}/audio").status_code == 404  # no Piper → browser fallback

    def fake_audio(text, synthesize=None):
        p = tts.cache_path(text)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"OggS-fake")
        return p

    monkeypatch.setattr(tts, "audio_for", fake_audio)
    r = client.get(f"/api/cards/{card['id']}/audio")
    assert r.status_code == 200 and r.content == b"OggS-fake"
    assert r.headers["content-type"] == "audio/ogg"
    assert client.get("/api/cards/core:r99999/audio").status_code == 404
