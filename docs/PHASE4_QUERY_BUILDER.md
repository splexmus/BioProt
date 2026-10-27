# Phase 4.2 deterministic literature-query builder

Phase 4.2 converts completed biological-retrieval artifacts into source-neutral,
versioned literature queries. It does not contact PubMed or PMC.

## Inputs

The builder reads only these fixed filenames from a completed pipeline run:

- `queries.tsv`;
- `function_candidates.tsv`;
- `fusion_summary.tsv`;
- `alternatives.tsv`;
- `sequence_results.tsv`;
- `run_metadata.json`.

It never reads benchmark gold labels, evaluation outputs, or manual literature labels.
The output manifest lists every accessed file and checksum and states the prohibited
input classes that were not accessed.

An optional context TSV supplies biological identity that the standard FASTA/run schema
does not always contain:

```text
query_id  query_accession  protein_name  organism  taxonomy_id
```

The header must match exactly. An unexpected column—including `gold_labels`—fails the
build. A query must resolve to a validated UniProt accession or have an explicit protein
name in this context file. Organism and taxonomy remain null when not provided.

## Deterministic selection

For each query, the builder:

1. preserves the query order from `queries.tsv`;
2. selects up to five informative function candidates by fusion rank and stable ID;
3. selects up to five unique sequence-hit accessions by normalized score and accession;
4. records sequence identity, coverage, normalized score, target ID, and tool/database
   provenance for every selected homolog;
5. never relabels a Foldseek structural match as a homolog;
6. selects up to three ranked alternative hypotheses after the top candidate;
7. constructs ordered atomic `query_terms`;
8. constructs up to twelve quoted, source-neutral Boolean `query_variants`;
9. uses the biological run timestamp instead of wall-clock time, making repeated builds
   byte-for-byte deterministic.

The default limits are implementation parameters and are recorded with a stable hash.
They are not learned weights or biological confidence thresholds.

## Query variants

Variants are ordered from exact-query evidence toward broader fallback evidence:

- query accession plus candidate label plus organism;
- query accession plus controlled candidate identifier plus organism;
- protein name plus top candidate label plus organism;
- selected sequence homolog plus top candidate label;
- query identity plus an alternative-hypothesis label.

The expressions use only quoted terms joined by `AND`. They contain no PubMed field
tags. Phase 4.3 may translate syntax for PubMed, but it may not add new biological terms
or labels.

## Outputs

`literature_queries.jsonl` contains one validated `LiteratureQuery` per protein.
`literature_query_manifest.json` contains:

- contract and builder versions;
- source biological run and parameter hashes;
- builder limits and their hash;
- input and output SHA-256 checksums;
- context coverage counts;
- prohibited-input declaration;
- explicit limitations.

## Command

```bash
pixi run python -m dualrag build-literature-queries \
  --run results/my-biological-run \
  --output results/my-literature-queries \
  --context query_context.tsv
```

For FASTA identifiers that already contain valid UniProt accessions, `--context` is
optional unless protein name, organism, or taxonomy is required.

The repository smoke fixture is synthetic and tests only the data flow:

```bash
pixi run smoke-fixture
pixi run python -m dualrag build-literature-queries \
  --run results/pixi-smoke \
  --output results/pixi-smoke-literature-queries \
  --context tests/fixtures/literature_query_context.tsv
```

Synthetic fixture terms are not biological literature queries.

