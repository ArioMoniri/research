---
description: "Write the study prompt for an idea, enhance it and run the four reviewers"
argument-hint: "<idea id>"
---

Review idea `$ARGUMENTS`. Follow CLAUDE.md throughout.

1. Read the idea in `registry/ideas.yaml` and the latest audit for each database it needs. If any required field is missing or under 60% complete, stop and tell the lead (rule 6).
2. Write `prompts/<id lower-case>_<short-name>.md` from what the audit found: real table and column names, measured coverage, the time split with dates, outputs under `results/`.
3. Pass the prompt to the **prompt-enhancer** agent.
4. Send the enhanced prompt to **clinician-reviewer**, **ml-reviewer**, **methods-reviewer** and **skeptic** in parallel. Give each the prompt and the audit, not your opinion of them.
5. Save each report as `prompts/reviews/<id>_round<N>_<reviewer>.md`. Revise the prompt and repeat until no reviewer has a blocking objection. If the same objection survives three rounds, stop and bring it to the lead instead of arguing it away.
6. In the registry set `prompt_path`, `fields_verified_against_audit: true`, `verdicts` (verdict, round and report path per reviewer) and status `reviewed`. Only the lead sets `approved`.
7. Validate the registry, record the rounds in RUNLOG.md and choices in DECISIONS.md, commit, and show the lead the prompt, the verdicts and what the reviewers still doubt.
