---
description: "Register a new database, then audit it, assess privacy and write its node card"
argument-hint: "<connection alias>"
---

Register the database reached through the connection alias `$ARGUMENTS`, then run Phases 1 to 3 for it. Follow CLAUDE.md throughout.

1. **Register.** Ask the lead for anything not already known: a short id, engine (oracle, postgresql, sqlserver, mysql), connection mode, schema, owner, site column (or "unknown"), and ethics scope (approval reference, whether it covers publication, whether pooling with other databases is allowed). Add the entry to `registry/databases.yaml`. Store the alias only, never a credential. Leave anything unknown as `UNSET`. Run `python -m src.registry.registry validate`.
2. **Check the engine.** If `src/db/<engine>.py` is a stub, stop and tell the lead the adapter must be implemented first; offer to implement it against `src/db/base.py`.
3. **Phase 1, audit.** Hand the data-auditor agent the database id. Step 1 is `python -m src.audit.dictionary --db <id>`. **Stop at GATE 1**: show the lead the audit summary and every field under 60% complete. Continue to steps 2 to 7 only on approval, each with a cost estimate logged first.
4. **Record patient-ID format.** If the audit identifies the patient-ID format, add a regular expression for it to `configs/patient_id_patterns.txt` (the pattern, never an example value).
5. **Phase 2, privacy.** Write `docs/audits/<id>/privacy_assessment.md` as specified in the project brief.
6. **Phase 3, node card.** Write `docs/audits/<id>/node_card.md`. Aggregates only.
7. **Update** `last_audit`, `audit_path`, `audit_results_path`, `privacy_path` and `node_card_path` in the registry; log runs in RUNLOG.md and choices in DECISIONS.md; commit.
8. **Report** in the standard form: done, outputs, not done and why, decision needed.
