"""Error states and operations: empty deck, missing content, backups."""
import importlib.util
import sqlite3
import tarfile
from datetime import datetime

from kaskade import config, db, srs


def load_backup():
    spec = importlib.util.spec_from_file_location("backup", config.REPO_DIR / "server/scripts/backup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_empty_deck_is_handled(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONTENT_DIR", tmp_path / "nothing")
    srs.deck.cache_clear()
    srs.deck_index.cache_clear()
    try:
        r = client.get("/api/cards/next").json()
        assert r["card"] is None and r["counts"]["new"] == 0
        assert client.get("/api/cards/stats").json()["deckSize"] == 0
    finally:
        srs.deck.cache_clear()
        srs.deck_index.cache_clear()


def test_backup_contains_consistent_db_and_media(client, tmp_path):
    db.set_setting("phase", "2A")
    (config.MEDIA_DIR / "upload-1.mp4").write_bytes(b"video")
    (config.MEDIA_DIR / "stock-tatort-x.mp4").write_bytes(b"re-downloadable")
    (config.MEDIA_DIR / "mt-0123abcd.mp4").write_bytes(b"re-downloadable")
    (config.TTS_DIR / "audio").mkdir(parents=True, exist_ok=True)
    (config.TTS_DIR / "audio" / "x.ogg").write_bytes(b"regenerable")
    (config.DATA_DIR / ".env").write_text("ANTHROPIC_API_KEY=secret")

    out = load_backup().backup(data=config.DATA_DIR, dest=tmp_path / "bk", now=datetime(2026, 10, 12, 12, 0),
                                    db=config.DB_PATH)
    with tarfile.open(out) as tar:
        names = tar.getnames()
        assert "kaskade-data/kaskade.db" in names and "kaskade-data/media/upload-1.mp4" in names
        assert not any("tts" in n or ".env" in n for n in names)
        assert not any("stock-" in n or "/mt-" in n for n in names)  # Kaskade fetches those again
        tar.extract("kaskade-data/kaskade.db", tmp_path / "restore")
    con = sqlite3.connect(tmp_path / "restore/kaskade-data/kaskade.db")
    assert con.execute("SELECT value FROM settings WHERE key = 'phase'").fetchone()[0] == '"2A"'


def test_backup_keeps_newest(client, tmp_path):
    mod = load_backup()
    for minute in range(5):
        mod.backup(data=config.DATA_DIR, dest=tmp_path / "bk", keep=3, now=datetime(2026, 10, 12, 12, minute))
    left = sorted(p.name for p in (tmp_path / "bk").glob("*.tar.gz"))
    assert left == ["kaskade-20261012-120200.tar.gz", "kaskade-20261012-120300.tar.gz", "kaskade-20261012-120400.tar.gz"]


def test_missing_practice_and_texts_files_do_not_crash(client, monkeypatch, tmp_path):
    from kaskade import practice, texts
    monkeypatch.setattr(config, "CONTENT_DIR", tmp_path / "nothing")
    practice.bank.cache_clear()
    texts.library.cache_clear()
    try:
        assert client.get("/api/texts").json() == []
        o = client.get("/api/practice").json()
        assert o["lesen"] == [] and o["hoeren"] == []
    finally:
        practice.bank.cache_clear()
        texts.library.cache_clear()
