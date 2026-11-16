"""YouTube import from a datacenter IP (follow-up #4): cookies.txt, clear messages, Mac one-liner."""
import stat

from kaskade import config
from kaskade.routes import media

COOKIES = ("# Netscape HTTP Cookie File\n"
           ".youtube.com\tTRUE\t/\tTRUE\t1893456000\tSID\tabc\n"
           ".youtube.com\tTRUE\t/\tTRUE\t1893456000\tHSID\tdef\n")
URL = "https://www.youtube.com/watch?v=abcdefghijk"


def test_help_has_the_mac_command(client):
    h = client.get("/api/media/youtube/help").json()
    assert h["cookies"] is False
    assert "--sub-langs" in h["macCommand"] and "--convert-subs srt" in h["macCommand"]


def test_cookies_upload_validation_and_delete(client):
    bad = client.post("/api/media/youtube/cookies", files={"file": ("c.txt", b"hello")})
    assert bad.status_code == 422
    other = client.post("/api/media/youtube/cookies", files={"file": ("c.txt", COOKIES.replace("youtube", "example").encode())})
    assert other.status_code == 422 and "youtube.com" in other.json()["detail"]
    ok = client.post("/api/media/youtube/cookies", files={"file": ("c.txt", COOKIES.encode())}).json()
    assert ok["cookies"] is True
    mode = stat.S_IMODE((config.DATA_DIR / "youtube-cookies.txt").stat().st_mode)
    assert mode == 0o600
    assert media.youtube_opts(config.MEDIA_DIR, "yt-1")["cookiefile"].endswith("youtube-cookies.txt")
    assert client.delete("/api/media/youtube/cookies").json()["cookies"] is False
    assert "cookiefile" not in media.youtube_opts(config.MEDIA_DIR, "yt-1")


def test_bot_check_gives_a_clear_message(client, monkeypatch):
    def blocked(*a, **k):
        raise RuntimeError("ERROR: [youtube] abc: Sign in to confirm you're not a bot")
    monkeypatch.setattr(media, "fetch_youtube", blocked)
    r = client.post("/api/media/youtube", json={"url": URL})
    assert r.status_code == 502
    assert "cookies.txt" in r.json()["detail"] and "Mac" in r.json()["detail"]
    client.post("/api/media/youtube/cookies", files={"file": ("c.txt", COOKIES.encode())})
    r = client.post("/api/media/youtube", json={"url": URL})
    assert "abgelaufen" in r.json()["detail"]
