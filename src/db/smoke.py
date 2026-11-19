"""Connection smoke test: one query against a one-row system table.

    python -m src.db.smoke --db vivax-oracle-01

Run this first on the database machine. It proves that the registered
connection works without a password prompt and that CSV spooling works.
It reads no patient table.
"""
import argparse
import csv
import sys
import tempfile
from pathlib import Path

from ..common import runlog
from ..common.config import database
from .base import get_adapter

SMOKE_SQL = {"oracle": "SELECT 1 AS ok FROM dual"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Connection smoke test")
    ap.add_argument("--db", required=True)
    args = ap.parse_args(argv)
    entry = database(args.db)
    adapter = get_adapter(entry)
    sql = SMOKE_SQL.get(adapter.engine)
    if sql is None:
        adapter.dictionary_queries()  # raises the clear not-implemented message
        return 2
    with runlog.logged(f"python -m src.db.smoke --db {args.db}", "(none)", note="SELECT 1; no table read"):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "smoke.csv"
            adapter.run_to_csv(sql, out, timeout_s=60)
            with open(out, newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.reader(fh))
        if len(rows) != 2 or rows[1][0].strip() != "1":
            raise RuntimeError("connected, but the CSV output was not in the expected form; check SQLcl version and SQLFORMAT")
    print("connection ok; CSV spool ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
