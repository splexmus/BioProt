# Phase 6 confidence calibration

Contract: `phase6-confidence-calibration-v1`  
Status: development pilot; not production calibration

## Meaning of confidence

Phase 6 estimates one narrow outcome: the probability that the top-ranked B4 function
identifier is an exact match to an admissible Tier-A EC or GO Molecular Function label,
conditional on a top-ranked prediction being present. It does not estimate whether an
experiment would succeed, whether every sentence in an LLM report is true, or whether a
literature passage is relevant.

The LLM never supplies the confidence. A deterministic external calibrator transforms
the upstream top-1 ranking score into a probability.

## Data split

- Source fit split: 42 development proteins; 36 have eligible predictions, producing
  51 query-namespace examples.
- Evaluation: 9 validation proteins, producing 15 examples.
- Excluded: the 9-protein test split, because its results were previously exposed.

Each protein has total weight one across its available EC and GO-MF examples. Gold labels
are used only for fitting/evaluation and never enter a retrieval or LLM evidence packet.
The small validation set makes all reported metrics descriptive and unstable.

## Calibrator and outputs

The pre-frozen v1 method is L2-regularized Platt logistic calibration over the B4 top-1
ranking score. Extra evidence features are exported for diagnostics but are not fitted,
which limits overfitting in this small cohort.

Outputs include:

- `calibration_examples.tsv`: labels, diagnostics and calibrated probabilities;
- `calibration_exclusions.tsv`: missing predictions and prohibited test examples;
- `calibration_model.json`: fitted external model and target definition;
- `calibration_evaluation.json`: raw versus calibrated Brier, log-loss and ECE;
- `reliability_bins.tsv` and `reliability_diagram.svg`;
- `calibration_manifest.json`: checksummed inputs, outputs and claim boundaries.

Confidence labels are descriptive: `LOW < 0.50`, `MODERATE 0.50-0.75`, and
`HIGH >= 0.75`. They must not be attached to the current development proteins as if they
were unseen prospective predictions.

Run on external storage:

```bash
scripts/run_phase6_calibration.sh
```

Phase 6 can reach scientific completion only after a larger newly locked validation/test
cohort demonstrates useful calibration on unseen characterized proteins.

The completed development result is summarized in `docs/PHASE6_REPORT.md`.
