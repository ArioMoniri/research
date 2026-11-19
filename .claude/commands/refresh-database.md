---
description: "Rerun a database audit, diff it against the previous one and list affected ideas and studies"
argument-hint: "<database id>"
---

Refresh the audit of database `$ARGUMENTS`. Follow CLAUDE.md throughout.

1. Find the previous audit date in `registry/databases.yaml` (`last_audit`). If there is none, say so and run `/add-database` steps 3 onward instead.
2. Rerun the audit with the data-auditor agent, starting with `python -m src.audit.dictionary --db <id>`. Rerun any later audit steps that exist for this database, each with its cost estimate logged first. The report is written with today's date; earlier reports are kept.
3. Diff: `python -m src.audit.diff --db <id> --old <previous date> --new <today>`. Summarise new and dropped tables and columns, row growth and completeness changes.
4. For every idea in `registry/ideas.yaml` and study in `registry/studies.yaml` that uses this database, compare its required `fields` with the diff. List each one whose fields changed, and say whether its prompt needs revising and why. A field that has fallen under 60% complete is a stop condition for that idea (rule 6).
5. Re-run the privacy re-assessment steps that depend on the data (smallest group sizes, rare values) and note any change in `docs/audits/<id>/privacy_assessment.md`.
6. Update `last_audit` and paths in the registry, log the runs, commit, and report in the standard form.
