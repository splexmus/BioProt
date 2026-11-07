# Phase 6 ranking, evidence sufficiency, and calibration

Run date: 2026-11-07  
Recommended development bundle: `phase6-development-evidence-v2`  
Previous-benchmark status: `EXPLORATORY_PREVIOUS_BENCHMARK_REUSE`

Development transition decision: `PASS_FOR_NEW_VALIDATION_BUILD`. This means the
pipeline improved enough to freeze and evaluate on a new independent cohort. It does
not replace the scientific status, which remains `FAIL_SCIENTIFIC_CALIBRATION_GATE`.

## Implemented pipeline

```text
Sequence-anchored dual ranking
        ↓
Evidence sufficiency probability
        ↓
Top-1 prediction or explicit abstention
        ↓
Probability calibration for accepted predictions only
```

The ranker keeps the sequence-only top candidate at rank 1 when one exists, while
structure can add candidates below it. The selected development profile permits at
most one structure-only candidate per namespace. This prevents consensus or projected
structure candidates from displacing a stronger sequence top-1 merely because they
receive a fusion bonus.

Evidence sufficiency uses a cluster-aware out-of-fold multifeature logistic model. The
recommended high-coverage revision requires at least 95% development coverage and 90%
coverage within each namespace. Calls below the selected sufficiency threshold are
reported as `ABSTAIN`; only accepted calls enter the calibrator.

## Ranking result

Development-only selection on 552 proteins:

| Metric | Sequence-only | Anchored dual v3 |
|---|---:|---:|
| Recall@1 | 0.3769 | 0.3963 |
| Recall@10 | 0.7549 | 0.7803 |
| Precision@10 | 0.4806 | 0.4124 |
| MRR | 0.7460 | 0.7721 |

On the previously revealed 150-protein benchmark, before abstention:

| Metric | Sequence-only | Anchored dual v3 |
|---|---:|---:|
| Recall@1 | 0.3648 | 0.3781 |
| Recall@10 | 0.6047 | 0.6302 |
| Precision@10 | 0.3476 | 0.2801 |
| MRR | 0.5360 | 0.5445 |
| Candidate coverage | 0.8467 | 0.9200 |

The paired dual-minus-sequence Recall@10 improvement was 0.0256 with a 95% bootstrap
interval of 0.0044 to 0.0522. Precision remains the principal ranking weakness.

## Sufficiency and calibration result

The first 80%-coverage development policy transferred poorly and accepted only 59.8%
of the previous benchmark. It was rejected. The high-coverage v2 revision was then
selected on development and is the recommended exploratory bundle:

| Item | Development OOF | Previous benchmark |
|---|---:|---:|
| Accepted coverage | 95.0% | 86.2% |
| Accepted examples | 781 | 163 |
| Accepted weighted accuracy | 68.4% | 57.4% |
| Brier score | 0.2107 | 0.2470 |
| Log loss | 0.6104 | 0.6865 |
| ECE | 0.0047 | 0.1060 |

Only one of 26 abstained previous-benchmark cases would have had a correct top-1 call,
so the gate removed weak predictions effectively. After abstention, dual Recall@10
remained above sequence-only by 0.0189 with a 95% bootstrap interval of 0.0011 to
0.0422.

Calibration improved over the earlier frozen result (Brier 0.2581, log loss 0.7089,
ECE 0.1661), but it still misses the scientific limits of 0.22, 0.65, and 0.10. It also
does not create enough LOW or HIGH cases. Therefore this work does not pass the Phase 6
scientific gate and does not authorize access to the sealed test labels.

It does pass the separate development-continuation checks: ranking Recall@10 has a
positive confidence interval; Recall@1 and MRR exceed sequence-only; accepted coverage
exceeds 80%; only 3.8% of abstentions would have been correct; and Brier, log loss, and
ECE all improved over the previous pipeline. The improvement is modest rather than a
claim of production-ready confidence.

## Interpretation boundary

The previous benchmark labels were already revealed before this improvement cycle. The
80%-coverage transfer failure influenced the decision to create the 95%-coverage
revision. Consequently all previous-benchmark v2 results are retrospective and cannot
serve as confirmatory validation. A new cluster-independent validation cohort must be
created after the v2 ranking, sufficiency model, calibrator, code, and thresholds are
frozen.

## New frozen validation v2

The development transition was followed through on a new 300-protein cohort that
excluded all 938 proteins used by the original benchmark and fresh validation v1. The
cohort contained 403 eligible EC/GO-MF query-namespace cases. Retrieval, ranking,
abstention decisions, calibration parameters, code, and hashes were frozen before its
gold labels were revealed.

The sample-size gate passed: 324 cases from 243 proteins were accepted, giving 80.4%
coverage. Only 6.3% of abstained calls would have been correct, so the evidence
sufficiency layer remained useful.

However, ranking did not reproduce the retrospective benefit. Dual-minus-sequence
Recall@10 was 0.0046 with a 95% bootstrap interval from -0.0140 to 0.0233, classified as
`NO_MEASURABLE_OVERALL_BENEFIT`.

Calibration improved strongly over the raw ranking score but still failed every
absolute metric limit:

| Metric | Raw score | Calibrated | Required |
|---|---:|---:|---:|
| Brier score | 0.3138 | 0.2571 | <=0.22 |
| Log loss | 0.9925 | 0.7076 | <=0.65 |
| ECE | 0.2333 | 0.1377 | <=0.10 |

There were 317 MODERATE, seven HIGH, and zero LOW cases. All seven HIGH calls were
correct, but their Wilson 95% lower bound was only 0.646 and the group was below the
required size of 30. Final status remains `FAIL_SCIENTIFIC_CALIBRATION_GATE`; the test
vault was not accessed.

## Artifacts

- Ranking profile:
  `/media/splexmus/4TB_HDD1/dualrag/benchmarks/ranking/phase6-development-ranking-v3`
- Development evidence bundle:
  `/media/splexmus/4TB_HDD1/dualrag/calibration/runs/phase6-development-evidence-v2`
- Gold-free previous-benchmark application:
  `/media/splexmus/4TB_HDD1/dualrag/calibration/runs/phase6-fresh-validation-v1-evidence-v2`
- Retrospective evaluation:
  `/media/splexmus/4TB_HDD1/dualrag/benchmarks/evaluations/phase6-fresh-validation-v1-evidence-v2-exploratory`
- New frozen validation v2:
  `/media/splexmus/4TB_HDD1/dualrag/benchmarks/evaluations/phase6-fresh-validation-v2-frozen`
