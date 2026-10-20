"""Wiederhören feed: a private podcast (RSS) with the audio of this week's input.

Episodes: every library text read in the last 14 days, plus "Kernsätze der Woche"
(each sentence reviewed in Karten this ISO week, spoken twice — #33: none about child abuse). Audio is Piper MP3,
cached in ~/kaskade-data/tts/audio. The feed is reachable only on the tailnet.
"""
from datetime import datetime, timedelta
from email.utils import format_datetime
from xml.sax.saxutils import escape

from . import db, srs, texts, themes

MP3_BYTES_PER_SEC = 64_000 / 8


def week_key(at: datetime) -> str:
    y, w, _ = at.astimezone(srs.TZ).isocalendar()
    return f"{y}-W{w:02d}"


def week_sentences(at: datetime) -> list[str]:
    """Distinct sentences of cards reviewed in the ISO week of `at`, without lines that hit #33's search
    (the cards themselves stay as they are)."""
    local = at.astimezone(srs.TZ)
    monday = (local - timedelta(days=local.weekday())).date().isoformat()
    with db.tx() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT card_id FROM review_log WHERE rating > 0 AND local_date >= ? GROUP BY card_id ORDER BY MIN(id)",
            (monday,))]
    out = []
    for cid in ids:
        c = srs.card_content(cid)
        if c and c["sentence"] not in out and not themes.ABUSE.search(c["sentence"]):
            out.append(c["sentence"])
    return out[:80]


def week_script(sentences: list[str]) -> str:
    return "\n".join(f"{s}\n{s}" for s in sentences)


def episodes(at: datetime | None = None) -> list[dict]:
    at = at or srs.now_utc()
    since = (at - timedelta(days=14)).isoformat()
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT text_id, MAX(read_at) AS last FROM text_reads WHERE read_at >= ? GROUP BY text_id ORDER BY last DESC",
            (since,)).fetchall()
    eps = []
    sentences = week_sentences(at)
    if sentences:
        key = week_key(at)
        eps.append({"key": f"week-{key}", "title": f"Kernsätze der Woche {key[-2:]}",
                    "description": f"{len(sentences)} Sätze aus deinen Karten, jeder zweimal.",
                    "text": week_script(sentences), "date": at})
    for r in rows:
        t = texts.get(r["text_id"])
        if t:
            eps.append({"key": f"text-{t['id']}", "title": f"Lesen: {t['title']}",
                        "description": t["text"].split("\n\n")[0][:240],
                        "text": t["text"].replace("\n\n", "\n"), "date": datetime.fromisoformat(r["last"])})
    return eps


def rss(eps: list[dict], base: str, sizes: dict[str, int]) -> str:
    items = []
    for e in eps:
        size = sizes.get(e["key"], 0)
        secs = int(size / MP3_BYTES_PER_SEC)
        url = f"{base}api/feed/audio/{e['key']}.mp3"
        items.append(
            "<item>"
            f"<title>{escape(e['title'])}</title>"
            f"<description>{escape(e['description'])}</description>"
            f"<guid isPermaLink=\"false\">kaskade-{escape(e['key'])}</guid>"
            f"<pubDate>{format_datetime(e['date'])}</pubDate>"
            f"<enclosure url=\"{escape(url)}\" length=\"{size}\" type=\"audio/mpeg\"/>"
            f"<itunes:duration>{secs // 60}:{secs % 60:02d}</itunes:duration>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>'
        "<title>Kaskade · Wiederhören</title>"
        f"<link>{escape(base)}</link>"
        "<language>de</language>"
        "<description>Audio von allem, was du diese Woche gelesen und gelernt hast. Privat, nur im Tailnet.</description>"
        "<itunes:author>Kaskade</itunes:author><itunes:explicit>false</itunes:explicit>"
        + "".join(items) +
        "</channel></rss>"
    )
