# {{STUDY_NAME}}: rules for every session and subagent

This is the study repository for idea {{IDEA_ID}} ({{IDEA_TITLE}}), created from
the Vivax research hub at commit `{{HUB_COMMIT}}`. The hub keeps the registries;
this repository holds code, configs, prompts, logs, aggregate results, figures
and the manuscript. **It never holds data.**

The output is read by peer reviewers, hospital partners and investors. A wrong
number costs more than a slow one. **When unsure, measure or ask. Never fill a
gap with a plausible guess.**

## Rules that hold for the whole project

The data describes real people, even after de-identification, and every result
must survive an audit.

1. **Nothing patient-level reaches your context or the logs.** Interactive
   queries return aggregates only. Any count under 10 is shown as `<10`. Code
   that reads rows runs as a script and writes to disk; you read its aggregate
   outputs, not the rows. Never display the content of a clinical note.
2. **The database is read-only.** No DDL or DML, ever. All SQL goes through
   `src/db/` (which checks it with `src/db/guard.py`), never ad hoc.
3. **Cost before scan.** Before any query that scans a large table, estimate its
   cost (table size from the dictionary, plan) and write the estimate in
   RUNLOG.md. Prefer dictionary statistics, `SAMPLE`, `APPROX_COUNT_DISTINCT`
   and partition-wise queries. Ask the project lead before running anything
   expected to take more than ten minutes, and schedule heavy work off-hours.
4. **Patients are split, not rows, and splits are by time.** The held-out period
   is not touched until a paper's final evaluation step.
5. **Every reported number comes from a file in `results/`** produced by code at
   a recorded git commit, with three seeds and a 95% bootstrap interval where a
   model is involved. Never write a number or a citation from memory. If a
   citation cannot be confirmed by DOI or arXiv ID, drop it.
6. **Stop and ask at each GATE.** Also stop if a required field is missing or
   under 60% complete, rather than choosing a proxy.
7. **Keep three logs current:** `RUNLOG.md` (every run: command, commit,
   duration, output path), `DECISIONS.md` (each choice and why),
   `PROVENANCE.csv` (each figure and table mapped to code, commit and data
   snapshot).

## Further standing rules

- **Credentials.** Never print, log or store a credential. Connections use a
  saved SQLcl connection or wallet alias named in `registry/databases.yaml`. If
  a password prompt appears, stop and let the project lead type it.
- **UNSET.** A value of `UNSET` in `registry/` or `configs/` means the lead has
  not supplied it. Stop and ask; do not substitute.
- **Unverified description.** Figures under `unverified_description` in the
  database registry come from the kickoff brief and have not been measured. Do
  not cite them in any document.
- **No data in git.** Run `bash scripts/install_hooks.sh` once per clone. The
  check in `scripts/precommit_check.py` runs before every commit and push. Do
  not bypass it.
- **Nothing public.** You do not submit to a journal, post a preprint, make a
  repository public or change a repository's visibility. Study repositories are
  created private, and only after the lead has agreed to the name and
  description.
- **Cross-database work.** Each database is a site. Data from different
  databases is never joined or pooled unless `ethics.pooling_with_other_databases`
  in the registry allows it. The default is separate training with federated or
  merged models.
- **Runs on a clean tree.** Commit before a run that produces results, so the
  commit in RUNLOG.md identifies the code exactly.

## Gates

| Gate | Stop and show the lead | Before |
|---|---|---|
| GATE 1 | Audit summary and the list of fields under 60% complete | Phases 2 to 4 |
| GATE 2 | Export plan, estimated runtime, transfer route to the GPU host | Moving any data |
| GATE 3 | The six study prompts and reviewer verdicts | Any training |
| GATE 4 | Submission package and a one-page summary of remaining reviewer doubts | Anything leaving the private repository |

## Reporting to the lead

At the end of each phase: what was done, where the outputs are, what could not
be done and why, and the decision needed. Lead with anything that changes the
plan.

## Writing

Plain, specific prose. Concrete claims with our actual numbers. No filler, no
inflated adjectives, no stock phrases. State limitations plainly.

## Phase 5 in this repository

1. Run the enhanced prompt in `prompts/`. Log every run.
2. journal-scout proposes three venues; the lead chooses one; format to it from then on.
3. figure-maker builds figures from `results/`; figure-reviewer checks them.
4. writer drafts; every sentence with a number points to `PROVENANCE.csv`.
5. editor revises for plain, specific prose, with the venue's AI-use disclosure and the human authors' contributions.
6. stats-verifier, citation-checker and the four reviewers report; fix and repeat until nothing blocking remains. Keep every report in `manuscripts/<paper>/reviews/`.
7. repro-verifier reruns the pipeline from a fresh clone.
8. Assemble the submission package and stop at GATE 4.
