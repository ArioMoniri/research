# Prompt P1: transportability of trajectory models (DRAFT, not runnable)

**Status: draft written before the audit.** Project rules require this prompt to be written from what the audit found, then passed through prompt-enhancer and the four reviewers (`/review-idea P1`). Every `[AUDIT: ...]` and `[LEAD: ...]` slot below is unfilled. Do not run this prompt, and do not fill a slot with an estimate.

---

Read `CLAUDE.md` first and follow every rule in it.

## Claim under test

Trajectory models of the Delphi and ETHOS kind, retrained from scratch on our patients, give calibrated and decision-relevant risk estimates for eight conditions in a Turkish multi-site hospital population, and their performance by sex, age and site can be compared with published cohorts.

The study is predictive. It makes no causal claim.

## Inputs

- MEDS extract of `vivax-oracle-01` at `[LEAD: extract path on the GPU host]`, data snapshot `[AUDIT: extract date and hub commit]`. The extract exists only after GATE 2.
- Event types and code systems: diagnoses `[AUDIT: table, code system, share valid ICD-10]`; medications `[AUDIT: code system, ATC mapping coverage]`; labs `[AUDIT: code system, LOINC mapping coverage, share with numeric value and unit]`; deaths `[AUDIT: recorded or not, source]`.
- Demographics: sex `[AUDIT: column, completeness]`, age or birth year `[AUDIT]`, site `[AUDIT: column, number of sites]`.
- Any input under 60% complete is a stop condition, not a reason to pick a proxy.

## Cohort and split

- Inclusion: `[AUDIT: minimum history, age range, justified from the follow-up deciles]`.
- Patients are split, never rows. Split by time: training on events before `[AUDIT: date T1]`, validation between T1 and `[AUDIT: date T2]`, held-out after T2. Dates are chosen from the events-per-year table so each period has enough outcomes, and are frozen in `configs/p1_split.yaml` before any model is trained.
- A patient's outcome window lies entirely in one period. Vocabulary, tokeniser, normalisers and code mappings are fitted on the training period only.
- The held-out period is read once, in the final evaluation step, after the analysis plan is frozen and committed.

## Models

- Two architectures: a Delphi-style model and an ETHOS-style model. Before implementing, confirm each reference by DOI or arXiv ID and record what was reproduced and what was changed.
- Three sizes each: `[LEAD/ML: parameter counts, fixed before training]`.
- Same tokenisation budget, training budget and hyperparameter search for every arm; search described in the config.

## Baselines

Age and sex only; logistic regression on counts of prior codes; gradient-boosted trees on the same features; for each condition, the established clinical score where its inputs exist in our data `[AUDIT: which scores are computable]`.

## Outcomes

Eight conditions, chosen before training by the clinician-reviewer and the lead from the audit: each must be decision-relevant, have a definition that reflects disease and not billing (for example repeated codes, or code plus drug or lab), and have enough events in every period. `[AUDIT + LEAD: the eight conditions, definitions, horizons, event counts per period]`. The list is frozen in `configs/p1_outcomes.yaml`.

## Analyses and outputs (all under `results/p1/`)

1. Discrimination and calibration per condition, model and size: AUROC, AUPRC, calibration slope and intercept, calibration curves. `metrics.csv`.
2. Net benefit (decision curves) at thresholds fixed in advance with the clinician-reviewer. `net_benefit.csv`.
3. The same by sex, age band and site. Cells under 10 are suppressed. `subgroups.csv`.
4. Scaling curve: performance against model size and against training-set size. `scaling.csv`.
5. Age-standardised incidence and model performance compared with published cohorts. Published numbers are entered only from sources confirmed by DOI, with the table and page recorded. `external_comparison.csv`.
6. Ablations: without labs; without medications; diagnoses only.

Every model result: three seeds (0, 1, 2) and a 95% bootstrap interval over patients. Every figure and table gets a `PROVENANCE.csv` row.

## Acceptance checks, fixed before training

- No patient appears in more than one split (checked by script; result written to `results/p1/split_check.csv`).
- Each trajectory model is compared with the strongest baseline; a difference counts only if the 95% intervals do not overlap or a paired bootstrap excludes zero.
- A model is called calibrated for a condition only if `[METHODS: calibration criterion, set in review]`.
- A leakage probe: a model trained with shuffled outcome dates must fall to baseline.

## Stop conditions

A gate; any `[AUDIT]` or `[LEAD]` slot still unfilled; a required field under 60% complete; fewer outcome events in a period than the methods-reviewer's stated minimum; any need to look at the held-out period before the final step; any database query estimated over ten minutes.

## Reporting

TRIPOD+AI, filled item by item from the current official checklist. Limitations to state plainly: single country, de-identified hospital records, codes shaped by reimbursement, site mix.
