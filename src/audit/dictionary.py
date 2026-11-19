"""Phase 1 step 1: dictionary-only audit.

Reads the data dictionary of a registered database (no data table is scanned),
applies small-cell suppression, and writes aggregate CSVs plus a Markdown
report. Raw dictionary output lives only in a temporary directory.

    python -m src.audit.dictionary --db vivax-oracle-01
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from ..common import runlog, suppress
from ..common.config import ROOT, database, project
from ..db.base import QueryFailed, get_adapter

OPTIONAL = {"segments", "part_tables", "part_keys", "tab_comments", "col_comments",
            "indexes", "ind_columns"}


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                for row in csv.DictReader(fh)]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fetch(adapter, tmp: Path) -> tuple[dict[str, list[dict]], dict]:
    """Run each dictionary query, trying alternatives in order."""
    data, manifest = {}, {}
    for name, alternatives in adapter.dictionary_queries().items():
        errors = []
        for i, sql in enumerate(alternatives):
            raw = tmp / f"{name}.csv"
            try:
                adapter.run_to_csv(sql, raw)
                data[name] = read_csv(raw)
                manifest[name] = {"status": "ok", "alternative": i, "rows": len(data[name])}
                break
            except QueryFailed as exc:
                errors.append(str(exc))
        else:
            if name not in OPTIONAL:
                raise QueryFailed(f"required dictionary query '{name}' failed: {errors[-1]}")
            data[name] = []
            manifest[name] = {"status": "unavailable", "errors": errors}
    return data, manifest


def build(data: dict[str, list[dict]], floor: float, threshold: int) -> dict[str, tuple[list[dict], list[str]]]:
    """Turn raw dictionary rows into suppressed, publishable tables."""
    seg = {r["table_name"]: r for r in data["segments"]}
    part = {r["table_name"]: r for r in data["part_tables"]}
    pkeys = defaultdict(list)
    for r in sorted(data["part_keys"], key=lambda r: suppress.to_int(r.get("column_position")) or 0):
        pkeys[r["table_name"]].append(r["column_name"])
    tcom = {r["table_name"]: r.get("comments", "") for r in data["tab_comments"]}
    ccom = {(r["table_name"], r["column_name"]): r.get("comments", "") for r in data["col_comments"]}
    real_tables = {r["table_name"] for r in data["tables"]}
    rows_of = {r["table_name"]: r.get("num_rows", "") for r in data["tables"]}

    tables = []
    for r in sorted(data["tables"], key=lambda r: -(suppress.to_int(r.get("num_rows")) or -1)):
        t = r["table_name"]
        tables.append({
            "table": t,
            "num_rows_stats": suppress.count(r.get("num_rows"), threshold),
            "stats_last_analyzed": r.get("last_analyzed", ""),
            "stats_sample_size": suppress.count(r.get("sample_size"), threshold),
            "blocks": r.get("blocks", ""),
            "avg_row_len": r.get("avg_row_len", ""),
            "bytes_on_disk": seg.get(t, {}).get("bytes", ""),
            "segments": seg.get(t, {}).get("segments", ""),
            "partitioned": r.get("partitioned", ""),
            "partitioning_type": part.get(t, {}).get("partitioning_type", ""),
            "subpartitioning_type": part.get(t, {}).get("subpartitioning_type", ""),
            "partition_count": part.get(t, {}).get("partition_count", ""),
            "partition_key": ", ".join(pkeys.get(t, [])),
            "temporary": r.get("temporary", ""),
            "comment": tcom.get(t, ""),
        })

    columns, under = [], []
    for r in sorted(data["columns"], key=lambda r: (r["table_name"], suppress.to_int(r.get("column_id")) or 0)):
        t = r["table_name"]
        if t not in real_tables:  # views and other objects are listed separately
            continue
        nulls, pct, flag = suppress.completeness(rows_of.get(t), r.get("num_nulls"), floor, threshold,
                                                 nearly_all_null=r.get("nearly_all_null", "").upper() == "Y")
        row = {
            "table": t, "column_id": r.get("column_id", ""), "column": r["column_name"],
            "data_type": r.get("data_type", ""), "length": r.get("data_length", ""),
            "precision": r.get("data_precision", ""), "scale": r.get("data_scale", ""),
            "nullable": r.get("nullable", ""),
            # Number of distinct values is a structural cardinality, not a count of
            # patients or events, and is not suppressed (DECISIONS.md D005).
            "num_distinct_stats": r.get("num_distinct", ""),
            "num_nulls_stats": nulls, "non_null_pct": pct, "completeness_flag": flag,
            "stats_last_analyzed": r.get("last_analyzed", ""),
            "comment": ccom.get((t, r["column_name"]), ""),
        }
        columns.append(row)
        if flag in ("under", "indeterminate", "no_stats"):
            under.append(row)

    cons = {r["constraint_name"]: r for r in data["constraints"]}
    ccols = defaultdict(list)
    for r in sorted(data["cons_columns"], key=lambda r: suppress.to_int(r.get("position")) or 0):
        ccols[r["constraint_name"]].append(r["column_name"])
    keys, fks = [], []
    for name, r in sorted(cons.items(), key=lambda kv: (kv[1]["table_name"], kv[0])):
        cols = ", ".join(ccols.get(name, []))
        if r["constraint_type"] in ("P", "U"):
            keys.append({"table": r["table_name"], "constraint": name,
                         "type": "primary" if r["constraint_type"] == "P" else "unique",
                         "columns": cols, "status": r.get("status", ""), "validated": r.get("validated", "")})
        else:
            ref = cons.get(r.get("r_constraint_name", ""), {})
            fks.append({"table": r["table_name"], "constraint": name, "columns": cols,
                        "ref_owner": r.get("r_owner", ""),
                        "ref_table": ref.get("table_name", "(outside schema)"),
                        "ref_columns": ", ".join(ccols.get(r.get("r_constraint_name", ""), [])),
                        "status": r.get("status", ""), "validated": r.get("validated", "")})

    icols = defaultdict(list)
    for r in sorted(data["ind_columns"], key=lambda r: suppress.to_int(r.get("column_position")) or 0):
        icols[r["index_name"]].append(r["column_name"])
    indexes = [{"table": r["table_name"], "index": r["index_name"], "uniqueness": r.get("uniqueness", ""),
                "type": r.get("index_type", ""), "columns": ", ".join(icols.get(r["index_name"], [])),
                "partitioned": r.get("partitioned", ""), "status": r.get("status", "")}
               for r in sorted(data["indexes"], key=lambda r: (r["table_name"], r["index_name"]))]

    # Columns that share a name and type across tables: join candidates to verify, not facts.
    by_name = defaultdict(set)
    for c in columns:
        by_name[(c["column"], c["data_type"])].add(c["table"])
    joins = [{"column": k[0], "data_type": k[1], "n_tables": len(v), "tables": "; ".join(sorted(v))}
             for k, v in sorted(by_name.items(), key=lambda kv: (-len(kv[1]), kv[0])) if len(v) > 1]

    other = [{"object": r["table_name"], "type": r.get("table_type", "")}
             for r in data["tab_comments"] if r["table_name"] not in real_tables]

    return {
        "tables": (tables, list(tables[0]) if tables else ["table"]),
        "columns": (columns, list(columns[0]) if columns else ["table"]),
        "columns_under_floor": (under, list(columns[0]) if columns else ["table"]),
        "keys": (keys, ["table", "constraint", "type", "columns", "status", "validated"]),
        "foreign_keys": (fks, ["table", "constraint", "columns", "ref_owner", "ref_table",
                               "ref_columns", "status", "validated"]),
        "indexes": (indexes, ["table", "index", "uniqueness", "type", "columns", "partitioned", "status"]),
        "join_candidates": (joins, ["column", "data_type", "n_tables", "tables"]),
        "other_objects": (other, ["object", "type"]),
    }


def md_table(rows: list[dict], fields: list[str], limit: int | None = None) -> str:
    if not rows:
        return "_None found._\n"
    shown = rows[:limit] if limit else rows
    out = ["| " + " | ".join(fields) + " |", "|" + "---|" * len(fields)]
    out += ["| " + " | ".join(str(r.get(f, "")).replace("|", "/") for f in fields) + " |" for r in shown]
    if limit and len(rows) > limit:
        out.append(f"\n_{len(rows) - limit} more rows in the CSV._")
    return "\n".join(out) + "\n"


def report(db: dict, out: dict, manifest: dict, csv_dir: Path, floor: float, when: str, sha: str) -> str:
    tables, columns = out["tables"][0], out["columns"][0]
    under = out["columns_under_floor"][0]
    rel = csv_dir.relative_to(ROOT) if csv_dir.is_relative_to(ROOT) else csv_dir
    no_stats = [t for t in tables if t["num_rows_stats"] == ""]
    analysed = sorted(t["stats_last_analyzed"] for t in tables if t["stats_last_analyzed"])
    size_note = ("from segment views" if manifest.get("segments", {}).get("status") == "ok" else
                 "NOT AVAILABLE: the account can read neither DBA_SEGMENTS nor its own USER_SEGMENTS "
                 "for this schema. Block counts from table statistics are in tables.csv; ask the DBA for sizes")
    by_flag = defaultdict(list)
    for c in under:
        by_flag[c["completeness_flag"]].append(c)
    cfields = ["table", "column", "data_type", "num_nulls_stats", "non_null_pct", "stats_last_analyzed"]
    lines = [
        f"# Data audit, step 1 (dictionary): {db['id']}",
        "",
        f"Date {when}. Engine {db.get('engine')}. Schema `{db.get('schema')}`. Code commit `{sha}`.",
        f"All numbers below come from the CSV files in `{rel}/`.",
        "",
        "## What this is and is not",
        "",
        "- Source: the data dictionary only. No data table was read, so the cost to the database was negligible.",
        "- Row counts and null counts are **optimizer statistics**, which are estimates as of the "
        "date each table was last analysed. They are not live counts.",
        "- Counts under 10 are shown as `<10`. Where a null count is suppressed, completeness is given as a bound.",
        "- Column minimum and maximum statistics and histograms were not read, because they hold real values.",
        "- Not covered here: code systems, coverage over time, per-event volumes, notes, deaths and "
        "data-quality flags (Phase 1 steps 2 to 7). Those need costed queries on data tables.",
        "",
        "## Summary",
        "",
        f"- Tables: {len(tables)}. Columns: {len(columns)}. Other objects (views etc.): {len(out['other_objects'][0])}.",
        f"- Tables without statistics (row count unknown): {len(no_stats)}.",
        f"- Statistics dates range from {analysed[0] if analysed else 'n/a'} to {analysed[-1] if analysed else 'n/a'}.",
        f"- Partitioned tables: {sum(1 for t in tables if t['partitioned'].upper() == 'YES')}.",
        f"- Primary or unique keys: {len(out['keys'][0])}. Declared foreign keys: {len(out['foreign_keys'][0])}.",
        f"- Sizes on disk: {size_note}.",
        f"- Columns under {floor:.0%} complete: {len(by_flag['under'])}. "
        f"Indeterminate: {len(by_flag['indeterminate'])}. No statistics: {len(by_flag['no_stats'])}.",
        "",
        "## Tables (largest first by statistics row count)",
        "",
        md_table(tables, ["table", "num_rows_stats", "stats_last_analyzed", "bytes_on_disk", "blocks",
                          "partitioned", "partitioning_type", "partition_key", "partition_count"], 60),
        "## Keys",
        "",
        md_table(out["keys"][0], ["table", "type", "columns", "status", "validated"], 80),
        "## Declared foreign keys (how tables join)",
        "",
        md_table(out["foreign_keys"][0], ["table", "columns", "ref_table", "ref_columns", "status"], 80),
        "## Join candidates (same column name and type in several tables)",
        "",
        "These are leads to verify, not confirmed joins.",
        "",
        md_table(out["join_candidates"][0], ["column", "data_type", "n_tables", "tables"], 40),
        f"## GATE 1 list: columns under {floor:.0%} complete",
        "",
        md_table(by_flag["under"], cfields, 200),
        "### Completeness indeterminate (table too small to state a bound)",
        "",
        md_table(by_flag["indeterminate"], cfields, 100),
        "### Columns without statistics (completeness unknown)",
        "",
        md_table(by_flag["no_stats"], ["table", "column", "data_type"], 100),
        "## Dictionary queries run",
        "",
        md_table([{"query": k, **{f: v.get(f, "") for f in ("status", "alternative", "rows")}}
                  for k, v in manifest.items()], ["query", "status", "alternative", "rows"]),
    ]
    return "\n".join(lines)


def run(db_id: str, when: str | None = None, registry: Path | None = None,
        results_root: Path | None = None, docs_root: Path | None = None) -> Path:
    cfg = project()
    floor, threshold = float(cfg.get("completeness_floor", 0.60)), int(cfg.get("small_cell_threshold", 10))
    db = database(db_id, registry)
    adapter = get_adapter(db)
    when = when or date.today().isoformat()
    csv_dir = (results_root or ROOT / "results" / "audit") / db_id / when
    doc_dir = (docs_root or ROOT / "docs" / "audits") / db_id
    with tempfile.TemporaryDirectory() as tmp:  # raw output never persists
        data, manifest = fetch(adapter, Path(tmp))
    out = build(data, floor, threshold)
    for name, (rows, fields) in out.items():
        write_csv(csv_dir / f"{name}.csv", rows, fields)
    sha = runlog.commit()
    (csv_dir / "manifest.json").write_text(json.dumps(
        {"database": db_id, "date": when, "step": "phase1-step1-dictionary", "commit": sha,
         "dirty_tree": runlog.dirty(), "queries": manifest}, indent=2), encoding="utf-8")
    doc_dir.mkdir(parents=True, exist_ok=True)
    doc = doc_dir / f"data_audit_{when}.md"
    doc.write_text(report(db, out, manifest, csv_dir, floor, when, sha), encoding="utf-8")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", required=True, help="database id in registry/databases.yaml")
    ap.add_argument("--date", help="override the report date (YYYY-MM-DD)")
    args = ap.parse_args(argv)
    cmd = "python -m src.audit.dictionary " + " ".join(argv if argv is not None else sys.argv[1:])
    with runlog.logged(cmd, f"results/audit/{args.db}/", note="dictionary only; no table scan"):
        doc = run(args.db, args.date)
    print(f"report: {doc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
