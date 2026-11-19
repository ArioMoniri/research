---
description: "Create the private study repository for an approved idea and begin Phase 5 there"
argument-hint: "<idea id>"
---

Start the study for idea `$ARGUMENTS`. Follow CLAUDE.md throughout.

1. Check that the idea's status in `registry/ideas.yaml` is `approved`. If it is anything else, stop: only the lead approves.
2. Check that GATE 2 (export) and GATE 3 (prompts and verdicts) have been passed and are recorded in DECISIONS.md. If not, stop.
3. Propose the repository name `vivax-<idea id>-<short-name>` and a one-sentence description. **Show both to the lead and wait for a yes.**
4. Commit the hub so the tree is clean, then scaffold: `python scripts/new_study.py --idea <id> --short-name <short-name> --dest <parent directory>`. This copies the enhanced prompt and its reviews, CLAUDE.md rules, the agents, the safety check with hooks, and the log scaffold, and writes `HUB_COMMIT`.
5. Create the GitHub repository with the gh CLI, which the lead authenticates. Always private, under the lead's own account: `gh repo create <name> --private --description "<description>" --source <path> --remote origin`. Never pass `--public`. Never change a repository's visibility afterwards.
6. Run `python scripts/precommit_check.py --all` in the study repository. Push only if it passes.
7. Add the study to `registry/studies.yaml` (repo URL, hub commit, venue null, phase `5.1 run`), set the idea's `study_repo` and status `running`, validate, and commit the hub.
8. Continue in the study repository with Phase 5, step 1. Nothing is submitted, posted or made public by you (GATE 4).
