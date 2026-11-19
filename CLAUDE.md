# Vivax research hub: rules for every session and subagent

Vivax is a small lab in Istanbul building a world model for healthcare: a model
that learns how patients change over time and under treatment. This repository
is the **hub**. It holds the registries of databases, ideas and studies, the
audit code, the review agents and the study prompts. Each study that goes ahead
gets its own repository, created from here.

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
- **The bridge.** This session may not be able to reach the database. Queries
  then go through `src/bridge/client.py` to `tools/vivax_bridge.py`, which runs on
  a machine that can. Every request is a committed file in `bridge/requests/`
  and every answer a committed, filtered file in `results/bridge/`. Two modes
  only: `dictionary` (dictionary views) and `aggregate` (must aggregate, must
  name its group-size column; groups under 10 are removed). Never try to get a
  row, an identifier or note text through it, and never alias a column to slip
  past its filters. State the cost estimate in every aggregate request.
- **Private repository first.** Queries and results are pushed to GitHub, so the
  hub repository must be private before anything goes through the bridge. Both
  ends refuse while it is public. Only the lead changes visibility.
- **Runs on a clean tree.** Commit before a run that produces results, so the
  commit in RUNLOG.md identifies the code exactly.

## Gates

| Gate | Stop and show the lead | Before |
|---|---|---|
| GATE 1 | Audit summary and the list of fields under 60% complete | Phases 2 to 4 |
| GATE 2 | Export plan, estimated runtime, transfer route to the GPU host | Moving any data |
| GATE 3 | The six study prompts and reviewer verdicts | Any training |
| GATE 4 | Submission package and a one-page summary of remaining reviewer doubts | Anything leaving the private repository |

## Layout

| Path | Holds |
|---|---|
| `registry/` | `databases.yaml`, `ideas.yaml`, `studies.yaml`. No patient data, no credentials |
| `configs/` | Project settings, patient-ID patterns for the safety check |
| `src/db/` | Engine adapters (Oracle implemented; PostgreSQL, SQL Server, MySQL are stubs) and the read-only guard |
| `src/audit/` | Audit code. Writes `results/audit/<db>/<date>/` and `docs/audits/<db>/` |
| `src/registry/` | Registry validation and the `/status` table |
| `tools/vivax_bridge.py`, `src/bridge/` | The bridge (runs near the database) and its client (runs here) |
| `bridge/requests/`, `results/bridge/` | Each query sent through the bridge and its filtered answer |
| `sql/` | Reviewed SQL for later audit steps and the export |
| `prompts/`, `prompts/reviews/` | Study prompts and each review round |
| `results/`, `figures/`, `manuscripts/`, `docs/`, `logs/` | Aggregate outputs only |
| `.claude/agents/`, `.claude/commands/` | Review agents and slash commands |
| `templates/study/`, `scripts/new_study.py` | Scaffold for study repositories |

## Commands

`/add-database`, `/refresh-database`, `/suggest-ideas`, `/new-idea`,
`/review-idea`, `/start-study`, `/status`. Each updates the registries and logs.

Useful checks:

```bash
python -m src.registry.registry validate
python -m src.registry.registry status
python -m pytest -q
python scripts/precommit_check.py --all
```

## Reporting to the lead

At the end of each phase: what was done, where the outputs are, what could not
be done and why, and the decision needed. Lead with anything that changes the
plan.

## Writing

Plain, specific prose. Concrete claims with our actual numbers. No filler, no
inflated adjectives, no stock phrases. State limitations plainly.
