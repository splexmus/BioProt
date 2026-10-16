# Phase 1 characterized integration run

Date: 2026-10-16 UTC  
Run ID: `a23128c71537f105`  
Input: `tests/fixtures/phase1_characterized.fasta`  
Input SHA-256: `a5d58e0f961406b9f92c891c1120120e3b0a5dfaba66b4257bec9e1ccf662d2e`

This run exercised real eggNOG-mapper, AlphaFold DB REST acquisition, the local
Foldseek PDB database, SIFTS-derived target metadata, normalization, and merge for five
reviewed Swiss-Prot proteins.

## Result summary

- Queries: 5
- eggNOG hits: 5 (one per query under the current parser/top-hit behavior)
- AlphaFold models: 4 downloaded and sequence-compatible
- AlphaFold unavailable: P00720 returned HTTP 404 and was recorded as `NOT_FOUND`
- Foldseek hits: 40 (10 for each query with an AlphaFold model)
- Foldseek hits with UniProt mapping: 40/40
- Foldseek hits with InterPro mapping: 40/40
- Foldseek hits with reviewed protein names: 31/40
- Merged rows: 41

P00720 retained its sequence evidence and became `SEQUENCE_ONLY`; no negative function
claim was made from the missing AlphaFold model. The other 40 pairwise merged rows are
currently labelled `CONFLICT`. That result exposes the known Phase 2 limitation: the
PoC comparator requires exact normalized names or directly shared identifiers and does
not yet reconcile broad eggNOG labels/Pfam identifiers with specific structural names
and InterPro identifiers. These labels must not be interpreted as confirmed biological
conflicts.

Writable cache and outputs were isolated under `/tmp/dualrag-phase1-characterized`;
the biological databases were read from the configured external storage.

## Repeat-run equivalence

The pipeline was run twice with the same input, configuration, database snapshots, and
parameters. Both runs produced run ID `a23128c71537f105`, 5 sequence hits, 40 structure
hits, and 41 merged rows. The second run correctly reused four cached AlphaFold models
while preserving the first run's biological acquisition identities and checksums.

`dualrag compare-runs` reported all seven stable artifacts equivalent:

| Artifact | Stable digest |
| --- | --- |
| `queries.tsv` | `2ca74f121be2183ea0285346ee126491b21f7da36f6c1e4ad51c6254ac19e623` |
| `sequence_results.tsv` | `b83aeca38827a8bdecc8e0115a5f48b2526f6492011a5066db2b1371685249bc` |
| `structure_results.tsv` | `ce33b3568f839e12536a7ffab205cf3bc49a15a27d7a6e2e9c7d5b8e1dc373de` |
| `merged_results.tsv` | `864e759c2ba8f9cba902f8359d49f364c811c964e0347dc5da21c86ff55fbdbd` |
| `alphafold_acquisition.tsv` | `f34512c686f578079bc925d8e2950d18e2baff2f1256eaeed4a419f9492b5cef` |
| `config.snapshot.yaml` | `6419f1a450fdbe4d0146443e4ba82382fb84d93fc7c72d7ea605a2e244fd1272` |
| `run_metadata.json` | `77a3355e4c0f8fd8ebe934b6209f9bc8b6b6cc6d4727dbe75bdfde6a147c6ddb` |

The comparison excludes output-location columns and timestamps, and treats AlphaFold
`DOWNLOADED` and `CACHED` as the same `AVAILABLE` state. Foldseek may finish parallel
queries in a different global block order, so cross-query block order is ignored;
within each query, hit order and all scientific values remain exact comparison fields.
Regression tests verify both sides of that rule. This satisfies the final Phase 1 exit
criterion; function-level interpretation of the current pairwise labels belongs to
Phase 2.

## Pixi migration validation

After Pixi became the supported environment manager, two additional real characterized
runs completed with the same run ID and counts. `dualrag compare-runs` reported all
seven Pixi-to-Pixi artifacts equivalent. The AlphaFold acquisition state was four
`CACHED` models plus the expected P00720 `NOT_FOUND` result.

The historical Conda-to-Pixi comparison intentionally reports non-equivalence in
sequence-derived artifacts and run metadata: Pixi resolved Python 3.11.9 instead of
3.11.6, and eggNOG-mapper 2.1.15 reported a different embedded build identifier. The
retrieved eggNOG values, normalized scores, Foldseek results, AlphaFold identities, and
row counts were unchanged. These provenance differences are preserved rather than
silently normalized away.
