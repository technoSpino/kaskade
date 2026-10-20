"""Plan stock (#16): the exact media the plan assigns, fetched into ~/kaskade-data in advance.

data/plan/stock.json lists every clip, podcast episode, YouTube video and book the plan uses —
links only, the files never go into git. Library rows carry the item's `key`, so a plan day
can say "tatort-schweigen 30:14–60:40" and Heute opens exactly that.
"""
import json
import logging
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from . import config, db, mediathek, satzcheck, transcode

log = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (Kaskade; personal learning app)"}
TAGS = {"krimi": "Krimi", "comedy": "Comedy", "drama": "Drama", "doku": "Doku", "news": "Nachrichten",
        "talk": "Talk", "podcast": "Podcast"}
PAPER_NOTICE_DAYS = 7                       # buy a printed book at least a week ahead …
DIGITAL_NOTICE_DAYS = 2                     # … an ebook or audiobook two days ahead


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads((config.CONTENT_DIR / "plan/stock.json").read_text(encoding="utf-8"))


def item(key: str) -> dict | None:
    return next((i for i in catalog()["items"] if i["key"] == key), None)


def book(book_id: str) -> dict | None:
    return next((b for b in catalog().get("books", []) if b["id"] == book_id), None)


def guess_tag(title: str) -> str | None:
    """A genre for a clip from its title (editable later in "Deine Clips")."""
    t = title.lower()
    rules = [("comedy", ("merz gegen merz", "tatortreiniger", "mord mit aussicht")),
             ("krimi", ("tatort", "polizeiruf", "soko", "krimi", "kommissar")),
             ("drama", ("charité", "charite", "bergdoktor", "druck")),
             ("news", ("tagesschau", "tagesthemen", "nachrichten")),
             ("doku", ("37 grad", "terra x", "doku", "reportage", "wunderschön", "feuer & flamme", "respekt")),
             ("talk", ("die 100", "talk", "maischberger")),
             ("podcast", ("podcast",))]
    for tag, words in rules:
        if any(w in t for w in words):
            return tag
    return None


# ── Library rows ─────────────────────────────────────────────────────────────

def _rows() -> list[dict]:
    with db.tx() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, key, tag, title, kind, media_file, status, duration, source_url FROM media")]


def by_key() -> dict[str, dict]:
    return {r["key"]: r for r in _rows() if r["key"]}


def playable(row: dict | None) -> bool:
    """In the library with a file on disk that every browser plays (converted or nothing to convert)."""
    if not row or not row["media_file"]:
        return False
    return (row["status"] or "ready") == "ready" and (config.MEDIA_DIR / row["media_file"]).exists()


def link_existing() -> list[str]:
    """Give catalog keys to clips that are already in the library (e.g. Matt's own Tatort upload)."""
    linked = []
    rows = _rows()
    have = {r["key"] for r in rows if r["key"]}
    for it in catalog()["items"]:
        if it["key"] in have or not it.get("match"):
            continue
        row = next((r for r in rows if not r["key"] and r["title"].startswith(it["match"])), None)
        if row:
            with db.tx() as conn:
                conn.execute("UPDATE media SET key = ?, tag = COALESCE(tag, ?) WHERE id = ?",
                             (it["key"], it.get("tag"), row["id"]))
            linked.append(it["key"])
    return linked


def backfill_tags() -> None:
    """Clips without a tag get one guessed from the title (once; "" means: deliberately none)."""
    with db.tx() as conn:
        for r in conn.execute("SELECT id, title FROM media WHERE tag IS NULL").fetchall():
            conn.execute("UPDATE media SET tag = ? WHERE id = ?", (guess_tag(r["title"]) or "", r["id"]))


# ── Fetching ─────────────────────────────────────────────────────────────────

def _register(it: dict, kind: str, media_file: str, cues: list, duration: float | None) -> int:
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO media(created_at, kind, title, source_url, media_file, cues, key, tag, duration, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (db.now_iso(), kind, it["title"], it.get("url"), media_file, json.dumps(cues, ensure_ascii=False),
             it["key"], it.get("tag") or "", duration, "converting" if transcode.enabled() else "ready"))
        return cur.lastrowid


def _convert(media_id: int) -> None:
    from .routes.media import convert_media  # the same conversion as uploads
    if transcode.enabled():
        convert_media(media_id)


