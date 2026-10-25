# Phase 3 benchmark contract

Contract ID: `phase3-benchmark-v1`  
Status: frozen for Phase 3.2 dataset construction  
Machine-readable form: `config/benchmark-contract-v1.yaml`

## Purpose and scope

This contract defines what DualRAG will count as a correct protein-function result
before collecting the benchmark dataset or implementing metrics. It covers only:

- **B2:** sequence retrieval;
- **B3:** structure retrieval;
- **B4:** deterministic dual retrieval.

Literature, LLM, graph, and calibrated-confidence layers are outside Phase 3. Each query
is one canonical protein and may have multiple correct functions.

## Primary endpoint

The single primary endpoint is **macro Function Recall@10 (`FR@10`)** over exact EC and
GO Molecular Function identifiers.

For each query:

1. rank candidates within each namespace;
2. compute exact Recall@10 against the admissible EC gold set, when present;
3. compute exact Recall@10 against the admissible GO Molecular Function gold set, when
   present;
4. average the available namespace scores for that query;
5. macro-average the per-query values.

The confirmatory contrast is `B4 - B2`. Its 95% confidence interval uses a paired
query-level bootstrap with 10,000 replicates and seed 42. B4 versus B3 is secondary.

InterPro and Pfam are deliberately excluded from the primary endpoint. A matching
domain or family is useful evidence, but it does not by itself establish the complete
function of a protein.

## What counts as correct

An exact prediction is correct only when the normalized controlled identifier occurs in
the frozen admissible gold set for the query. Mapping-derived predictions are allowed
only when the mapping release was frozen before test evaluation and was constructed
independently of benchmark labels. Free-text labels never count as automatic truth.

### EC

- Exact correctness requires all four EC levels.
- Incomplete EC gold labels do not enter the exact endpoint.
- Hierarchical partial credit is the number of common leading EC levels divided by four.
- Partial EC credit is a secondary diagnostic and never an exact hit.

### GO Molecular Function

- Only the Molecular Function namespace is scored automatically in version 1.
- `GO:0003674` is a root, not an informative gold label.
- Hierarchical propagation uses only `is_a` relations.
- An obsolete term is replaced only when it has exactly one `replaced_by`; otherwise the
  term is excluded with a reason.
- Semantic similarity uses Lin best-match average with information content calculated
  from a frozen reviewed-UniProt GO-MF corpus. It is secondary.

### InterPro and Pfam

- Exact InterPro and Pfam consistency are secondary endpoints.
- InterPro ancestor consistency and Pfam clan consistency are reported separately.
- Neither family/domain endpoint counts as exact functional correctness.
- A Pfam-to-InterPro integration can establish family-level partial agreement, not
  complete-function consensus.

## Gold-standard evidence

The primary Tier A set uses canonical UniProtKB/Swiss-Prot proteins with evidence at the
protein level and at least one admissible experimentally supported EC or GO-MF label.

Accepted GO experimental evidence codes are:

```text
EXP IDA IPI IMP IGI IEP HTP HDA HMP HGI HEP
```

An EC label must be a full reviewed EC assignment with experimental catalytic support.
The manifest must preserve the evidence code, supporting reference, source release, and
the decision that made every label admissible. Reviewed curator inference that does not
meet Tier A is retained as Tier B for sensitivity analysis, never for the primary claim.

Required query properties:

- canonical sequence and SHA-256;
- length 40–2,000 amino acids;
- no fragment flag or ambiguous/non-standard sequence;
- stable, non-obsolete accession or a unique documented replacement;
- at least one Tier A EC or GO-MF label.

Multiple functions do not exclude a protein. Missing AlphaFold models also do not
exclude it, because that would bias the structure-channel evaluation. A missing
nonprimary namespace removes the query only from that namespace denominator.
Uncharacterized proteins belong to a separate coverage study with no accuracy claim.

## Leakage control

### Dataset splits

