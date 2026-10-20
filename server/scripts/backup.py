"""Back up ~/kaskade-data to ~/kaskade-backups/kaskade-YYYYMMDD-HHMM.tar.gz.

Includes a consistent snapshot of kaskade.db (SQLite backup API, safe while the
API runs), media/, recordings/ and snippets/. Skips what can be regenerated (tts/, dict/, freq/)
and .env (secrets), and media Kaskade can download again (stock-* / mt-*: Mediathek
and podcast episodes, see data/plan/stock.json). Keeps the newest 14 archives.

Usage: .venv/bin/python scripts/backup.py [--dest DIR] [--keep N]
Restore: see docs/kaskade/RUNBOOK.md
"""
import argparse
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

DATA = Path.home() / "kaskade-data"
DEST = Path.home() / "kaskade-backups"
INCLUDE_DIRS = ("media", "recordings", "snippets")
REFETCHABLE = ("stock-", "mt-", ".partial")   # re-downloadable stock, unfinished uploads


def _skip_refetchable(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    return None if Path(info.name).name.startswith(REFETCHABLE) else info


def backup(data: Path = DATA, dest: Path = DEST, keep: int = 14, now: datetime | None = None,
           db: Path | None = None) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    out = dest / f"kaskade-{stamp}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "kaskade.db"
        db = db or data / "kaskade.db"
        if db.exists():
            src = sqlite3.connect(db)
            dst = sqlite3.connect(snap)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
        with tarfile.open(out, "w:gz") as tar:
            if snap.exists():
                tar.add(snap, arcname="kaskade-data/kaskade.db")
            for d in INCLUDE_DIRS:
                if (data / d).exists():
                    tar.add(data / d, arcname=f"kaskade-data/{d}", filter=_skip_refetchable)
    archives = sorted(dest.glob("kaskade-*.tar.gz"))
    for old in archives[:-keep]:
        old.unlink()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", type=Path, default=DEST)
    ap.add_argument("--keep", type=int, default=14)
    args = ap.parse_args()
    out = backup(dest=args.dest, keep=args.keep)
    print(f"{out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
