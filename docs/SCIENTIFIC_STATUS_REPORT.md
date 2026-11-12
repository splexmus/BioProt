# Overall scientific status

Assessment date: 2026-11-12
Overall status: **benchmark Phase 6 validation passed; sealed test evaluation pending**

## Current Phase 6 decision — 2026-11-12

The saved namespace-aware recovery calibrator (L2 0.01) passed the unchanged scientific
calibration gate on a new 300-protein cohort excluding 1,639 exposed identities.
370 cases from 273 proteins were evaluable (91.58% coverage). Brier was 0.194431,
log loss 0.563131, ECE 0.079762; all absolute and raw-improvement limits passed.
LOW/MODERATE/HIGH groups contained 158/108/104 cases, with monotonic weighted
accuracies 0.2992/0.4756/0.9058; HIGH Wilson lower bound was 0.8437.
Dual-minus-sequence Recall@10 was +0.074333 (95% CI 0.047278-0.103140).

Model, ranking and probabilities were frozen before validation gold reveal; no test
gold was accessed. Label custody is procedural separation, not third-party blinding.
The point-estimate gate passed; ECE's 95% interval still extends above 0.10.
This result applies to the benchmark MMseqs/Foldseek feature pipeline. Native eggNOG
analysis remains NOT_CALIBRATED, Phase 4 remains failed, and production/test acceptance
is pending. Full artifacts: `results/phase6-validation-20261112/REPORT.md`.

## Historical assessment — 2026-11-07

The following sections preserve the earlier cohort outcomes and have been superseded
for the current recovery calibrator by the dated validation result above.

## Bottom line

BioProt reproducibly runs independent sequence and structure retrieval, preserves their
provenance and disagreement, builds bounded literature evidence packets, and produces
grounded draft reports. That makes it a successful research *instrument*.

It is not yet a scientifically validated protein-function predictor. On the newest
independent validation cohort, the dual ranker did not show a measurable overall
Recall@10 advantage over sequence-only retrieval, calibrated confidence missed every
frozen absolute limit, and the literature retriever missed six frozen quality checks.
Its outputs must therefore remain putative hypotheses with explicit uncertainty.

## Evidence by component

| Component | What is established | Current scientific decision |
|---|---|---|
| Sequence retrieval | Reproducible local retrieval and useful functional candidates | Engineering pass; valuable baseline |
| Structure retrieval | Independent Foldseek evidence and structure-specific candidates | Engineering pass; AlphaFold queries remain labelled predicted |
| Dual ranking | Retrospective ranking improved, but newest cohort gain was +0.0046 with 95% CI -0.0140 to 0.0233 | No measurable overall benefit |
| Abstention | 80.4% accepted coverage; only 6.3% of abstained calls would have been correct | Useful risk-control signal |
| Calibration | Improved raw scores, but Brier 0.2571, log loss 0.7076, ECE 0.1377 | `FAIL_SCIENTIFIC_CALIBRATION_GATE` |
| Literature RAG | Complete, provenance-preserving Phase 4 workflow and 1,569 labelled passages | Frozen Phase 4 scientific exit `FAIL` |
| LLM reports | Schema-bounded local generation, evidence IDs, citation checks, separate modality sections | Development pass only; blinded expert validation pending |

## What the results mean

1. Sequence retrieval is currently the strongest dependable ranking anchor.
2. Structure evidence remains useful for rescue, domain context, and disagreement
   analysis, but the project has not demonstrated a reliable average gain for exact
   EC/GO-MF retrieval on unseen proteins.
3. The evidence-sufficiency layer is useful because it rejects mostly incorrect calls.
   It does not make accepted probabilities calibrated.
4. Literature retrieval is the largest downstream weakness. The labelled development
   pool achieved Recall@10 0.4615, nDCG@10 0.6889, citation precision 0.5393, citation
   recall 0.2697, entity correctness 0.3258, and organism correctness 0.3680.
5. An LLM can summarize retrieved evidence, but it cannot repair missing, misidentified,
   or poorly ranked evidence. Literature and biological retrieval scores must remain
   outside the LLM's control.

## Appropriate use now

- exploratory protein-function research;
- candidate generation and modality-specific evidence review;
- explicit `CONSENSUS`, `CONFLICT`, sequence-only, structure-only, and abstain analysis;
- generation of auditable draft reports for human review.

Do not use the current pipeline as experimental confirmation, a production annotation
service, or a source of validated probability estimates. The sealed test labels remain
unavailable because the frozen validation gate failed.

## Next scientific experiment

Evaluate the new persistent literature index as an ablation, not as an assumed
improvement. Re-run the existing 20-query/1,569-passage labels without changing them and
compare the old in-memory baseline against indexed hybrid retrieval. Only freeze a new
retriever if it improves recall and entity/organism correctness without reducing
citation precision; then test it once on a new independently labelled query set.

The controlled indexed reproduction was completed on 2026-11-07. All listed Phase 4
metrics exactly reproduced the original v4 values, confirming that persistence did not
change the scorer. The unrestricted corpus-wide run created 31,380 query-passage
candidates and 352 final hits, but it is not scientifically scored because the old
labels cover only the original restricted 1,569-candidate pool.
