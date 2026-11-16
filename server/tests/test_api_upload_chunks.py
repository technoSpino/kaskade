"""Chunked video uploads (follow-up #9): big files arrive in pieces, then register as a clip."""
from kaskade import config
from kaskade.routes import media

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo.\n"


def start(client, size, filename="film.mp4"):
    r = client.post("/api/media/uploads", json={"filename": filename, "size": size})
    assert r.status_code == 200, r.text
    return r.json()["uploadId"]


def put(client, uid, offset, data):
    return client.put(f"/api/media/uploads/{uid}?offset={offset}", content=data,
                      headers={"Content-Type": "application/octet-stream"})


def finish(client, uid, monkeypatch):
    monkeypatch.setenv("KASKADE_TRANSCODE", "0")
    return client.post("/api/media/upload", files={"subtitles": ("s.srt", SRT)}, data={"uploadId": uid, "title": "Film"})


def test_chunks_are_joined_and_registered(client, monkeypatch):
    data = bytes(range(256)) * 1000  # 256 kB
    uid = start(client, len(data))
    for off in range(0, len(data), 100_000):
        assert put(client, uid, off, data[off:off + 100_000]).json()["received"] == min(len(data), off + 100_000)
    m = finish(client, uid, monkeypatch).json()
    assert m["hasMedia"] and m["title"] == "Film"
    assert (config.MEDIA_DIR / f"upload-{m['id']}.mp4").read_bytes() == data
    assert list((config.MEDIA_DIR / ".partial").iterdir()) == []


def test_a_retried_chunk_is_not_appended_twice(client):
    uid = start(client, 10)
    assert put(client, uid, 0, b"12345").json()["received"] == 5
    assert put(client, uid, 0, b"12345").json()["received"] == 5   # retry after a lost response
    assert put(client, uid, 5, b"67890").json()["received"] == 10


def test_incomplete_upload_cannot_be_registered(client, monkeypatch):
    uid = start(client, 10)
    put(client, uid, 0, b"12345")
    assert finish(client, uid, monkeypatch).status_code == 409


def test_validation(client, monkeypatch):
    assert client.post("/api/media/uploads", json={"filename": "x.exe", "size": 5}).status_code == 422
    assert client.post("/api/media/uploads", json={"filename": "x.mp4", "size": 0}).status_code == 422
    assert put(client, "0123456789abcdef", 0, b"x").status_code == 404
    assert put(client, "../../etc/passwd", 0, b"x").status_code == 404
    monkeypatch.setattr(media, "CHUNK_MAX", 4)
    uid = start(client, 100)
    assert put(client, uid, 0, b"too big").status_code == 413
    assert put(client, uid, 0, b"ok").json()["received"] == 2  # nothing left over from the rejected piece
