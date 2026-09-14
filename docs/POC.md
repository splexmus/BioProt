# Phase 1 proof of concept

## Scope

The PoC executes the first repository milestone without external databases:

```text
synthetic FASTA
  ├── fixture sequence adapter  -> raw/sequence_hits.tsv -> sequence_results.tsv
  └── fixture structure adapter -> raw/structure_hits.tsv -> structure_results.tsv
                                                    ↓
                                           merged_results.tsv
```

Fixture adapters represent subprocess boundaries. They accept documented TSV rather
than parsing console text. Replacing one adapter does not change the evidence models,
normalizers, merge contract, or output schemas.

## Data contract

Each normalized row contains the minimum fields in `ARCHITECTURE.md` plus:

- `tool_version`, `source_accession`, `parameters_hash`, and `run_id` for provenance;
- `normalized_score` and `normalization_version` for a versioned modality-local feature;
- `raw_output_path` pointing to the preserved run artifact.

Semicolon-separated identifiers are canonicalized by trimming, deduplicating, and
sorting. Blank optional TSV cells map to `None`; no values are fabricated.

The merged table prefixes channel columns with `seq_` and `struct_`. It does not
contain a fused score. Multiple hits are retained as a per-query Cartesian pairing so
the evidence leading to each comparison remains visible.

## PoC normalization

Both scores are bounded to `[0, 1]`. They are ranking features only, not confidence.

Sequence `poc-sequence-v1`:

```text
0.35 identity + 0.30 coverage + 0.25 E-value strength + 0.10 bitscore saturation
```

Structure `poc-structure-v1`:

```text
0.35 TM-score + 0.25 query coverage + 0.15 target coverage
+ 0.15 E-value strength + 0.10 Foldseek-score saturation
```

These formulas are deliberately independent and must be evaluated/calibrated before
research use. They are not weights for a fused biological prediction.

## Agreement rules

- exact normalized function label: `CONSENSUS`;
- shared InterPro identifier: `PARTIAL_CONSENSUS`;
- hit in only one channel: `SEQUENCE_ONLY` or `STRUCTURE_ONLY`;
- hits in both channels without shared label/domain: `CONFLICT`;
- no hits: `INSUFFICIENT_EVIDENCE`.

This is a transparent baseline. Production comparison should add GO/EC/ontology
relations and must benchmark thresholds on curated validation data.

## Reproducibility artifacts

`run_id` is the first 16 characters of a SHA-256 hash over the input checksum and
validated resolved configuration. Repeated runs with those inputs produce equivalent
normalized TSVs. `run_metadata.json` has runtime context and timestamp, while
`config.snapshot.yaml` and `commands.log` capture the resolved settings and adapter
operations.

## External-data handoff

External mode fails closed. Before enabling it:

1. record real executable and database versions in a machine-readable manifest;
2. implement eggNOG against its local database using documented TSV formats;
3. implement AlphaFold DB REST lookup, raw JSON preservation, bounded caching, and an
   acquisition manifest;
4. implement Foldseek against its local target database using documented TSV formats;
5. preserve unmodified tool/API outputs beneath the run's `raw/` directory;
6. mock subprocess and HTTP boundaries in unit tests;
7. run the smoke fixture plus a small characterized-protein integration set.

AlphaFold and PDB provenance must remain distinct, including the
`experimental_structure` field. An external hit cannot be described as experimental
unless its source explicitly supports that claim.
