# Start the first research (P1), from database audit to reviewed study prompt

You are working in the Vivax research hub (repository `ArioMoniri/research`, branch `claude/blissful-albattani-s5krm7`). Read `CLAUDE.md` first and follow every rule in it for the whole task. Read `DECISIONS.md` and the last rows of `RUNLOG.md` to see what has been done.

## Goal

Take the first study, P1 (transportability of trajectory models), from nothing measured to a reviewed, runnable study prompt. That means: audit the database, pass GATE 1, finish the audit, fill the P1 prompt from what the audit found, have it reviewed, and stop at GATE 3. You do not export data or train anything in this task.

The output is read by peer reviewers, hospital partners and investors. A wrong number costs more than a slow one. When unsure, measure or ask. Never fill a gap with a plausible guess.

## What exists

- The hub: rules, 14 review agents, 7 slash commands, registries, audit code, tests.
- The database `vivax-oracle-01` (Oracle, de-identified hospital records) is reachable only through the bridge: `tools/vivax_bridge.py` runs on the lead's Mac over VPN and answers queries that you commit with `src/bridge/client.py`.
- Nothing about the database has been measured. The figures under `unverified_description` in `registry/databases.yaml` are claims to test.
- `prompts/phase1_audit.md` holds the audit instructions in full. `prompts/p1_transportability.md` is the P1 draft with unfilled `[AUDIT: ...]` and `[LEAD: ...]` slots.

## Part A: checks before the first query

1. `python -m pytest -q` and `python -m src.registry.registry validate`. Stop if either fails.
2. `bash scripts/install_hooks.sh`.
3. The repository must be private. If the bridge client refuses because it is public, stop and tell the lead. Do not look for another route.
4. Send `SELECT 1 AS ok FROM dual` through the bridge in dictionary mode. If there is no answer in 15 minutes, stop and ask the lead whether the bridge is running and on the VPN.

## Part B: audit step 1, then GATE 1

Follow `prompts/phase1_audit.md`, step 1.

1. Run `python -m src.audit.dictionary --db vivax-oracle-01`.
2. From its output files only, add to the report the candidate mapping: patient table and key; tables for diagnoses, medications, labs, notes, encounters and deaths; the site column; the date column of each event table. Give the evidence for each. Where two readings are possible, list both.
3. Update `registry/databases.yaml` (`last_audit`, paths), log the run, commit and push.

**GATE 1: stop.** Show the lead the audit summary, every field under 60% complete, tables without statistics, and the candidate mapping. Ask the lead to confirm the mapping and to answer the open questions in "Decisions waiting on the lead" below. Do not continue without a yes.

## Part C: audit steps 2 to 7 (only after GATE 1)

Follow `prompts/phase1_audit.md`, steps 2 to 7: code systems for diagnoses, drugs, labs and procedures; coverage over time per site and follow-up per patient; volumes per event type; notes (counts, lengths and language only); deaths and their source; quality flags.

For every query on a data table:

- Aggregate mode through the bridge, with the group-size column named.
- First write a RUNLOG.md row with status `ESTIMATE`: table, size and rows from step 1, sampling, expected duration. Over ten minutes: stop and ask.
- Start each new query shape on a 1% sample or one partition.
- Never select a patient identifier, note text or other free text, and never rename a column to pass the bridge's filters. If the bridge refuses a query and you do not understand why, report it; do not rephrase the query to get past it.

Then: mark each `unverified_description` claim as confirmed, contradicted or not yet measured; add the patient-ID format as a regular expression to `configs/patient_id_patterns.txt`; commit and push; give the lead a short report.

## Part D: fill and review the P1 prompt

Run `/review-idea P1`. In particular:

1. Check feasibility first. If any field P1 needs is missing or under 60% complete, stop and tell the lead which one. Do not choose a proxy.
2. Fill every `[AUDIT: ...]` slot in `prompts/p1_transportability.md` from files under `results/audit/`. Cite the file for each value.
3. Propose, do not decide, the `[LEAD: ...]` items: the eight conditions with definitions and event counts per period (with the clinician-reviewer), the split dates (from the events-per-year table), the cohort inclusion rule, and the three model sizes. Show the evidence for each proposal.
4. Confirm the Delphi and ETHOS references by DOI or arXiv ID with the citation-checker. If one cannot be confirmed, say so; do not describe the method from memory.
5. Pass the prompt through prompt-enhancer, then clinician-reviewer, ml-reviewer, methods-reviewer and skeptic. Save each round in `prompts/reviews/`. Revise until none has a blocking objection. If the same objection survives three rounds, bring it to the lead.
6. Set the registry: `prompt_path`, `fields_verified_against_audit: true`, verdicts, status `reviewed`. Only the lead sets `approved`.

**GATE 3: stop.** Show the lead the P1 prompt, the reviewer verdicts and what the reviewers still doubt. No export, no training and no study repository until the lead approves. (The export plan is GATE 2 and is a separate task.)

## Decisions waiting on the lead (ask at GATE 1 if still open)

- Site column, or "unknown"; GPU host and extract path; who approves gates; ethics approval reference.
- Show zero counts as `<10` too? (`DECISIONS.md` D004)
- Keep `EXPLAIN PLAN` blocked and estimate cost from dictionary sizes? (D008)
- Is the database account read-only, confirmed by the DBA? (D009)
- Bridge: ask before each aggregate query, or `--auto`? (D015)

## Always

- Log every run in `RUNLOG.md`, every choice in `DECISIONS.md`, every figure and table in `PROVENANCE.csv`.
- Commit before a run that produces results. Run `python scripts/precommit_check.py --all` before every push.
- Stop on: a gate; a password prompt; the repository found public; a query estimated over ten minutes; an `UNSET` value you need; two plausible readings of what a table or column means.
- Report at each stop: what was done, where the outputs are, what could not be done and why, and the decision needed. Lead with anything that changes the plan.
