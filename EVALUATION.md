# EVALUATION.md

The normative Phase 3 decisions are frozen in
[`docs/BENCHMARK_CONTRACT.md`](docs/BENCHMARK_CONTRACT.md) and
`config/benchmark-contract-v1.yaml`. If this overview conflicts with that contract, the
versioned contract controls.

The Phase 3.2-3.4 development dataset and leakage/difficulty artifacts are documented
in `docs/PHASE3_DATASET.md`. `phase3-pilot-v1` is suitable for pipeline development and
dry-run baseline evaluation, but its 60 queries are not a statistically powered final
benchmark. Phase 3.6 resolved strict structure targets through SIFTS and used a
leakage-filterable MMseqs2/Swiss-Prot B2 baseline because eggNOG-mapper does not expose
the ranked target information required by the frozen contract.

The executed pilot result is in `docs/PHASE3_REPORT.md`. On the nine-query untouched
test split, B4 dual FR@10 was 0.778 versus 0.722 for B2 sequence-only, but the paired
95% interval for the difference was 0.000-0.167. The contract conclusion is therefore
`NO_MEASURABLE_OVERALL_BENEFIT`, not an improvement claim.

An independently labelled candidate-panel case was added on 2026-10-26 without
changing the frozen pilot splits. Of 60 supplied accessions, 47 passed frozen-release,
Tier-A gold-label and pilot-cluster screening. External-case FR@10 was 0.743 for B2,
0.444 for B3 and 0.745 for B4; paired B4-minus-B2 was 0.0015 with a 95% interval of
-0.0590 to 0.0532. See `docs/PHASE3_EXTERNAL_PANEL_REPORT.md`. This is exploratory,
not a replacement confirmatory test set.

On 2026-10-26, the conservative `quality-gated-v2` profile was selected using the
development/validation behavior and checked against the previously exposed test split. B4
FR@10 increased from 0.557 to 0.575 on development and remained 0.796 on validation
and 0.778 on test. Test precision@10, MRR and nDCG@10 were also unchanged. The deeper
50-hit profile was retained as experimental because it lowered precision. The v1 test
split is only a regression check for v2, not fresh confirmatory evidence. These results
improve the ranking implementation but do not change the contract conclusion of
`NO_MEASURABLE_OVERALL_BENEFIT`. See `docs/PIPELINE_V2.md` and the comparison artifacts
under `benchmark/phase3-pipeline-v2-conservative/comparison/`.

## 1. Research questions

- RQ1: Does dual sequence+structure retrieval increase functional recall over sequence-only retrieval?
- RQ2: Does structure retrieval rescue proteins with weak sequence similarity?
- RQ3: Is sequence-structure agreement associated with higher prediction accuracy?
- RQ4: Can the system detect and expose meaningful conflicts rather than hiding them?
- RQ5: Does literature RAG improve final report quality/grounding after biological retrieval?
- RQ6: Are confidence estimates calibrated to empirical correctness?
- RQ7: Does an optional graph/path layer improve evidence coherence enough to justify extra complexity?

## 2. Benchmark datasets

### A. Characterized gold-standard proteins
Use reviewed/experimentally supported proteins with reliable function labels. Prefer diverse taxa, not one organism only.

### B. Sequence-difficulty strata
Stratify by similarity to known homologs, for example:

- >70%
- 50–70%
- 30–50%
- 20–30%
- <20%

The exact definition of similarity/nearest reference must be documented.

### C. Uncharacterized proteins
Use hypothetical/uncharacterized/unknown-function proteins to measure:

- annotation coverage
- specificity gain
- sequence/structure agreement
- conflict rate
- expert usefulness

Do not report accuracy against unknown ground truth.

## 3. Data splitting
Avoid random leakage across highly homologous proteins.

Recommended:
- cluster proteins with MMseqs2 at a chosen identity threshold
- assign whole clusters to development/validation/test
- report the clustering threshold and coverage

Possible split: 70/15/15, but the final choice is experimental.

## 4. Baselines

- B0: LLM only
- B1: literature RAG only
- B2: sequence retrieval only
- B3: structure retrieval only
- B4: sequence + structure, deterministic merge only
- B5: sequence-RAG
- B6: structure-RAG
- B7: dual sequence-structure RAG
- B8: dual RAG + literature
- B9: graph-enhanced dual RAG

