# Phase 4.3-4.7 literature pipeline

## What is implemented

Phase 4 now has an executable boundary from deterministic biological queries through
literature evaluation:

1. **4.3 acquisition:** PubMed ESearch resolves each versioned query variant to PMIDs;
   batched EFetch normalizes metadata and structured abstracts. PMC full text is fetched
   only after a PMC ESearch open-access/author-manuscript filter confirms availability.
   The legacy PMC OA Web Service was retired in August 2026. Raw JSON/XML, checksums, access
   failures, article license text, request provenance, and cache reuse are preserved.
2. **4.4 normalization:** articles are deduplicated by identifier and split into title/
   abstract, introduction, methods, results, discussion, and figure/table-caption chunks.
   Chunks are at most 1,200 characters and retain offsets and SHA-256.
3. **4.5 retrieval:** BM25 word retrieval and character-trigram vector similarity are
   normalized separately, combined 50/50, and passed through a deterministic biological
   reranker using explicit entity match, organism match, and section priors. Scores rank
   passages; they are not confidence and do not assign evidence roles.
4. **4.6 packets:** at most 10 articles, 20 chunks, and 3 chunks per article are emitted
   with alternatives and mandatory claim boundaries. `UNASSESSED` stays explicit.
5. **4.7 evaluation:** a strict manual TSV is scored for Precision/Recall@1/5/10, MRR,
   nDCG@10, citation precision/recall, entity and organism correctness, primary-
   experiment retrieval, and contradiction retrieval. Fewer than 20 manually labelled
   queries yields `INSUFFICIENT_MANUAL_LABELS`, not a scientific pass.

The initial vector baseline is deliberately dependency-light and deterministic. It is
a character n-gram vector, not a protein or publication foundation-model embedding.
That makes the lexical/vector/hybrid ablation reproducible; a learned embedding can be
added later under a new retriever version.

## Run all data on the external HDD

First build Phase 4.2 queries, then run:

```bash
scripts/run_phase4_on_hdd.sh \
  --queries results/my-literature-queries/literature_queries.jsonl \
  --email you@example.org \
  --run-name phase4-pilot-v1
```

An optional NCBI API key is read from `NCBI_API_KEY`; its value is never written to a
manifest. The runner verifies the exact mount and refuses to fall back to an internal
disk. Use `--dry-run` to inspect paths and the command.

The current `/media/splexmus/4TB_HDD1` mount was read-only when this implementation was
validated. The script reports this and stops before creating output. A read-only mount
with `errors=remount-ro` can indicate a filesystem/storage problem; inspect it and
repair/remount safely before running downloads.

## Manual evaluation

The runner creates `manual_labels.tsv`. Every row requires an annotator and explicit
boolean judgments. After expert annotation:

```bash
pixi run python -m dualrag evaluate-literature \
  --hits /media/splexmus/4TB_HDD1/dualrag/literature/runs/phase4-pilot-v1/literature_hits.jsonl \
  --labels /media/splexmus/4TB_HDD1/dualrag/literature/runs/phase4-pilot-v1/manual_labels.tsv \
  --output /media/splexmus/4TB_HDD1/dualrag/literature/runs/phase4-pilot-v1/evaluation
```

The implementation is complete when code and mocked fixtures pass. Phase 4 is
scientifically complete only after the manual dataset is populated and the resulting
metrics/error analysis are reviewed. No synthetic fixture establishes literature hit
quality.
