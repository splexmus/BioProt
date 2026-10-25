# Phase 3.2-3.4 benchmark dataset

Dataset ID: `phase3-pilot-v1`  
Contract: `phase3-benchmark-v1`  
Status: development pilot; not a statistically powered final benchmark

## Dataset used

The pilot contains 60 canonical records selected from the locally frozen
UniProtKB/Swiss-Prot 2026_03 release. The source flat file and FASTA are checksummed in
`benchmark/phase3-pilot-v1/source_manifest.json`. The builder scanned all 575,748 source
records and found 45,247 records satisfying the Phase 3 contract before selection.

An eligible record must:

- be reviewed Swiss-Prot with protein existence level 1;
- have a canonical, non-fragment sequence of 40-2,000 standard amino acids;
- have at least one exact EC or GO Molecular Function annotation with accepted
  experimental evidence;
- preserve sequence, taxonomy, entry version, annotation evidence and source release.

Selection is deterministic with seed 42 and round-robin balancing across available
superkingdom groups. The result contains 15 bacterial, 15 eukaryotic, 14 archaeal, 14
viral and 2 records whose first Swiss-Prot lineage is outside those four labels. This
broad pilot tests the machinery; it does not reproduce Swiss-Prot's natural taxonomic
distribution.

There are 43 admissible exact EC labels and 83 admissible experimental GO-MF labels.
InterPro and Pfam cross-references are retained in `domain_labels.tsv` only for
secondary domain-consistency evaluation. They are not accepted as complete-function
gold labels.

EC experimental rows preserve PubMed identifiers from the Swiss-Prot flat file. GO
rows preserve the evidence code and annotation source emitted by Swiss-Prot, but that
flat-file cross-reference does not carry the underlying publication identifier. This
is a pilot limitation and must be enriched from a release-matched GOA snapshot before
promoting the dataset to a final benchmark release.

## Phase 3.2 outputs

- `queries.fasta`: the 60 canonical query sequences;
- `queries.tsv`: sequence checksum, taxonomy, release, entry version and inclusion
  decision;
- `gold_labels.tsv`: exact EC/GO-MF labels plus Tier A/B evidence decisions;
- `domain_labels.tsv`: InterPro and Pfam secondary labels;
- `source_manifest.json` and `CHECKSUMS.sha256`: source and artifact provenance.

## Phase 3.3 leakage control

MMseqs2 16.747c6 clustered the query sequences at 30% identity and 80% bidirectional
coverage using single-step clustering. All 60 queries formed separate clusters. Whole
clusters were assigned with seed 42, producing:

| Split | Queries |
|---|---:|
| Development | 42 |
| Validation | 9 |
| Test | 9 |

`cluster_membership.tsv` and `splits.tsv` preserve these decisions. Gold labels are not
used by the assignment algorithm.

The queries were then searched against the same 575,748-entry Swiss-Prot release with
up to 1,000 candidates per query and at least 70% bidirectional coverage. The leakage
catalog contains 138 prohibited query-target pairs due to exact accession, identical
sequence, or at least 90% identity with at least 80% coverage of both sequences.

`prohibited_targets.tsv` is the frozen reference-sequence exclusion catalog. Phase 3.6
used it to filter B2 targets and SIFTS-resolved PDB chains; unresolved PDB targets were
excluded from the strict primary track. See `docs/PHASE3_REPORT.md` for executed counts.

## Phase 3.4 difficulty strata

After removing prohibited targets, the closest remaining Swiss-Prot reference with at
least 70% bidirectional coverage determines difficulty:

| Stratum | Queries |
|---|---:|
| >70% | 24 |
| 50-70% | 11 |
| 30-50% | 18 |
| 20-30% | 1 |
| <=20% | 0 |
| No allowed hit | 6 |

These are reference-catalog strata, not retrieval-database strata. The final benchmark
report must also calculate the closest allowed eggNOG/PDB-resolved reference used by
each baseline and disclose any changes.

## Rebuild

```bash
PYTHONPATH=src pixi run python scripts/build_phase3_dataset.py \
  --swissprot-dat /path/to/uniprot_sprot.dat.gz \
  --swissprot-fasta /path/to/uniprot_sprot.fasta.gz \
  --source-release 2026_03 \
  --source-sha256 c87208822a56e8ae0d6bf5072c287b35e42a8b9f25e8bd771389abc5b7a29c38 \
  --output benchmark/phase3-pilot-v1 \
  --size 60
```

Use `--resume` only when the query file is unchanged and existing MMseqs2 outputs have
already been inspected. The builder still reconstructs and validates query selection
before reusing those files.
