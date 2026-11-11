# Phase 6 recovery experiment plan

Prepared 2026-11-11. Execution: development model search and cohort sizing completed.
New cohort construction awaits the missing third-cohort exposure list. See
`../results/phase6-recovery-20261111/REPORT.md` for measured results and limitations.

## Objective and baseline

Develop a calibrator for exact top-1 EC/GO-MF correctness and evaluate it once on a
new cluster-independent cohort under the unchanged calibration-evaluation-v2 contract.
Passing is an experimental outcome, not a guaranteed deliverable.

Use the actual numeric V4 settings as the baseline: sequence/structure/agreement
0.55/0.30/0.15 and base/quality 0.85/0.15. Preserve the existing user-edited YAMLs;
snapshot effective settings and hashes in each experiment. Latest matched comparison:
Brier 0.227963, log loss 0.646619, ECE 0.026707, five LOW and five HIGH examples on
171 cases from 118 validation proteins. This is a retrospective baseline.

## 1. Audit inputs and establish label boundaries

- Inventory every previously exposed accession and sequence checksum, including the
  original 788 proteins and all fresh-validation cohorts. Recover the accession list
  for the third 300-protein cohort recorded in MEMORY.md and ROADMAP.md; its artifacts
  were absent from the mounted benchmark tree during the previous inspection.
- If that cohort cannot be identified, model development can proceed, but a claim that
  a new cohort excludes every previous query must remain blocked.
- Preserve sealed test gold. Read only query identities needed for exclusion.
- Verify that EC and GO-MF rows from the same protein/sequence cluster stay in the
  same fold, and that input gold contains only intended development labels.
- Audit baseline construction: B2 rankings changed slightly when fusion weights changed
  in the latest comparison. Explain this coupling and use a fixed sequence-only comparator
  for candidate comparisons; retain historical outputs rather than rewriting them.

Deliverable: input/exposure ledger, baseline manifest, and any necessary focused tests.

## 2. Establish development-only cross-validation

Reuse scripts/run_phase6_development_calibration.py and the existing 552-protein
development view. Start with five cluster-aware folds and seed 42. Generate held-out
probabilities for Platt, isotonic, and multifeature L2 logistic using existing helpers.
Use the same fixed V4 predictions for every calibration candidate.

Record Brier, log loss, ECE, coverage, LOW/MODERATE/HIGH counts, group accuracy and
Wilson bounds, plus namespace and difficulty summaries. These group checks must be
calculated from out-of-fold predictions, not training-fit probabilities.

## 3. Try a small, prespecified model extension

First audit the existing feature contract and missing-value handling. Most suggested
evidence features already exist; do not add duplicate or unavailable measurements.
Use the current multifeature model as baseline. Compare a small declared L2 penalty
grid and one namespace-aware variant (EC versus GO-MF), reusing the NumPy fitter.
Fit scaling, imputation, and coefficients inside each training fold only. Do not use
class rebalancing or stretch probabilities to populate confidence groups.

Use nested cluster-aware CV if selecting penalties or variants: inner folds select the
candidate and outer folds estimate generalization. Retain the frozen primary selection
objective, log loss, with the existing Brier/ECE/complexity tie-breakers. Freeze the
candidate list before inspecting comparisons. Any additional model needs a new
development plan entry, not repeated tuning on the validation cohort.

Advance only if outer-fold evidence supports the unchanged absolute metric limits,
minimum improvements over raw scores, and usable confidence-group separation.
Report uncertainty. Brier <=0.21 is an optional development margin, not a replacement
for the scientific limit of 0.22. If no candidate is ready, record the failure and
improve development evidence rather than spending a new validation cohort.

## 4. Size and build one new cohort

Estimate required total size from development out-of-fold group frequencies and
acceptance coverage. For example, five HIGH cases per 118 proteins implies about
708 proteins merely to EXPECT 30 HIGH cases. This is not a power calculation and
does not provide a high probability of meeting the minimum. Account for count
uncertainty and LOW cases when choosing the fixed size; do not assume 300 is enough.

