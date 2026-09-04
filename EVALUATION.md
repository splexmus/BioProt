# EVALUATION.md

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

## 8. Citation metrics

```text
Citation Precision = supported citations / citations produced
Citation Recall = claims requiring citation with support / all claims requiring citation
```

Also inspect entity consistency: correct protein, organism, gene, and experimental context.

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
