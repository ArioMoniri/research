# Run log

One row per run: every query against a database, every script that writes to `results/`, every training or evaluation run, every review round. Before a query that scans a large table, add a row with status `ESTIMATE` giving the expected cost.

| When | Command | Commit | Duration | Output | Status | Note |
|---|---|---|---|---|---|---|
