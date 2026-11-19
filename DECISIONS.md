# Decisions

Each choice and why. Newest last. Entries are not edited after the fact; a reversal is a new entry that names the one it replaces. "Needs lead" marks a choice made provisionally that the project lead should confirm.

## D001 (2026-11-19) Hub built in a cloud session, not on the database machine
The kickoff session ran in a cloud container with no SQLcl and no route to the database, and the five bracketed values in the brief (connection alias, schema, GPU host and extract path, site column, project lead) were not filled. Phases 0 and 0b were completed here. Phase 1 step 1 was implemented and tested on synthetic metadata but **not run**. No database was contacted. Values not supplied are recorded as `UNSET` and code refuses to run until they are filled.

## D002 (2026-11-19) Per-database, dated audit paths
The brief names `docs/data_audit.md` and `results/audit/*.csv`. Because the hub must hold several databases and dated refreshes that can be diffed, audits are written to `docs/audits/<db id>/data_audit_<date>.md` and `results/audit/<db id>/<date>/`. Privacy assessments and node cards go to `docs/audits/<db id>/`. `docs/README.md` indexes them. Needs lead: say if the flat paths are required as well.

## D003 (2026-11-19) Step 1 reads the dictionary only
Row counts, null counts and distinct counts come from optimizer statistics, so step 1 costs the database almost nothing and scans no data table. The price is that these are estimates as of each table's last statistics date, and are labelled so everywhere. Tables without statistics are reported as "row count unknown"; no `COUNT(*)` is run to fill the gap without a cost estimate and, if over ten minutes, the lead's approval.

## D004 (2026-11-19) Suppression applied literally, including zero
Rule 1 says any count under 10 is shown as `<10`. Zero is under 10, so zeros are also shown as `<10`. Where a null count is suppressed, completeness is shown as a bound (for example `>=99.1`) that does not let the count be recovered. Cost: a column with no nulls cannot be told from one with a few. Needs lead: confirm, or allow true zeros to be shown.

## D005 (2026-11-19) Structural cardinalities are not suppressed
The number of distinct values in a column, and counts of tables, columns, partitions and blocks, describe the schema rather than groups of patients, and are needed to recognise categorical columns and plan queries. They are shown as they are. Needs lead: confirm.

## D006 (2026-11-19) Column min/max statistics and histograms are never read
Oracle stores the lowest and highest value of each column, and histogram endpoints, in the dictionary. These are real data values (a date, an identifier, a code), so the audit does not select them. A test enforces this.

## D007 (2026-11-19) SQLcl logon form is unverified
SQLcl could not be installed or run here. The SQLcl 25.1 user guide confirms the `-S` and `-L` options and the `/` logon form, but does not document how to name a saved connection at launch. The adapter defaults to `sql -S -L -name <alias>` (mode `saved`) or `sql -S -L /@<alias>` (mode `wallet`); both are unverified. `python -m src.db.smoke --db <id>` must pass on the database machine before the audit runs. If neither form works, set `connection.sqlcl_logon` in the registry to the arguments that do. The adapter rejects anything shaped like `user/password`. Standard input is closed, so a password prompt makes the run fail rather than hang; the operator is told to stop for the lead.
Source: https://docs.oracle.com/en/database/oracle/sql-developer-command-line/25.1/sqcug/startup-sqlcl-settings.html (read 2026-11-19).

## D008 (2026-11-19) EXPLAIN PLAN conflicts with the read-only rule
Rule 3 asks for a plan before a large scan. In Oracle, `EXPLAIN PLAN` writes rows to a plan table, which is DML, and rule 2 forbids DML without exception. The read-only guard therefore blocks `EXPLAIN PLAN`. Until the lead decides, cost estimates use dictionary sizes and row counts, partition metadata and index definitions. Needs lead: either allow `EXPLAIN PLAN` (with the DBA's agreement, into the session's temporary plan table) or confirm dictionary-based estimates are enough.

## D009 (2026-11-19) Two layers of read-only protection
`src/db/guard.py` allows a single `SELECT` or `WITH` statement and rejects write, DDL, PL/SQL and locking keywords. This is a second line of defence. The first should be a database account that holds only read privileges. Needs lead: ask the DBA to confirm the account's privileges.

## D010 (2026-11-19) Ideas seeded with plain-language field needs
The six studies are in `registry/ideas.yaml` as `proposed`, with required fields in plain terms (for example "lab results with numeric values and units") and `fields_verified_against_audit: false`. They are mapped to real tables and columns by `/review-idea` after the audit. The brief's figures for the database (patients, sites, years) are stored under `unverified_description` and must not be cited.

## D011 (2026-11-19) Turkish national ID numbers are always blocked from git
Besides patterns learned from the audit (`configs/patient_id_patterns.txt`, empty until then), the safety check blocks any 11-digit number that passes the TC Kimlik checksum. It reports the file and line, never the value.

## D012 (2026-11-19) Study repositories are scaffolded locally, created remotely by command
`scripts/new_study.py` builds the study repository on disk and refuses unless the idea is `approved` and the hub tree is clean. Creating the GitHub repository is a separate step in `/start-study`, always `--private`, and only after the lead agrees to the name and description. In this cloud session GitHub access is limited to the hub repository, so `/start-study` must run where the lead has authenticated `gh`.