Before labels are revealed, preregister a fixed size based on these estimates and
available eligible proteins. Use scripts/build_phase6_fresh_validation.py with all
known exposure datasets, the frozen Swiss-Prot release/checksum, and existing
cluster/leakage rules. Use representative predeclared sampling, not selection for
predicted success or particular confidence groups. Save screening/exclusion provenance.

The current builder materializes gold during construction, so retain the documented
procedural separation limitation. Seal it immediately and use the gold-free pipeline
view; do not claim independent third-party blinding.

## 5. Freeze and evaluate once

Fit the selected calibrator on the declared development set. Freeze model coefficients,
preprocessing, feature schema, V4 ranking, mappings, databases, abstention rule if any,
confidence boundaries, contract, source code, environment and checksums. Apply the
pipeline without gold, then freeze predictions before revealing new validation labels.
Reuse the existing freeze and frozen-validation runners, extending their model boundary
only if the new variant requires it, with corresponding tests.

All checks must pass together:

- At least 100 evaluable cases, 75 proteins, and 80% prediction coverage.
- Brier <=0.22, log loss <=0.65, ECE <=0.10, each improving over raw by >=0.02.
- At least 20 LOW, 20 MODERATE and 30 HIGH cases, monotonic group accuracy.
- HIGH accuracy >=0.85 and Wilson 95% lower bound >=0.70.
- Finite, nonconstant probabilities within [0,1].

Use 2,000 protein-level bootstrap replicates for calibration uncertainty as specified
by the frozen contract, and 10,000 paired replicates for Phase 3 Recall@10. Report
namespace/difficulty/taxonomy/cross-modal subgroups without promoting underpowered
groups to inferential claims. Sample-size failure is INSUFFICIENT_EVIDENCE; any other
unmet required check retains the scientific failure. Do not extend the cohort after
inspecting correctness outcomes to seek a pass.

## 6. Deliverables and handoff

Write versioned run artifacts and a comparison report under git-ignored results/.
Keep current raw evidence, runs, and historical decisions. Report V4 versus the new
calibrator using development CV, then the one new prospective validation outcome.
Confidence remains NOT_CALIBRATED until the gate passes. Passing permits the separate
one-time sealed test evaluation after its required freeze and recorded decision;
production claims also depend on that outcome.

Implementation scope: calibration/development.py and scientific.py only where needed,
existing script callers and configuration schemas, focused calibration and leakage tests,
and calibration documentation. No changes to biological retrieval scores or frozen
acceptance thresholds. Run focused tests, Ruff and mocked/offline smoke checks; describe
external retrieval execution separately from offline fitting and evaluation.

## Implemented development commands

The recovery runner retains the existing logistic defaults and adds optional positive
L2 regularization and a namespace feature in the shared fitter. Eight candidates are
declared before fitting: Platt, isotonic, and pooled/namespace-aware logistic at
L2 0.01, 0.1 and 1.0. Model selection uses inner three-fold CV; outer five-fold CV
reports held-out probabilities. All folds keep protein clusters together. Means and
scales are fitted only on training rows; missing values retain the existing zero-value
feature convention. No new dependency is required.

```bash
PYTHONPATH=src .pixi/envs/default/bin/python scripts/run_phase6_recovery.py \
  --dataset /media/splexmus/4TB_HDD1/dualrag/benchmarks/step3-merged-reviewed-v1-development \
  --run /media/splexmus/4TB_HDD1/dualrag/benchmarks/runs/step6-interpro111-config-development-v4 \
  --output results/phase6-recovery-NEW
```

Use `scripts/audit_phase6_exposure.py --help` to reproduce the known exposure ledger,
and `scripts/size_phase6_cohort.py --help` for group-count planning. Each command
refuses to overwrite its output. Development readiness is not scientific validation.
