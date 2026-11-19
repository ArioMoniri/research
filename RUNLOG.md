# Run log

One row per run: every query against a database, every script that writes to `results/`, every training or evaluation run, every review round. Before a query that scans a large table, add a row with status `ESTIMATE` giving the expected cost.

| When | Command | Commit | Duration | Output | Status | Note |
|---|---|---|---|---|---|---|
| 2026-11-19 12:09 UTC | `python -m src.audit.dictionary --db vivax-oracle-01` | no-commit+dirty | 0.0s | results/audit/vivax-oracle-01/ | FAILED | ConfigError: database schema is not set. Ask the project lead for it and record it in the registry or configs/project.yaml. Do not guess. |
