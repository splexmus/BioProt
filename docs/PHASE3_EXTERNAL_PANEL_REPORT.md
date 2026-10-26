# Phase 3 external candidate-panel benchmark

Run: `phase3-external-panel-run-v1`  
Dataset: `phase3-external-panel-v1`  
Source panel date: 2026-10-26  
Evaluation split: `external_case`

This is a separately labelled external-case rerun. It does not change the original
60-protein pilot or its untouched nine-query test split.

## Screening

- Supplied candidates: 60.
- Included after frozen-source and pilot-cluster screening: 47.
- Excluded: 13.
- Eligible for the <=30% closest-allowed-identity subgroup:
  2.
- Architecture labels remain provisional because positional InterProScan evidence was
  not available.

The complete decisions are in `benchmark/phase3-external-panel-v1/panel_screening.tsv`.
`NO_ANNOTATED_ACTIVE_SITE` means no UniProt `ACT_SITE` feature and does not establish
biological inactivity.

## External-case result

| Baseline | Function Recall@10 | 95% bootstrap interval |
|---|---:|---:|
| B2 sequence only | 0.743 | 0.632-0.845 |
| B3 structure only | 0.444 | 0.322-0.567 |
| B4 deterministic dual | 0.745 | 0.633-0.847 |

The paired B4-minus-B2 estimate is 0.0015, with a 95%
interval from -0.0590 to
0.0532. The contract conclusion is
**NO_MEASURABLE_OVERALL_BENEFIT**. Dual retrieval therefore showed no measurable overall
benefit in this external case.

## Retrieval and cross-modal outcomes

- AlphaFold models downloaded: 43.
- AlphaFold models unavailable: 4.
- Allowed sequence hits: 384.
- Allowed structure hits: 412.
- Excluded structure hits: 150.
- Both channels correct: 27.
- Sequence rescues: 13.
- Structure rescues: 0.
- Incorrect consensus: 2.
- Both failed or missing: 4.

No structure rescue occurred. The low-identity subgroup contains only two proteins, so
it cannot support a general conclusion about remote-homology rescue.

## Interpretation limits

- Twelve supplied proteins lacked admissible Tier-A EC/GO-MF labels in frozen
  Swiss-Prot 2026_03; one additional candidate overlapped an exposed pilot cluster.
- This panel was proposed after the original benchmark was inspected, so it is an
  exploratory external case, not a new untouched confirmatory test set.
- Mapping ablations did not change B4 Function Recall@10 in this cohort.
- Supplied single/multi-domain labels remain unverified and subgroup results using them
  are exploratory only.
- Scores are retrieval-ranking features, not calibrated biological confidence.