MVP research should reach at least B2–B4 before implementing B5+.

Phase 3 evaluates B2, B3, and B4 only. B0/B1 and B5+ remain future-layer labels and
must not be mixed into the Phase 3 primary analysis.

## 5. Retrieval metrics
Evaluate each retriever independently:

- Recall@1 / @5 / @10
- Precision@K where labels permit
- MRR
- nDCG
- candidate coverage

Cross-modal metrics:

- union recall: `Recall(R_seq ∪ R_struct)`
- intersection coverage: proteins with informative evidence from both
- structure rescue rate: correct functions retrieved by structure when sequence misses
- sequence rescue rate: converse
- conflict rate

## 6. Function prediction metrics

- exact protein-function match where a controlled gold label exists
- protein-family accuracy
- EC exact match and hierarchical partial match
- GO semantic similarity
- domain consistency
- top-K function recall

Use hierarchical metrics so a broadly correct family prediction is not treated exactly like an unrelated prediction.

The primary endpoint is macro exact EC/GO-MF Function Recall@10. InterPro and Pfam are
secondary family/domain consistency endpoints and cannot by themselves establish exact
function correctness. See the contract for evidence eligibility, hierarchy, missingness,
bootstrap, and claim rules.

## 7. Generation metrics
For LLM-generated reports:

- factual correctness
- groundedness
- citation precision
- citation recall
- completeness
- biological relevance
- specificity
- unsupported-claim rate
- contradiction handling
- expert preference/usefulness

Do not rely only on LLM-as-judge; include expert evaluation on a meaningful sample.

Phase 5 reports that bypass the Phase 4 exit gate are development artifacts only. A
deterministic verifier pass checks schema, evidence linkage, citation metadata,
controlled identifiers, and claim boundaries; it is not a biological truth judgment.
The Phase 5 exit decision still requires blinded human/expert comparison against a
deterministic evidence-template baseline and a biological-evidence-only generation
baseline.

## 8. Citation metrics

```text
Citation Precision = supported citations / citations produced
Citation Recall = claims requiring citation with support / all claims requiring citation
```

Also inspect entity consistency: correct protein, organism, gene, and experimental context.

Phase 4.0-4.1 contract `phase4-literature-v1` requires a manually labelled passage
dataset before literature retrieval can be declared successful. Labels must distinguish
support, contradiction, background, irrelevant, and unassessed passages while separately
recording exact-protein/homolog/family matching and organism compatibility. The frozen
evaluation set must report literature Precision@K, Recall@K, MRR or nDCG, citation
precision/recall, entity correctness, organism correctness, primary-experiment retrieval,
and contradiction retrieval. The original v1 evaluation profile intentionally left
acceptance thresholds unset; pooled evaluation v2 now freezes pilot thresholds before
the new annotation run.

`dualrag evaluate-literature` implements these passage-level metrics using an explicit
manual TSV. The evaluator reports `INSUFFICIENT_MANUAL_LABELS` below the frozen
20-query pilot minimum. `config/literature-evaluation-v1.yaml` remains the descriptive
historical profile. The operational Phase 4 exit gate is v2 below.

The five-query v3 audit showed that labelling final hits alone cannot estimate recall.
Evaluation v2 therefore uses a completely judged pooled candidate set and reports
lexical, character-vector, hybrid, and reranked metrics separately. Pilot thresholds
are frozen before human annotation in `config/literature-evaluation-v2.yaml`; all must
pass. Recall is explicitly limited to the PubMed candidate pool and must not be
described as absolute literature recall. See `docs/PHASE4_EXIT_BENCHMARK.md`.

## 9. Confidence calibration
Evaluate with:

- reliability diagram
- Brier score
- Expected Calibration Error (ECE)
- accuracy by confidence bucket

Compare external calibration to LLM self-confidence as a baseline, not as the preferred method.

## 10. Ablation study
Full system versus:

- without sequence retrieval
- without structure retrieval
- without domain evidence
- without cross-modal agreement feature
- without reranker
- without literature
- without graph/path layer
- without calibration

Each ablation should answer a mechanistic question, not just generate another number.

## 11. Reproducibility requirements
Every benchmark run stores:

- git commit
- environment lock/export
- tool versions
- database versions
- configuration
- command line
- random seed
- raw outputs
- normalized outputs
- metrics
