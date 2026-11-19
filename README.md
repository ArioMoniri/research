# Vivax research hub

The hub for Vivax's research programme on patient world models. It is not one study: it keeps the registries of databases, research ideas and studies, the audit code, the review agents and the study prompts. Each study that goes ahead gets its own private repository, created from here.

**No patient data and no credentials are stored here.** Read `CLAUDE.md` for the rules every session follows.

## State

Run `/status` in Claude Code, or:

```bash
python -m src.registry.registry status
```

## First steps on the database machine

1. Fill the `UNSET` values in `registry/databases.yaml` and `configs/project.yaml`.
2. Install the safety hooks:

```bash
bash scripts/install_hooks.sh
```

3. Prove the connection works without a password prompt (reads no patient table):

```bash
python -m src.db.smoke --db vivax-oracle-01
```

4. Run the dictionary audit (Phase 1, step 1; scans no data table):

```bash
python -m src.audit.dictionary --db vivax-oracle-01
```

Then stop at GATE 1 and review `docs/audits/vivax-oracle-01/`.

## Commands

| Command | Does |
|---|---|
| `/add-database <alias>` | Registers a database, then audit, privacy assessment and node card |
| `/refresh-database <id>` | Reruns the audit, diffs it, lists affected ideas and studies |
| `/suggest-ideas [<id>]` | Proposes studies the audits support and the literature lacks |
| `/new-idea "<description>"` | Registers your idea and checks it against the audits |
| `/review-idea <id>` | Writes the study prompt, enhances it, runs the four reviewers |
| `/start-study <id>` | For an approved idea: creates the private study repository |
| `/status` | One table of everything and the next decision waiting on you |

## Logs

`RUNLOG.md` (every run), `DECISIONS.md` (each choice and why), `PROVENANCE.csv` (each figure and table mapped to code, commit and data snapshot).

## Requirements

Python 3.10 or later with PyYAML; pytest for the tests; SQLcl on the database machine.
