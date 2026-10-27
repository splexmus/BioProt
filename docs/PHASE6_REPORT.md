# Phase 6 development calibration report

Run: `phase6-development-v1`  
Date: 2026-10-27  
Status: `DEVELOPMENT_PILOT_NOT_FOR_PRODUCTION`

Phase 6 fitted an external Platt logistic calibrator for the probability that a top-1
B4 prediction exactly matches an admissible Tier-A EC or GO-MF identifier. The model
uses the top-1 ranking score; the LLM supplies no confidence value.

The source development split contains 42 proteins, but only 36 have at least one
eligible top-1 EC/GO-MF prediction, yielding 51 query-namespace fitting examples. The
validation evaluation contains nine proteins and 15 examples. All 15 test
query-namespace cases were excluded, including the case without a prediction.

## Validation results

| Metric | Raw ranking score | Platt calibrated |
|---|---:|---:|
| Brier score | 0.3069 | 0.2729 |
| Expected calibration error | 0.2387 | 0.1824 |
| Log-loss | 0.9071 | 0.7406 |
| Weighted exact accuracy | 0.5556 | 0.5556 |

Calibration improves all three probability-quality diagnostics without changing the
underlying ranking or exact accuracy. However, only 15 validation examples are
available. Six examples are labelled `LOW`, nine `MODERATE`, and none `HIGH`; the
confidence labels therefore remain descriptive development outputs.

The fitted model has slope `1.01698`, intercept `0.14277`, development-score mean
`0.74128`, and scale `0.20912`. It must not be interpreted beyond the exact top-1
identifier target or attached retrospectively to the development reports as prospective
confidence.

## Completion boundary

Phase 6 engineering is complete: the contract, feature export, model, evaluation,
reliability bins/diagram, manifests, and tests exist. Scientific calibration remains
pending a larger newly locked characterized cohort with genuinely unseen evaluation
proteins.