MMseqs2 clusters use at least 30% identity and 80% bidirectional coverage. Entire
clusters—not individual proteins—are assigned to development, validation, or test using
a 70/15/15 target ratio and seed 42. The final achieved ratios and cluster counts must be
reported; they need not be forced by splitting a cluster.

### Search-target exclusions

Before scoring, exclude:

1. the exact query accession;
2. an identical sequence checksum;
3. targets with at least 90% alignment identity and at least 80% bidirectional coverage.

Alignment identity is identical aligned residue pairs divided by aligned residue pairs.
Coverage is aligned residues divided by full sequence length, calculated independently
for query and target. Structure-target homology is calculated from the target protein
sequence resolved through SIFTS, not from Foldseek's structural score or its local
sequence-identity field.

The rule applies to sequence and structure targets. Structure targets are resolved
through SIFTS. A structure target without resolvable accession provenance is excluded
from the strict primary track and may appear only in a labelled sensitivity analysis.

Retrievers must request at least 100 hits, apply exclusions, and then score the first
allowed 1, 5, and 10 results. Filtering an already truncated top-10 list is invalid.
Any adapter that cannot expose a stable target ID and the information needed for these
exclusions cannot contribute primary retrieval metrics.

Gold labels must never enter the fusion evidence packet. Test labels remain hidden until
the dataset, mappings, parameters, and code are frozen. Smoke-set-derived synonym files,
including the Phase 2 characterized bundle, are prohibited from the primary benchmark.

## Secondary metrics

Retrieval:

- Recall@1, @5 and @10;
- Precision@K;
- MRR and nDCG;
- candidate coverage.

Cross-modal:

- union recall and intersection coverage;
- structure and sequence rescue rates;
- conflict rate;
- incorrect-consensus rate.

Function and family:

- exact and hierarchical EC;
- exact GO-MF recall and semantic similarity;
- exact and ancestor-aware InterPro consistency;
- exact Pfam and clan consistency;
- top-K function recall.

Every metric must report its numerator, denominator, query count, missingness, point
estimate, 95% interval, and per-query values.

## Difficulty strata

Difficulty is the alignment identity to the closest **allowed** reference with at
least 70% coverage:

```text
>70%, 50–70%, 30–50%, 20–30%, <=20%, no allowed hit
```

Report results by difficulty, taxonomy superkingdom, and enzyme/non-enzyme group.
Subgroup and mapping-ablation tests are exploratory and use Holm-adjusted p-values.

## Claim rules

Dual retrieval may be claimed to improve overall performance only when the paired 95%
confidence interval for `B4 - B2` on test-set `FR@10` is entirely above zero. A benefit
limited to a difficulty stratum must be reported as a qualified subgroup result. If the
primary interval includes zero, report no measurable overall benefit even when secondary
or qualitative results are interesting.

Scores produced by Phase 2 remain ranking features, not confidence estimates.

## Required outputs for later Phase 3 steps

Every benchmark run must eventually preserve:

- this contract and its checksum;
- query, label, cluster, split, and prohibited-target manifests;
- database, mapping, ontology, software, and Pixi-lock versions;
- commands, configuration, Git state, and random seed;
- raw and normalized retrieval results;
- per-query and aggregate metrics with confidence intervals;
- exclusions, missingness, and biological error-analysis assignments.

The query manifest must include accession, canonical sequence and checksum, length,
organism/taxonomy, protein-existence status, database release, and inclusion decision.
Every gold-label row must include namespace, identifier, evidence tier/code, supporting
reference, source release, primary-admissibility flag, and decision reason. Every
prohibited-target row must include query, target, modality, exclusion reason, identity,
both coverages, and identifier-resolution source.

## Gate to Phase 3.2

Dataset collection may begin only if each proposed record can express the evidence,
sequence, release, and exclusion fields required above. Any change to the primary
endpoint, Tier A evidence policy, or leakage thresholds creates a new contract version;
it must not silently modify `phase3-benchmark-v1`.
