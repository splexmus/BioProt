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

## Integrated analysis, literature and LLM reports

`dualrag analyze` now writes a Phase 6 assessment automatically. For example:

```bash
pixi run python -m dualrag analyze \
  --fasta tests/fixtures/queries.fasta --config config/config.yaml \
  --calibration-model results/phase6-recovery-20261111/selected_calibrator.json \
  --output results/analysis-with-phase6
```

This fixture example verifies reporting using synthetic retrieval. On real inputs, use
the verified external-data config. Add `--literature local --literature-index PATH` for
indexed search, or `--literature online --email ADDRESS` for PubMed/PMC acquisition.
Add `--report ollama --allow-unvalidated-phase4` for experimental LLM synthesis.

Outputs:

- `calibration/calibration_report.json`: model provenance and per-query applicability.
- `calibration/calibration_report.md`: readable assessment and explicit limitations.
- `calibration/candidate_assessments.tsv`: native ranks, modality scores and null probabilities.
- `literature/top_literature.md` and TSV: top ten ranked passages per query when enabled.
- `report/reports/*.md`: LLM reports with deterministic Phase 6 and literature sections.

The saved cohort model is accepted for applicability reporting, not inference on native
analysis features. Currently every supplied model is report-only: there is no registered
native-analysis inference contract. The benchmark model uses leakage-filtered MMseqs
and function projections absent from ordinary eggNOG analysis, and native GO candidates
are not restricted to GO-MF. A feature-schema adapter alone cannot establish transfer
calibration. Training, frozen cohort evaluation, and production probabilities remain
separate until a matching feature pipeline is validated. No gold labels are read and no
model is fitted by `analyze`.

The external assessment describes review/abstention and applicability. It does not
calibrate the LLM, literature scores, citations or biological truth. No usable function
candidate yields `ABSTAIN`; an informative candidate yields `REVIEW_REQUIRED`. The
trained Phase 6 sufficiency model remains unapplied for the same contract mismatch.
Literature role labels remain unchanged; retrieved UNASSESSED passages are background.
