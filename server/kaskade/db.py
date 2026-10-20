"""SQLite storage. One file at ~/kaskade-data/kaskade.db, single user."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vocab_tests (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  answers TEXT NOT NULL,
  result TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL,            -- upload | youtube
  title TEXT NOT NULL,
  source_url TEXT,
  media_file TEXT,               -- filename inside MEDIA_DIR
  cues TEXT NOT NULL             -- JSON [{start, end, text}]
);
CREATE TABLE IF NOT EXISTS satzcheck_runs (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  media_id INTEGER,
  content_type TEXT NOT NULL,    -- simple | adult
  window_start REAL NOT NULL,
  window_end REAL NOT NULL,
  ratings TEXT NOT NULL,         -- JSON [{cue, text, rating}]
  result TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS placements (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL,          -- in_progress | done
  state TEXT NOT NULL,
  result TEXT
);
CREATE TABLE IF NOT EXISTS recordings (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  context TEXT NOT NULL,         -- e.g. placement:3:q1
  filename TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS writings (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  context TEXT NOT NULL,
  prompt_id TEXT NOT NULL,
  text TEXT NOT NULL,
  grade TEXT
);
CREATE TABLE IF NOT EXISTS cards (
  id TEXT PRIMARY KEY,           -- e.g. core:0001
  status TEXT NOT NULL,          -- new | learning | known | suspended
  fsrs TEXT,                     -- serialised fsrs.Card
  due TEXT,
  introduced_on TEXT,            -- local date the card was first shown
  lapses INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS cards_due ON cards(status, due);
CREATE TABLE IF NOT EXISTS review_log (
  id INTEGER PRIMARY KEY,
  card_id TEXT NOT NULL,
  rating INTEGER NOT NULL,       -- 1..4, 0 = kenne ich schon
  reviewed_at TEXT NOT NULL,
  local_date TEXT NOT NULL,
  prev TEXT                      -- card row before this review (for undo)
);
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY,
  local_date TEXT NOT NULL,
  block TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  seconds INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS mined (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  sentence TEXT NOT NULL,
  target TEXT NOT NULL,
  lemma TEXT NOT NULL,
  display TEXT NOT NULL,
  gloss TEXT NOT NULL,
  en TEXT,
  note TEXT,
  kasus TEXT,                    -- N | A | D | G | NULL
  source TEXT
);
CREATE TABLE IF NOT EXISTS watch_ranges (
  local_date TEXT NOT NULL,      -- #21: a day's rolling clip range, fixed on its first computation
  block TEXT NOT NULL,           -- input | lesen
  clip TEXT NOT NULL,            -- stock key
  start REAL NOT NULL,
  end REAL,
  clean INTEGER NOT NULL,        -- 1 = fixed before he started the block that day (counts for his pace)
  reached REAL,                  -- his position the next time a range of this block was fixed
  PRIMARY KEY (local_date, block)
);
CREATE TABLE IF NOT EXISTS media_progress (
  media_id INTEGER PRIMARY KEY,  -- resume position per clip (Schauen & minen)
  position REAL NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS practice_attempts (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  module TEXT NOT NULL,          -- lesen | hoeren | schreiben
  item_id TEXT NOT NULL,
  points INTEGER NOT NULL,
  total INTEGER NOT NULL,
  timed INTEGER NOT NULL DEFAULT 0,
  seconds INTEGER,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS immersion_log (
  id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  local_date TEXT NOT NULL,
  minutes INTEGER NOT NULL,
  kind TEXT NOT NULL,            -- aktiv | passiv
  title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS text_reads (
  id INTEGER PRIMARY KEY,
  text_id TEXT NOT NULL,
  read_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plan_done (
  local_date TEXT NOT NULL,
  block TEXT NOT NULL,
  PRIMARY KEY (local_date, block)
);
CREATE TABLE IF NOT EXISTS ratings (
  id INTEGER PRIMARY KEY,        -- #23 "Wie viel hast du verstanden?" after a block
  created_at TEXT NOT NULL,
  local_date TEXT NOT NULL,
  block TEXT NOT NULL,           -- input | lesen | pruefung (Lesetest)
  item TEXT NOT NULL,            -- clip:<key>:<from>-<to> | text:<id> | news:<feed>:<date> | book:<id>:<part> | lesetest:<book>
  kind TEXT NOT NULL,            -- clip | audio | text | news | book | lesetest
  label TEXT NOT NULL,           -- what it was, as Heute showed it
  book TEXT,                     -- book id (book days and the Lesetest, #24)
  pct INTEGER,                   -- 20 | 40 | 60 | 80 | 100; NULL = skipped
  hard INTEGER,                  -- Schauen: lines marked "zu schwer" …
  lines INTEGER,                 -- … of the lines heard
  detail TEXT,                   -- JSON: clip id + range, article links, pages
  UNIQUE (local_date, block, item)
);
CREATE TABLE IF NOT EXISTS hard_lines (
  id INTEGER PRIMARY KEY,        -- #23 Schauen: Z = "zu schwer"
  created_at TEXT NOT NULL,
  local_date TEXT NOT NULL,
  media_id INTEGER NOT NULL,
  start REAL NOT NULL,
  end REAL,
  text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news_picks (
  local_date TEXT NOT NULL,      -- the plan day the articles are for
  feed TEXT NOT NULL,            -- tagesschau feed id (see materials.NEWS_FEEDS)
  items TEXT NOT NULL,           -- JSON [{title, url, published}] — links only
  PRIMARY KEY (local_date, feed)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


MIGRATIONS = [
    "ALTER TABLE review_log ADD COLUMN prev TEXT",
    # mined from a clip (Schauen & minen): where the line is, and its audio snippet
    "ALTER TABLE mined ADD COLUMN media_id INTEGER",
    "ALTER TABLE mined ADD COLUMN clip_start REAL",
    "ALTER TABLE mined ADD COLUMN clip_end REAL",
    "ALTER TABLE mined ADD COLUMN audio TEXT",
    # #19: which fields a KI filled in (JSON list: lemma, gloss, case), more target words of the same line
    "ALTER TABLE mined ADD COLUMN ai_fields TEXT",
    "ALTER TABLE mined ADD COLUMN words TEXT",
    # #25: time to reveal (ms, capped at 60 s), rating derived from it (1) or chosen (0), words in the sentence
    "ALTER TABLE review_log ADD COLUMN reveal_ms INTEGER",
    "ALTER TABLE review_log ADD COLUMN auto INTEGER",
    "ALTER TABLE review_log ADD COLUMN words INTEGER",
    # #28: the card's audio played by itself before the timer started (1) or not (0)
    "ALTER TABLE review_log ADD COLUMN autoplay INTEGER",
    # #29: the "gesprochen" track from a Whisper transcript (JSON [{start, end, text}]); which track a
    # "zu schwer" line and a mined sentence came from (spoken | NULL = ARD subtitles)
    "ALTER TABLE media ADD COLUMN spoken_cues TEXT",
    "ALTER TABLE hard_lines ADD COLUMN track TEXT",
    "ALTER TABLE mined ADD COLUMN track TEXT",
    # #29: what media.spoken_cues was built from ("<mtime_ns>:<size>:<builder>"): a replaced file is re-imported
    "ALTER TABLE media ADD COLUMN spoken_stamp TEXT",
    # clip conversion to H.264/AAC MP4: NULL/ready | converting | original (conversion failed, original kept)
    "ALTER TABLE media ADD COLUMN status TEXT",
    # plan stock (#16): stable key from data/plan/stock.json, genre tag, duration for clips without cues
    "ALTER TABLE media ADD COLUMN key TEXT",
    "ALTER TABLE media ADD COLUMN tag TEXT",
    "ALTER TABLE media ADD COLUMN duration REAL",
]


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for sql in MIGRATIONS:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # already applied


@contextmanager
def tx():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_setting(key: str, default=None):
    with tx() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
