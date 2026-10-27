# Phase 4 exit benchmark

This package turns the Phase 4 engineering pilot into an evaluation that can satisfy
the frozen exit gate. It does not replace human scientific annotation.

## What changed after the v3 audit

The v3 label file covered only final hits. That made citation recall equal to one by
construction and made Recall@K a recall-within-results measure. Evaluation v2 instead
preserves `literature_candidates.jsonl`, containing every query-linked passage scored by
the lexical, character-vector, hybrid, and reranked methods. Every candidate must be
judged before the pool is complete.

Recall is now explicitly **pooled PubMed candidate recall**. It is not absolute recall
over all papers that exist. The evaluation reports each retrieval method separately,
candidate coverage, label completeness, contradiction coverage, and threshold checks.
It also writes `literature_error_analysis.tsv` with top-10 false positives, relevant
passages missed at 10, entity/organism mismatches, non-primary top hits, and missed
contradictions.

## Benchmark queries

`build-literature-benchmark-queries` selects at least 20 records from the Phase 3
development split. It prioritizes conflict, structure-only, and sequence-only cases,
then fills the set with consensus cases. It reads:

- the characterized query manifest and split assignment;
- B4 predictions;
- leakage-filtered sequence evidence;
- controlled GO names and EC-to-GO descriptions;
- Phase 3 reproducibility metadata.

It does not read `gold_labels.tsv`, literature judgments, or held-out literature
answers. This is recorded in the query manifest.

## Prepare on the external HDD

In the user's normal terminal, where the HDD is mounted `rw`:

```bash
cd /home/splexmus/Documents/BioProt
export NCBI_API_KEY="YOUR_ROTATED_KEY"

scripts/run_phase4_exit_benchmark.sh prepare \
  --email YOUR_REAL_EMAIL@example.org \
  --run-name phase4-exit-development-v1 \
  --queries 20
```

The command refuses to overwrite an existing run. It writes all queries, raw source
responses, articles, chunks, scores, final hits, packets, manifests, and the annotation
sheet beneath:

```text
/media/splexmus/4TB_HDD1/dualrag/literature/runs/phase4-exit-development-v1/
```

## Human annotation

Annotate every row in `manual_pool_labels.tsv`. Context columns such as PMID, title,
passage text, source URL, and all four method ranks are included in the same TSV. Do not
change query IDs, chunk IDs, passage text, or ranks. Fill only:

- annotator;
- relevant;
- citation_supported;
- contradiction;
- entity_correct;
- organism_correct;
- primary_experiment;
- notes.

At least 20 queries and five contradiction passages are required by the frozen pilot
gate. `codex_preannotation` is not expert provenance. A human reviewer must record their
own identifier after reviewing each judgment.

Benchmark query builder `phase3-pool-v4` adds bounded protein-name and simplified-taxon
fallbacks for PubMed. These fallbacks address zero-hit searches caused by long strain
names while preserving the per-query candidate cap. They use no benchmark gold labels
or manual literature judgments. Broad fallback results remain unassessed until human
entity, organism, relevance, and evidence-role review.

## Evaluate

```bash
scripts/run_phase4_exit_benchmark.sh evaluate \
  --run-name phase4-exit-development-v1
```

The evaluator fails the gate if the candidate pool is not completely labelled. The
thresholds are frozen in `config/literature-evaluation-v2.yaml` before annotation and
all checks must pass. A `PASS` supports moving to Phase 5 as a development-pilot gate;
it does not establish experimental confirmation, clinical validity, or absolute
literature recall.