def duration_of(path: Path) -> float | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                             check=True, capture_output=True, text=True, timeout=60).stdout
        return round(float(json.loads(out)["format"]["duration"]), 2)
    except (subprocess.SubprocessError, OSError, ValueError, KeyError):
        return None


def fetch_mediathek(it: dict) -> int:
    """Download an ARD/ZDF episode with its German subtitles, register it under its key."""
    stem = f"stock-{it['key']}"
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    mediathek.fetch(it["url"], config.MEDIA_DIR, stem, lambda d: None)
    files = sorted(config.MEDIA_DIR.glob(f"{stem}.*"))
    subs = [f for f in files if f.suffix in {".srt", ".vtt"}]
    media = [f for f in files if f.suffix in {".mp4", ".webm", ".mkv", ".m4v", ".mov"}]
    if not media or not subs:
        for f in files:
            f.unlink(missing_ok=True)
        raise RuntimeError("kein Video" if not media else "keine deutschen Untertitel")
    cues = satzcheck.parse_subtitles(subs[0].read_text(encoding="utf-8", errors="replace"))
    for f in subs:
        f.unlink(missing_ok=True)  # cues live in the DB; no third-party subtitle files kept
    media_id = _register(it, "mediathek", media[0].name, cues, duration_of(media[0]))
    _convert(media_id)
    return media_id


def podcast_episode(feed_xml: bytes, number: str) -> dict | None:
    """The feed entry whose title starts with "<number>:" → {title, url, published}."""
    channel = ET.fromstring(feed_xml).find("channel")
    for entry in channel.findall("item") if channel is not None else []:
        title = (entry.findtext("title") or "").strip()
        enc = entry.find("enclosure")
        if re.match(rf"^#?{re.escape(number)}\b", title) and enc is not None and enc.get("url"):
            return {"title": title, "url": enc.get("url"), "published": entry.findtext("pubDate")}
    return None


def _download_audio(it: dict, url: str, kind: str) -> int:
    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(url.split("?")[0]).suffix or ".mp3"
    dest = config.MEDIA_DIR / f"stock-{it['key']}{ext}"
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, tmp.open("wb") as out:
        while chunk := r.read(1024 * 1024):
            out.write(chunk)
    tmp.replace(dest)
    media_id = _register(it, kind, dest.name, [], duration_of(dest))
    _convert(media_id)
    return media_id


def fetch_podcast(it: dict) -> int:
    """Download one episode from the podcast's public RSS feed as an audio clip (no subtitles)."""
    with urllib.request.urlopen(urllib.request.Request(it["feed"], headers=UA), timeout=60) as r:
        ep = podcast_episode(r.read(), str(it["episode"]))
    if not ep:
        raise RuntimeError(f"Folge {it['episode']} nicht im Feed")
    return _download_audio(it, ep["url"], "podcast")


def fetch_audio(it: dict) -> int:
    """A radio play with a direct audio link (e.g. ARD Radio Tatort, which has no public feed)."""
    return _download_audio(it, it["audio"], "audio")


FETCHERS = {"mediathek": fetch_mediathek, "podcast": fetch_podcast, "audio": fetch_audio}


def due(it: dict, today: date) -> bool:
    return it["kind"] in FETCHERS and date.fromisoformat(it.get("fetchOn", "2000-01-01")) <= today


def run(today: date, only: set[str] | None = None) -> dict:
    """Link existing clips, then fetch every due item that isn't in the library yet."""
    report = {"linked": link_existing(), "fetched": [], "failed": [], "waiting": []}
    have = by_key()
    for it in catalog()["items"]:
        if it["kind"] not in FETCHERS or it["key"] in have or (only and it["key"] not in only):
            continue
        if not due(it, today):
            report["waiting"].append({"key": it["key"], "fetchOn": it["fetchOn"]})
            continue
        try:
            FETCHERS[it["kind"]](it)
            report["fetched"].append(it["key"])
        except Exception as e:  # network, yt-dlp, ffmpeg: report and carry on with the next item
            log.warning("stock %s failed: %s", it["key"], e)
            report["failed"].append({"key": it["key"], "error": str(e)[:200]})
    return report


def notice(first_day: date, fmt: str) -> date:
    """"Kaufen bis": a week before the first reading day for paper, two days for ebook/audiobook."""
    days = PAPER_NOTICE_DAYS if fmt == "paper" else DIGITAL_NOTICE_DAYS
    return first_day - timedelta(days=days)
