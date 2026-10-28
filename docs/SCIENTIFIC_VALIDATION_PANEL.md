# Step 3 scientific-validation panel plan

## Objective

Build a new, versioned characterized-protein panel for confirmatory evaluation. The
panel must contain at least 200 eligible proteins, but collection continues until a
cluster-aware split can supply at least 100 validation and 100 untouched-test
query-namespace examples. With a 70/15/15 split and sparse labels, the practical target
is approximately 800 proteins rather than stopping automatically at 200.

This panel is independent of the exposed Phase 3 pilot and the later 60-protein external
candidate panel. It evaluates the frozen retrieval, fusion, literature, report, and
calibration pipeline; it is not used to tune prompts or thresholds after test labels are
revealed.

## Frozen eligibility contract

Use `config/benchmark-contract-v1.yaml` unless a versioned v2 contract is approved
before collection. Each included query must have:

- a canonical UniProtKB/Swiss-Prot accession and sequence;
- evidence at protein level;
- length from 40 through 2,000 standard amino acids, with no fragment flag;
- sequence SHA-256, entry version, source release, and database checksum;
- at least one admissible Tier-A full EC or experimental GO Molecular Function label;
- label evidence code, supporting reference, namespace, identifier, and inclusion reason.

Accepted experimental GO codes remain `EXP`, `IDA`, `IPI`, `IMP`, `IGI`, `IEP`, `HTP`,
`HDA`, `HMP`, `HGI`, and `HEP`. A full EC requires experimental catalytic support.
Tier-B curator inference may be retained for sensitivity analysis but cannot support the
primary correctness claim.

## Exclusion and leakage rules

Before selection, create a frozen exclusion ledger containing:

1. all accessions and sequence checksums from the existing Phase 3 60-protein pilot;
2. all accessions and checksums from the external 60-protein panel, including rejected
   candidates;
3. every member of their MMseqs2 clusters at 30% identity and 80% bidirectional coverage;
4. obsolete, merged, fragment, ambiguous-sequence, or unresolved-label records.

After panel selection, cluster the new queries together with all exposed queries. Assign
whole new clusters to one split only. No exposed-query cluster may enter the new panel.
During retrieval, continue excluding exact accessions, identical sequences, and targets
with at least 90% identity and 80% bidirectional coverage. Apply the same exclusion to
sequence and SIFTS-resolved structure targets.

## Selection strategy

1. Freeze one Swiss-Prot release and record flat-file and FASTA checksums.
2. Stream all eligible Tier-A records and apply the exclusion ledger.
3. Build selection strata for taxonomy, EC versus GO-MF availability, sequence length,
   membrane/soluble status when available, and functional family.
4. Draw a deterministic seed-42 candidate pool of at least 1,500 proteins, balanced
   across major superkingdoms without forcing biologically impossible equal counts.
5. Run MMseqs2 reference searches and calculate closest-allowed-reference difficulty.
6. Prefer enough 20-30%, below-20%, and no-allowed-hit proteins to make remote-homology
   conclusions estimable; record the achieved counts instead of inventing balance.
7. Select an initial 800-query panel, cluster it, and count query-namespace examples per
   split. Expand deterministically if validation or test has fewer than 100.

The current `select_balanced_entries` helper balances only by superkingdom. It must be
extended or wrapped for multi-stratum selection and explicit exposed-cluster exclusion
before this dataset is built.

## Required artifacts

Store the dataset outside Git and large databases on the configured HDD. Keep the small
contracts and summaries in the repository. The dataset directory must contain:

```text
queries.fasta
queries.tsv
gold_labels.tsv
domain_labels.tsv
exposed_queries.tsv
exclusion_ledger.tsv
mmseqs_clusters.tsv
cluster_membership.tsv
splits.tsv
difficulty_strata.tsv
prohibited_targets.tsv
source_manifest.json
selection_manifest.json
summary.json
commands.log
CHECKSUMS.sha256
```

Gold labels for the untouched test split must be exported to a separately permissioned
or encrypted location before any test retrieval begins. The pipeline-facing test query
manifest contains sequences and provenance but no gold function labels.

## Acceptance checks

Step 3 is complete only when:

- every row passes the frozen eligibility and provenance schema;
- no exposed accession, checksum, or 30%/80% cluster is present;
- the panel has at least 200 proteins and the achieved split has at least 100 validation
  and 100 test query-namespace examples;
- each split reports taxonomy, namespace, family, length, and difficulty distributions;
- no single cluster is divided between splits;
- test labels are sealed and their checksum is recorded before pipeline execution;
- a second validator reproduces all row counts and checksums from the manifests.

## Implementation checkpoints

1. Add an exclusion-ledger builder and tests for accession, checksum, and cluster overlap.
2. Add deterministic multi-stratum selection with an adaptive panel-size loop.
3. Add a label-sealing export that prevents test gold from entering evidence packets.
4. Generate a small synthetic fixture and prove the exclusion and split invariants.
5. Build the real panel on the HDD, validate it, and write a dataset report before
   running Phase 1-5.
