# Prompt: analyse the database (Phase 1 audit)

Paste this into a Claude Code session opened on the hub repository, with the bridge running on the machine that reaches the database.

---

You are running the Phase 1 audit of database `vivax-oracle-01` for the Vivax research hub. Read `CLAUDE.md` first and follow every rule in it. Hand the work to the `data-auditor` agent where it fits.

## Purpose

Find out what the database holds, how it is coded and how complete it is, so that six studies can be designed against facts. Nothing about this database has been measured yet. The figures in `registry/databases.yaml` under `unverified_description` are claims to test, not facts to repeat.

## Before the first query

1. Run `python -m src.registry.registry validate` and `python -m pytest -q`. Stop if either fails.
2. Confirm the hub repository is private. If `src/bridge/client.py` refuses because it is public, stop and tell the lead. Do not look for another route.
3. Confirm the bridge answers: send `SELECT 1 AS ok FROM dual` in dictionary mode.

## How every query is run

- Through the bridge only (`src/bridge/client.py`, or `src/audit/` code that uses it). Never ad hoc.
- `dictionary` mode for dictionary views. `aggregate` mode for data tables: the query must aggregate, name its group-size column, and carry a cost estimate.
- Before each aggregate query, write a RUNLOG.md row with status `ESTIMATE`: table, size and row count from step 1, sampling used, expected duration. If the estimate exceeds ten minutes, stop and ask the lead.
- Prefer `SAMPLE`, `APPROX_COUNT_DISTINCT` and one partition at a time. Start every new query shape on a 1% sample or a single partition.
- Save reviewed SQL under `sql/oracle/audit/`. Write outputs to `results/audit/vivax-oracle-01/<date>/`.
- Never select a patient identifier, a note's text or any free-text column as an output column or a group key. Never rename a column to pass the bridge's filters.

## Step 1: structure (dictionary only)

Run `python -m src.audit.dictionary --db vivax-oracle-01`.

Outputs: `tables.csv`, `columns.csv`, `columns_under_floor.csv`, `keys.csv`, `foreign_keys.csv`, `indexes.csv`, `join_candidates.csv`, `manifest.json`, and `docs/audits/vivax-oracle-01/data_audit_<date>.md`.

Then, from those files only, write a short section in the report that names: the patient table and patient key; the candidate tables for diagnoses, medications, labs, notes, encounters and deaths; the candidate site column; the date column of each event table. Mark each as "candidate" with the evidence (name, type, keys, comments). Where two readings are possible, list both and ask.

**GATE 1. Stop here.** Show the lead the summary, the fields under 60% complete, the tables without statistics, and the candidate mapping. Continue to steps 2 to 7 only after the lead confirms the mapping and approves.

## Steps 2 to 7 (after GATE 1; each needs data tables)

2. **Code systems.** For each candidate code column (diagnoses, drugs, labs, procedures): on a sample, the share of values matching each pattern (ICD-10, ATC, LOINC, SUT procedure codes, anything else as "in-house"), and the 50 most frequent codes with counts. Report the sample fraction with every share.
3. **Coverage.** First and last event date per site; events per year per site; follow-up length per patient in deciles; patients with under 1, 1 to 5, 5 to 10 and over 10 years of history. Follow-up is computed inside the query and only the distribution is returned.
4. **Volumes.** Per event type: patients with at least one event; events per patient in deciles; for labs, the share with a numeric value and the share with a unit.
5. **Notes.** Count, length distribution in deciles, and language share estimated in SQL from character patterns. No text leaves the database.
6. **Deaths.** Whether deaths are recorded, in which table and column, counts per year, and whether the source is the hospital record or an external registry. If the source cannot be established from the data, say so and ask.
7. **Quality flags.** Future dates; impossible ages; exact duplicate events; number of distinct units per lab code for the 50 most frequent lab codes.

After steps 2 to 7, add the patient-ID format (as a regular expression, never an example value) to `configs/patient_id_patterns.txt`.

## Acceptance checks

- Every number in the report traces to a CSV under `results/audit/` and a RUNLOG.md row.
- No output contains a count under 10, an identifier or note text.
- Each claim in `unverified_description` is marked confirmed, contradicted or not yet measured, with the measured value.
- Optimizer estimates and measured values are labelled as such. Sampled values carry their sample fraction.

## Stop conditions

A gate; a password prompt; the repository found public; a query estimated over ten minutes; a bridge refusal you do not understand (report it, do not rephrase the query to get past it); a required field missing or under 60% complete; two plausible readings of what a table or column means.

## Report to the lead

What was done, where the outputs are, what could not be done and why, and the decision needed. Lead with anything that changes the plan.
