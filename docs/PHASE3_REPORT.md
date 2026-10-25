# Phase 3 scientific benchmark report

Run ID: `phase3-run-v1`  
Dataset: `phase3-pilot-v1`  
Contract: `phase3-benchmark-v1`  
Primary split: untouched test, 9 queries

## Result

| Baseline | FR@10 | 95% bootstrap interval |
|---|---:|---:|
| B2 sequence only | 0.722 | 0.500-0.944 |
| B3 structure only | 0.250 | 0.000-0.556 |
| B4 deterministic dual | 0.778 | 0.556-1.000 |

The paired B4-minus-B2 estimate is 0.0556; its 95% interval
is 0.0000 to 0.1667. Therefore
the contract conclusion is **NO_MEASURABLE_OVERALL_BENEFIT**. The positive point estimate
does not establish improvement because the interval is not entirely above zero.

## Retrieval coverage

- AlphaFold: 46 models available;
  14 unavailable.
- Allowed B2 hits after leakage filtering: 394.
- Allowed B3 hits after SIFTS and homology filtering: 449.
- Excluded structure hits: 175.
- Candidate coverage on test: B2 0.889,
  B3 0.778, B4 1.000.

## Cross-modal error analysis over all 60 pilot queries

- both channels correct: 30;
- sequence rescue: 13;
- structure rescue: 0;
- incorrect consensus: 5;
- both fail or are missing: 12.

No structure-rescue example occurred in this pilot. That is a result, not evidence that
structure retrieval can never rescue weak-sequence queries. The pilot contains only one
query in the 20-30% bin and none in the <=20% bin.

## Mapping ablations

Five configurations were executed: no mapping, InterPro2GO, EC2GO/GO mapping, curated
GO Molecular Function names/exact synonyms, and all mappings. Mapping projections came
from official GO external2go files and GO release 2026-07-26. They were frozen before
test scoring. See `evaluation/mapping_ablation_metrics.tsv` and
`evaluation/mapping_ablation_contrasts.tsv`.

## Limitations

- This is a 60-query development pilot with only 9 untouched test queries.
- B2 uses leakage-filterable MMseqs2/Swiss-Prot retrieval because eggNOG-mapper emits
  annotations rather than the required ranked, filterable hit list.
- Fourteen queries had no AlphaFold model, reducing B3 coverage without removing them.
- Difficulty was defined against frozen Swiss-Prot; database-specific target resolution
  is preserved in the raw exclusion artifacts.
- GO experimental rows still need release-matched GOA publication identifiers before
  promotion to a final gold-standard release.
- Scores are ranking features and are not calibrated confidence estimates.

## Reproducibility artifacts

- `predictions.tsv` and `ablation_predictions.tsv`;
- `raw/sequence_evidence.tsv`, `raw/structure_evidence.tsv`, acquisition and exclusions;
- `evaluation/per_query_metrics.tsv`, aggregate metrics, subgroup tests and error table;
- hierarchical EC, GO Lin-BMA and exact InterPro/Pfam secondary metrics;
- `reproducibility_manifest.json`, provenance manifests and `CHECKSUMS.sha256`.
