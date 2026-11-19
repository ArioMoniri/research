---
description: "Propose new studies from what the audits support and the literature lacks"
argument-hint: "[database id]"
---

Propose new study ideas, for database `$ARGUMENTS` if one is given, otherwise across all audited databases. Follow CLAUDE.md throughout.

1. Read the latest audit report and CSVs for each database in scope. If a database has no audit, say so and stop for that database: an idea cannot be checked against data that has not been profiled.
2. Search recent literature before proposing anything (PubMed, bioRxiv/medRxiv, arXiv, web search). For every paper you rely on, record the DOI or arXiv ID and confirm it resolves. Drop anything you cannot confirm.
3. Propose only ideas the data can support: every required field must exist in the audit and be at least 60% complete. Name the tables and columns. Never propose an idea that needs data the audit does not show.
4. For each idea give: one-line claim, layer (model, test, harness, data), databases and fields needed, the gap in the literature with citations, the main risk, and a rough compute cost.
5. Add each to `registry/ideas.yaml` with status `proposed`, `origin: /suggest-ideas <date>`, and the confirmed citations under `notes`. Do not duplicate an existing idea; say which one it overlaps.
6. Run `python -m src.registry.registry validate`, record the search in RUNLOG.md, commit, and show the lead the list.
