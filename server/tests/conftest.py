import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """API client with an isolated data dir and database."""
    from kaskade import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(config, "RECORDINGS_DIR", tmp_path / "recordings")
    monkeypatch.setattr(config, "SNIPPETS_DIR", tmp_path / "snippets")
    monkeypatch.setattr(config, "TTS_DIR", tmp_path / "tts")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from fastapi.testclient import TestClient
    from kaskade.main import app

    with TestClient(app) as c:
        yield c
