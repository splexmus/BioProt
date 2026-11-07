# Step 3 merged reviewed benchmark dataset

Dataset ID: `step3-merged-reviewed-v1`  
Frozen source: UniProtKB/Swiss-Prot `2026_03`  
Storage: `/media/splexmus/4TB_HDD1/dualrag/benchmarks/step3-merged-reviewed-v1`

## Construction

The dataset merges these nomination exports by UniProt accession:

- `benchmark/uniprotkb_2026_10_28.tsv`;
- `benchmark/uniprotkb_2026_10_28_v2.tsv`;
- `benchmark/uniprotkb_2026_10_28_v3.tsv`.

For every source, including v2, supplied review status is determined only by a
case-insensitive exact value of `reviewed` in the `Reviewed` column. Protein-existence,
annotation-score, EC, GO, PDB, or publication fields cannot promote an export row marked
`unreviewed`. Frozen Swiss-Prot remains authoritative for sequence, entry version,
taxonomy, protein-level evidence, and Tier-A labels.

The reviewed nomination union contained 1,254 accessions. Screening used the frozen
Phase 3 contract: canonical 40-2,000-residue sequence, standard residues, protein-level
evidence, and at least one admissible experimental EC or GO Molecular Function label.
MMseqs2 then excluded every candidate sharing a 30%-identity/80%-bidirectional-coverage
cluster with either the original 60-protein pilot or any of the 60 external-panel
nominations, including previously rejected nominations.

## Result

| Measure | Result |
|---|---:|
| Included proteins | 788 |
| Query clusters | 660 |
| Development proteins | 552 |
| Validation proteins | 118 |
| Test proteins | 118 |
| Validation query-namespace examples | 171 |
| Test query-namespace examples | 172 |
| EC query proteins | 389 |
| GO-MF query proteins | 776 |
| Prohibited retrieval pairs | 4,277 |

Taxonomic composition is 511 Eukaryota, 180 Bacteria, 88 Archaea, and 9 viruses across
57 organisms. Difficulty against the closest allowed Swiss-Prot reference is:

| Stratum | Proteins |
|---|---:|
| Above 70% identity | 509 |
| 50-70% | 145 |
| 30-50% | 90 |
| 20-30% | 10 |
| No allowed hit | 34 |

The panel passes the numerical Step 3 floor and the minimum 100 validation/test
query-namespace examples. It has only ten 20-30% cases and no explicit below-20% cases
with an allowed hit, so remote-homology conclusions will have limited power and must be
reported separately from aggregate performance.

## Independent validation

- all recorded artifact checksums pass;
- 788 unique query, split, and difficulty rows agree;
- every query has at least one admissible Tier-A label;
- exact exposed-accession overlap is zero;
- exposed sequence-checksum overlap is zero;
- no query cluster crosses a split;
- no v2 row not marked `reviewed` was accepted.

## Scientific status

The original merged directory remains a development source containing all labels. A
pipeline-facing view and procedural test-label vault were created on 2026-10-28:

```text
/media/splexmus/4TB_HDD1/dualrag/benchmarks/step3-merged-reviewed-v1-pipeline
/media/splexmus/4TB_HDD1/dualrag/benchmarks/sealed/step3-merged-reviewed-v1
```

The pipeline view contains development and validation gold only; it has zero test-gold
rows. The vault contains 792 test-label rows for 118 proteins and is mode `0700`, with
files mode `0600`. Its test-label SHA-256 is
`b4e18359502e860bb52e9b30914e21e80cb31d5ff0bf5ebfc2b890bb22568904`.

This is procedural filesystem separation, not historical blinding: the complete source
gold file existed before the seal, the owner can access both locations, and query
accessions/protein names remain visible for retrieval provenance. Therefore the current
dataset supports development and prospective pipeline-level label isolation, but cannot
by itself justify a claim of a previously untouched third-party test. Do not tune
retrieval, mappings, prompts, calibration, or thresholds using vault contents.

Recreate the separated views with `scripts/seal_step3_test_labels.py`. The command
refuses to overwrite either destination.

## Rebuild

```bash
.pixi/envs/default/bin/python scripts/build_step3_merged_dataset.py \
  --nomination benchmark/uniprotkb_2026_10_28.tsv \
  --nomination benchmark/uniprotkb_2026_10_28_v2.tsv \
  --nomination benchmark/uniprotkb_2026_10_28_v3.tsv \
  --swissprot-dat /media/splexmus/4TB_HDD1/dualrag/databases/uniprot/swissprot/current/uniprot_sprot.dat.gz \
  --swissprot-fasta /media/splexmus/4TB_HDD1/dualrag/databases/uniprot/swissprot/current/uniprot_sprot.fasta.gz \
  --pilot-queries benchmark/phase3-pilot-v1/queries.tsv \
  --external-panel benchmark/phase3-external-panel-v1/panel_input.tsv \
  --contract config/benchmark-contract-v1.yaml \
  --output /media/splexmus/4TB_HDD1/dualrag/benchmarks/step3-merged-reviewed-v1 \
  --dataset-id step3-merged-reviewed-v1 \
  --source-release 2026_03 \
  --source-sha256 c87208822a56e8ae0d6bf5072c287b35e42a8b9f25e8bd771389abc5b7a29c38 \
  --mmseqs .pixi/envs/default/bin/mmseqs
```
