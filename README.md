# Vivax research hub

The hub for Vivax's research programme on patient world models. It is not one study: it keeps the registries of databases, research ideas and studies, the audit code, the review agents and the study prompts. Each study that goes ahead gets its own private repository, created from here.

**No patient data and no credentials are stored here.** Read `CLAUDE.md` for the rules every session follows.

## State

Run `/status` in Claude Code, or:

```bash
python -m src.registry.registry status
```

## Connecting to the database through the bridge

The Claude session that runs this work may not be able to reach the database. `tools/vivax_bridge.py` is one file that runs on a machine that can (for example a Mac on the hospital VPN) and serves each query the session sends. It needs Python 3, git with access to this repository, and SQLcl with a saved connection. It asks for no password.

**The repository must be private first.** Queries and results travel through it. The bridge refuses to run while it is public.

```bash
python3 vivax_bridge.py setup
```

```bash
python3 vivax_bridge.py run
```

By default it shows each query that reads data tables and waits for `y`. `run --auto` removes that prompt. Dictionary queries are always automatic. Stop it with Ctrl-C. What it enforces is listed at the top of the file and in `DECISIONS.md` D015.

On the session side:

```bash
python -m src.audit.dictionary --db vivax-oracle-01
```

## Running directly on a machine that reaches the database

Set `connection.transport: direct`, the connection mode, alias and schema in `registry/databases.yaml`, then:

```bash
bash scripts/install_hooks.sh
```

```bash
python -m src.db.smoke --db vivax-oracle-01
```

```bash
python -m src.audit.dictionary --db vivax-oracle-01
```

Either way, stop at GATE 1 and review `docs/audits/vivax-oracle-01/`.

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
