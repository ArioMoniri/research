# Run log

One row per run: every query against a database, every script that writes to `results/`, every training or evaluation run, every review round. Before a query that scans a large table, add a row with status `ESTIMATE` giving the expected cost.

| When | Command | Commit | Duration | Output | Status | Note |
|---|---|---|---|---|---|---|
| 2026-11-19 12:09 UTC | `python -m src.audit.dictionary --db vivax-oracle-01` | no-commit+dirty | 0.0s | results/audit/vivax-oracle-01/ | FAILED | ConfigError: database schema is not set. Ask the project lead for it and record it in the registry or configs/project.yaml. Do not guess. |
| 2026-11-19 12:12 UTC | `python -m pytest -q` | b35e5855b71f | 0.2s | (none) | ok | 36 tests pass; synthetic metadata fixtures only; no database contacted |
| 2026-11-19 12:13 UTC | `python scripts/new_study.py --idea P1 --short-name transportability --dest <scratch>` | b35e5855b71f | 0.3s | (throwaway clone, deleted) | ok | Scaffold test in a throwaway clone: refused while P1 was "proposed"; built once approved there; its pre-commit hook blocked a CSV outside results/. Hub registry unchanged |
| 2026-11-19 13:05 UTC | `python -m pytest -q` | 99a110d18cb0+dirty | 31.7s | (none) | ok | 66 tests pass, including the dictionary audit end to end through the bridge with a fake SQLcl and synthetic metadata; no database contacted |
