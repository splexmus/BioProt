# Local literature vector index

## What was implemented

The Phase 4 chunk corpus can now be stored in a local SQLite database. Each row contains:

- the validated `LiteratureChunk` JSON and its PMID;
- a deterministic case-folded character-trigram vector;
- source checksum and index version metadata;
- a separate checksummed build manifest.

Search reads the stored vectors, combines exact cosine similarity with the existing BM25
score, applies the existing biological reranker, and writes the same
`literature_candidates.jsonl`, `literature_hits.jsonl`, and `evidence_packets.jsonl`
contracts as the online pipeline. It does **not** call PubMed or PMC during search.

This is an exact local vector store, not an ANN service such as Qdrant and not a semantic
embedding model. It is the smallest dependency-free implementation that can be compared
fairly with the existing `hybrid-bm25-char3-v1` baseline. Upgrade only after it is
measured and corpus size makes exact scanning too slow.

## Step-by-step: build the first HDD index

From `/home/splexmus/Documents/BioProt`:

```bash
pixi install

RUN=/media/splexmus/4TB_HDD1/dualrag/literature/runs/phase4-exit-development-v4
INDEX_ROOT=/media/splexmus/4TB_HDD1/dualrag/literature/indexes
mkdir -p "$INDEX_ROOT"

pixi run python -m dualrag build-literature-index \
  --chunks "$RUN/literature_chunks.jsonl" \
  --index "$INDEX_ROOT/phase4-exit-development-v4.sqlite3"
```

Expected output: `indexed 1569 literature chunks`. The adjacent
`phase4-exit-development-v4.sqlite3.manifest.json` records provenance and checksums.
The command refuses to overwrite an existing index. Rebuild intentionally with
`--replace` only when the source chunk file is known and versioned.

## Step-by-step: search without PubMed

Search the complete local corpus for the existing query set:

```bash
OUT=/media/splexmus/4TB_HDD1/dualrag/literature/runs/phase4-vector-development-v1

pixi run python -m dualrag search-literature-index \
  --queries "$RUN/queries/literature_queries.jsonl" \
  --index "$INDEX_ROOT/phase4-exit-development-v4.sqlite3" \
  --output "$OUT" \
  --top-k 20
```

Omit `--query-article-links` for a corpus-wide vector search. Add
`--query-article-links "$RUN/query_article_links.json"` only for a controlled comparison
restricted to the articles originally fetched for each query.

The output contains:

```text
literature_candidates.jsonl   all scored local candidates
literature_hits.jsonl         article-limited top passages
evidence_packets.jsonl        bounded Phase 5-ready packets
retrieval_manifest.json       input hashes, versions, counts
evidence_packet_manifest.json packet provenance
```

## Step-by-step: use your own protein queries

1. Run the biological pipeline for the protein.
2. Build a leakage-safe `literature_queries.jsonl` with
   `dualrag build-literature-queries`.
3. Search the local index with the command above and your new query file.
4. Inspect `literature_hits.jsonl`; absence of a hit means only that the *local corpus*
   lacks a retrieved passage.
5. If coverage is insufficient, run online Phase 4 acquisition once to fetch new PubMed
   metadata/abstracts and eligible PMC OA text, then build a new versioned index from its
   `literature_chunks.jsonl`.

A vector index replaces repeated retrieval against an already acquired corpus; it does
not contain all of PubMed and cannot eliminate periodic corpus acquisition. PubMed
metadata and PMC Open Access text must still be acquired under their source and
licensing rules.

## Step-by-step: evaluate before adoption

Create a fresh output from the frozen v4 queries, then evaluate it against labels mapped
by stable `(query_id, chunk_id)`. Do not assume row order is unchanged. Compare at least
Recall@10, nDCG@10, citation precision/recall, entity correctness, and organism
correctness with `docs/SCIENTIFIC_STATUS_REPORT.md`.

The indexed retriever is an experimental ablation. Its ranking score is not confidence,
and the implementation does not change the current Phase 4 or Phase 6 gate decisions.

## Verified run

On 2026-11-07 the v4 corpus produced an index of 1,569 chunks. Restricted search
reproduced all recorded Phase 4 metrics exactly and therefore remained `FAIL`, as
expected. Unrestricted local search produced 31,380 candidates and 352 final hits across
20 queries. Those unrestricted results require a new complete label pool before any
quality comparison can be claimed.

Artifacts:

- index: `/media/splexmus/4TB_HDD1/dualrag/literature/indexes/phase4-exit-development-v4.sqlite3`
- unrestricted run: `/media/splexmus/4TB_HDD1/dualrag/literature/runs/phase4-vector-development-v1`
- controlled reproduction: `/media/splexmus/4TB_HDD1/dualrag/literature/runs/phase4-vector-controlled-v1`
