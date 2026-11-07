# Phase 6 prospective scientific calibration thresholds

Contract: `config/calibration-evaluation-v2.yaml`  
Status: frozen before new validation predictions  
Dataset: `step3-merged-reviewed-v1`

The freeze record is `config/calibration-evaluation-v2.freeze.json`. It hashes the
threshold contract, pipeline-view dataset artifacts, procedural-seal manifest, and Pixi
lock. It explicitly records that the wider worktree and Gemma 4 generation system are
not yet frozen.

## Purpose

This contract completes Step 5 of the scientific-validation plan. It defines the result
required before calibrated confidence may be attached to future reports. The thresholds
are a conservative project decision, not a universal calibration standard. They were
chosen using the old 15-example development pilot and the new cohort's declared sample
sizes, not new validation predictions or sealed test evaluation.

Validation gold had already been materialized in the pipeline view before this freeze.
No new validation predictions, correctness outcomes, or calibration metrics existed.
Accordingly, this is prospective with respect to model outcomes, not a claim of blinded
validation-label custody.

Confidence retains its narrow Phase 6 meaning: the probability that a top-ranked EC or
GO Molecular Function identifier exactly matches admissible Tier-A gold, conditional on
a top-ranked prediction existing. It is not experimental confirmation and does not
measure whether LLM prose or literature interpretation is true.

## Required validation evidence

- at least 100 evaluable query-namespace examples;
- at least 75 unique proteins;
- at least 80% candidate-prediction coverage;
- LOW, MODERATE, and HIGH groups containing at least 20, 20, and 30 examples;
- finite, nonconstant probabilities bounded by zero and one.

An unmet sample minimum returns `INSUFFICIENT_EVIDENCE`, never a scientific pass.

## Required metric performance

Every check must pass:

| Measure | Absolute requirement | Improvement over raw score |
|---|---:|---:|
| Brier score | at most 0.22 | at least 0.02 |
| Log-loss | at most 0.65 | at least 0.02 |
| Expected calibration error | at most 0.10 | at least 0.02 |

Observed accuracy must be nondecreasing from LOW to MODERATE to HIGH. HIGH confidence
must have at least 85% point accuracy and a 95% Wilson lower bound of at least 70%.

Aggregate confidence intervals use 2,000 seed-42 protein-cluster bootstrap replicates.
Namespace, difficulty, taxonomy, and cross-modal subgroups require 30 examples for an
inferential claim; smaller groups are descriptive only. This matters because the merged
dataset has only ten proteins in the 20-30% identity stratum.

## Model selection and test boundary

Validation compares raw score, Platt logistic, isotonic regression, and multifeature L2
logistic calibration. Lowest validation log-loss wins; differences within 0.01 use
Brier, then ECE, then lower model complexity. Raw score is a baseline, not a selectable
calibrator.

If no method passes every validation check, confidence remains `NOT_FOR_PRODUCTION`.
If one passes, freeze its parameters and hashes before accessing test gold. Evaluate the
frozen calibrator on test once. A failed test cannot be followed by tuning and reuse of
the same test as a confirmatory cohort.

The current filesystem seal is procedural rather than historically untouched. It blocks
accidental pipeline access but does not turn this cohort into a third-party blinded test.

