"""Clip conversion to H.264/AAC MP4 with +faststart (follow-up #3)."""
import shutil
import subprocess

import pytest

from kaskade import config, transcode

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def ff(*args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def moov_first(path) -> bool:
    data = path.read_bytes()
    return data.find(b"moov") < data.find(b"mdat")


def test_plan_per_codec():
    assert transcode.plan({"video": "h264", "audio": "aac"}) == "remux"
    assert transcode.plan({"video": "h264", "audio": None}) == "remux"
    assert transcode.plan({"video": "av1", "audio": "opus"}) == "transcode"
    assert transcode.plan({"video": "h264", "audio": "opus"}) == "transcode"
    assert transcode.plan({"video": "vp9", "audio": "aac"}) == "transcode"
    assert transcode.plan({"video": None, "audio": "mp3"}) == "keep"
    assert transcode.plan({"video": None, "audio": "opus"}) == "audio"


@needs_ffmpeg
def test_webm_becomes_h264_aac_mp4(tmp_path):
    src = tmp_path / "upload-1.webm"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x180:d=2", "-f", "lavfi", "-i", "sine=duration=2",
       "-c:v", "libvpx", "-c:a", "libopus", "-shortest", str(src))
    out = transcode.convert(src)
    assert out == tmp_path / "upload-1.mp4" and not src.exists()
    assert transcode.probe(out) == {"video": "h264", "audio": "aac"}
    assert moov_first(out)


@needs_ffmpeg
def test_h264_mp4_is_only_remuxed_for_faststart(tmp_path):
    src = tmp_path / "upload-2.mp4"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x180:d=2", "-f", "lavfi", "-i", "sine=duration=2",
       "-c:v", "libx264", "-c:a", "aac", "-shortest", str(src))  # no +faststart: moov at the end
    assert not moov_first(src)
    out = transcode.convert(src)
    assert out == src and moov_first(out)
    assert transcode.probe(out) == {"video": "h264", "audio": "aac"}


@needs_ffmpeg
def test_audio_files(tmp_path):
    wav = tmp_path / "a.wav"
    ff("-f", "lavfi", "-i", "sine=duration=1", str(wav))
    out = transcode.convert(wav)
    assert out.suffix == ".m4a" and transcode.probe(out)["audio"] == "aac"
    mp3 = tmp_path / "b.mp3"
    ff("-f", "lavfi", "-i", "sine=duration=1", str(mp3))
    assert transcode.convert(mp3) == mp3  # plays everywhere already


def test_broken_file_keeps_the_original(tmp_path):
    bad = tmp_path / "upload-9.mp4"
    bad.write_bytes(b"not a video")
    assert transcode.convert(bad) is None
    assert bad.exists() and not list(tmp_path.glob("*converting*"))


SRT = b"1\n00:00:00,500 --> 00:00:01,500\nHallo.\n"


@needs_ffmpeg
def test_upload_is_converted_in_the_background(client, tmp_path):
    clip = tmp_path / "c.webm"
    ff("-f", "lavfi", "-i", "color=c=gray:s=320x180:d=2", "-f", "lavfi", "-i", "sine=duration=2",
       "-c:v", "libvpx", "-c:a", "libopus", "-shortest", str(clip))
    r = client.post("/api/media/upload", files={"subtitles": ("s.srt", SRT), "media": ("c.webm", clip.read_bytes())},
                    data={"title": "T"}).json()
    m = client.get(f"/api/media/{r['id']}").json()   # TestClient runs background tasks before returning
    assert m["status"] == "ready"
    files = [f.name for f in config.MEDIA_DIR.iterdir()]
    assert files == [f"upload-{r['id']}.mp4"]
    assert client.get(f"/api/media/{r['id']}/file").headers["content-type"] == "video/mp4"


def test_failed_conversion_keeps_the_upload(client, monkeypatch):
    monkeypatch.setattr(transcode, "convert", lambda src: None)
    r = client.post("/api/media/upload", files={"subtitles": ("s.srt", SRT), "media": ("c.webm", b"x" * 100)},
                    data={"title": "T"}).json()
    m = client.get(f"/api/media/{r['id']}").json()
    assert m["status"] == "original" and m["hasMedia"]
    assert (config.MEDIA_DIR / f"upload-{r['id']}.webm").exists()


def test_conversion_can_be_switched_off(client, monkeypatch):
    monkeypatch.setenv("KASKADE_TRANSCODE", "0")
    r = client.post("/api/media/upload", files={"subtitles": ("s.srt", SRT), "media": ("c.webm", b"x" * 100)},
                    data={"title": "T"}).json()
    assert client.get(f"/api/media/{r['id']}").json()["status"] == "ready"
    assert (config.MEDIA_DIR / f"upload-{r['id']}.webm").exists()
