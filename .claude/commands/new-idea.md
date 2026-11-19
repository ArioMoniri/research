---
description: "Turn the lead's idea into a registry entry and check it against the audits"
argument-hint: "\"<description>\""
---

The lead's idea: $ARGUMENTS

Follow CLAUDE.md throughout.

1. Restate the idea as a one-line claim that could be shown false. Ask one question if the claim is ambiguous; otherwise proceed.
2. Choose the layer (model, test, harness, data) and list the fields the idea needs.
3. Check feasibility against the latest audit of each database it needs: does each field exist, under which table and column, and how complete is it? If a database has no audit yet, say the check cannot be done.
4. Tell the lead plainly if the data does not support the idea: which field is missing or under 60% complete, and what would have to change. Do not offer a proxy as if it were the field.
5. Add the entry to `registry/ideas.yaml` with the next free id, status `proposed`, `origin: lead, <date>`, and the feasibility result under `notes`. If the idea is not feasible, still record it, with the reason, so it is not proposed again.
6. Run `python -m src.registry.registry validate` and commit.
