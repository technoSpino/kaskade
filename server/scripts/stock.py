"""Fetch the plan's stock (data/plan/stock.json) into ~/kaskade-data, then run the Materialcheck.

Links clips that are already in the library to their catalog key, downloads every due
Mediathek/podcast item that is missing, and writes materialcheck.json for Heute.
Run daily by kaskade-stock.timer; safe to run by hand any time.

Usage: .venv/bin/python scripts/stock.py [--only KEY,KEY] [--no-fetch]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaskade import db, stock  # noqa: E402
from kaskade.routes.today import _today  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated catalog keys")
    ap.add_argument("--no-fetch", action="store_true", help="only link and check")
    args = ap.parse_args()
    db.init()
    stock.backfill_tags()
    only = {k for k in args.only.split(",") if k} or None
    report = stock.run(_today(), only=only) if not args.no_fetch else {"linked": stock.link_existing()}
    try:
        from kaskade import materials
        report["check"] = materials.write_check(_today())
    except ImportError:
        pass
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
