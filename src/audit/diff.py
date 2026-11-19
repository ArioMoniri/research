"""Diff two dictionary audits of the same database (used by /refresh-database).

    python -m src.audit.diff --db vivax-oracle-01 --old 2026-11-20 --new 2027-02-01

Writes results/audit/<db>/<new>/diff_vs_<old>.csv and prints a short summary.
Suppressed values ("<10", bounds) are compared as text only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..common import runlog
from ..common.config import ROOT
from .dictionary import read_csv, write_csv


def _num(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def diff(old_dir: Path, new_dir: Path, pct_points: float = 5.0) -> list[dict]:
    rows = []
    old_t = {r["table"]: r for r in read_csv(old_dir / "tables.csv")}
    new_t = {r["table"]: r for r in read_csv(new_dir / "tables.csv")}
    for t in sorted(set(new_t) - set(old_t)):
        rows.append({"change": "table_added", "table": t, "column": "", "old": "", "new": new_t[t]["num_rows_stats"]})
    for t in sorted(set(old_t) - set(new_t)):
        rows.append({"change": "table_dropped", "table": t, "column": "", "old": old_t[t]["num_rows_stats"], "new": ""})
    for t in sorted(set(old_t) & set(new_t)):
        a, b = old_t[t]["num_rows_stats"], new_t[t]["num_rows_stats"]
        if a != b:
            rows.append({"change": "row_count", "table": t, "column": "", "old": a, "new": b})
    old_c = {(r["table"], r["column"]): r for r in read_csv(old_dir / "columns.csv")}
    new_c = {(r["table"], r["column"]): r for r in read_csv(new_dir / "columns.csv")}
    for k in sorted(set(new_c) - set(old_c)):
        rows.append({"change": "column_added", "table": k[0], "column": k[1], "old": "", "new": new_c[k]["data_type"]})
    for k in sorted(set(old_c) - set(new_c)):
        rows.append({"change": "column_dropped", "table": k[0], "column": k[1], "old": old_c[k]["data_type"], "new": ""})
    for k in sorted(set(old_c) & set(new_c)):
        a, b = old_c[k], new_c[k]
        if a["data_type"] != b["data_type"]:
            rows.append({"change": "type_changed", "table": k[0], "column": k[1], "old": a["data_type"], "new": b["data_type"]})
        pa, pb = _num(a["non_null_pct"]), _num(b["non_null_pct"])
        moved = pa is not None and pb is not None and abs(pa - pb) >= pct_points
        if moved or a["completeness_flag"] != b["completeness_flag"]:
            rows.append({"change": "completeness", "table": k[0], "column": k[1],
                         "old": f"{a['non_null_pct']} ({a['completeness_flag']})",
                         "new": f"{b['non_null_pct']} ({b['completeness_flag']})"})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Diff two dictionary audits")
    ap.add_argument("--db", required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    args = ap.parse_args(argv)
    base = ROOT / "results" / "audit" / args.db
    out = base / args.new / f"diff_vs_{args.old}.csv"
    cmd = "python -m src.audit.diff " + " ".join(argv if argv is not None else sys.argv[1:])
    with runlog.logged(cmd, str(out.relative_to(ROOT))):
        rows = diff(base / args.old, base / args.new)
        write_csv(out, rows, ["change", "table", "column", "old", "new"])
    counts = {}
    for r in rows:
        counts[r["change"]] = counts.get(r["change"], 0) + 1
    print(f"{len(rows)} changes -> {out}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
