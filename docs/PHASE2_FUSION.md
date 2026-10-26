# Phase 2 function-level fusion

Phase 2 adds a derived, function-level layer without changing or replacing the Phase 1
retrieval tables. Sequence and structure evidence remain independently inspectable.
The implementation is a transparent baseline for benchmarking, not a calibrated
functional prediction or experimental validation.

`fixed-weight-v1` remains the frozen baseline described below. The production
`quality-gated-v2` profile adds biological-source deduplication, capped independent
support aggregation, structure coverage/TM-score gates, and optional guarded deep-hit
retrieval. Raw scores and v1-compatible evidence remain visible. Its formulas,
configuration, evaluation, and offline-rescoring workflow are documented in
`docs/PIPELINE_V2.md`.

## 2.1 Candidate-function grouping

`dualrag.fusion.candidates` converts each normalized hit into candidate assertions using:

1. EC identifiers
2. GO identifiers
3. InterPro, Pfam, and SUPFAM family/domain identifiers
4. orthologous groups
5. normalized free-text labels

Candidate IDs are namespaced, such as `EC:1.1.1.1`, `GO:0005524`,
`INTERPRO:IPR000001`, or `LABEL:alcohol_dehydrogenase`. Contributions with the same
query and candidate ID are grouped across hits and modalities. The output retains:

- the best normalized score from each modality;
- the count and IDs of supporting sequence and structure hits;
- tool, tool version, database, and database version for each modality;
- all observed labels;
- the candidate type and informativeness decision;
- run ID, parameters hash, fusion version, and rank.

No evidence row is deleted from the Phase 1 outputs. Candidate grouping is an additional
view written to `function_candidates.tsv`.

## 2.2 Informativeness and cross-modal classification

The first rule set is deliberately explicit:

- EC and non-root GO terms are informative controlled function identifiers.
- InterPro, Pfam, SUPFAM, and orthologous groups are informative family-level evidence.
- specific normalized labels are informative fallback evidence.
- GO ontology roots and generic labels such as `hypothetical protein`,
  `uncharacterized protein`, and `unknown function` are retained but marked unclear.

Query status is assigned from informative candidates:

| Condition | Status |
| --- | --- |
| Shared EC, GO, or exact normalized label | `CONSENSUS` |
| Shared family/domain/orthology candidate | `PARTIAL_CONSENSUS` |
| Informative sequence candidates only | `SEQUENCE_ONLY` |
| Informative structure candidates only | `STRUCTURE_ONLY` |
| Both channels informative but candidate sets disjoint | `CONFLICT` |
| Neither channel informative | `INSUFFICIENT_EVIDENCE` |

The query-level result is written to `fusion_summary.tsv`. Exact label matching is
deterministic string normalization, not semantic or LLM-based equivalence.

## 2.3 Fixed-weight baseline and conflict report

The versioned `fixed-weight-v1` development score is:

```text
candidate score = 0.4 * best sequence score
                + 0.4 * best structure score
                + 0.2 * agreement bonus
```

The agreement bonus is `1.0` for candidate-level consensus, `0.5` for partial
consensus, and `0.0` otherwise. Missing modality scores contribute zero. Ties use the
documented candidate-type priority and candidate ID, so ranking is deterministic.

These weights are uncalibrated experimental hyperparameters. The score ranks candidates
within this baseline; it is not a probability, correctness estimate, or final confidence.
Validation/calibration belongs to Phases 3 and 6.

For every query classified as `CONFLICT`, `conflicts.tsv` records the top sequence and
structure candidate IDs, total candidate counts, reason, run ID, and parameters hash.
The configurable `conflict_report_top_k` limits only the compact report; the complete
candidate table is retained.

## 2.4 Versioned cross-namespace mappings

`fusion.mapping_path` may point to a TSV with this required schema:

```text
source_candidate_id  canonical_candidate_id  relation  source  source_version
```

`relation` is one of `EXACT`, `BROADER`, `NARROWER`, or `RELATED`. Only `EXACT`
changes the candidate ID. The other relations support partial compatibility without
claiming identity. The file path and SHA-256 digest are written to the audit.

## 2.5 Curated synonyms

`fusion.synonym_path` may point to a versioned TSV:

```text
normalized_label  canonical_candidate_id  source  source_version
```

Each row is treated as a curated exact mapping from a normalized `LABEL` candidate.
No fuzzy match, embedding similarity, or LLM-generated synonym is accepted.

## 2.6 Candidate consolidation

Exact mapping chains resolve to their declared canonical target. Consolidated rows keep
all original IDs in `candidate_aliases` and all mapping sources in
`mapping_provenance`. Cycles and conflicting exact targets fail the run. Non-exact
relations retain two distinct candidate rows and may change the query state only to
`PARTIAL_CONSENSUS` when the two modalities support the related pair.

## 2.7 Evidence-quality features

Three inspectable features are emitted for each candidate:

- `identifier_quality`: fixed specificity by namespace;
- `modality_support`: one modality is 0.5 and both are 1.0;
- `hit_support`: distinct supporting modality/hit pairs, saturated at three.

The version-1 quality score is `0.5 * identifier_quality + 0.3 * modality_support +
0.2 * hit_support`. It is a ranking feature, not calibrated confidence.

## 2.8 Deterministic reranking

`evidence-quality-v1` retains the Phase 2.3 score as `fused_score` and computes:

```text
rerank_score = 0.8 * fused_score + 0.2 * evidence_quality_score
```

Both weights are configurable and must sum to one. Stable namespace priority and
candidate ID break ties.

## 2.9 Alternatives and ambiguity

`alternatives.tsv` contains the configurable top candidates per query, the score delta
from rank one, and `ambiguous_with_top` when that delta is within
`fusion.ambiguity_margin`. This is a near-tie indicator, not a correctness probability.

## 2.10 Validation and audit

`fusion_audit.json` is deterministic and records mapping input checksums, mapping and
compatibility coverage, status and namespace counts, conflict and alternative counts,
the run/parameter IDs, and limitations. The comparison command includes all Phase 2
tables and the audit in repeat-run equivalence.

## Output files

| File | Granularity | Purpose |
| --- | --- | --- |
| `function_candidates.tsv` | candidate per query | grouped evidence, separate modality scores, rank |
| `fusion_summary.tsv` | query | status, reason, counts, top candidate |
| `conflicts.tsv` | conflicting query | compact disagreement report |
| `alternatives.tsv` | ranked candidate subset | score deltas and near-tie flag |
| `fusion_audit.json` | run | counts, mapping checksums, versions, limitations |

The existing `merged_results.tsv` remains the Phase 1 hit-pair table and is not silently
redefined as a function-level result.

## Validation results

The synthetic fixture produces all required states: `CONSENSUS`, `PARTIAL_CONSENSUS`
in focused unit tests, `SEQUENCE_ONLY`, `STRUCTURE_ONLY`, `CONFLICT`, and
`INSUFFICIENT_EVIDENCE`. Focused tests also exercise exact mappings, curated synonyms,
non-exact relations, reranking, alternatives, and mapping audit checksums. The complete
fixture pipeline emits 23 candidate rows, five query summaries, one conflict row, and
18 alternative rows.

The final 2026-10-21 characterized integration run (`27665c3b0f2402db`) used real eggNOG,
AlphaFold acquisition/cache, Foldseek PDB search, and SIFTS/Swiss-Prot target metadata:

- 5 queries
- 5 sequence hits
- 40 structure hits
- 628 grouped candidate rows
- 25 ranked alternative rows
- 4 computational `CONFLICT` summaries
- 1 `SEQUENCE_ONLY` summary for P00720 after AlphaFold `NOT_FOUND`

No mapping or synonym TSV was configured for this run, so its audit correctly records
zero mapped contributions rather than silently inferring cross-namespace agreement.
Two final runs under package version 0.2.0 were equivalent across all twelve stable
Phase 1 and Phase 2 artifacts. File SHA-256 digests for the final Phase 2 artifacts were:

- `function_candidates.tsv`: `109ae55c945606dc1f8a50a511ae169b969a849964c1e766fbb186040fb24b42`
- `fusion_summary.tsv`: `9feb5afcaaf280910662ea81894b6d90538ef32b78f164b10df7a235e494ca98`
- `conflicts.tsv`: `05a5dbf45d231908e085175e3fbee586c228ccecf9efb9c3a02db592f83758ab`
- `alternatives.tsv`: `584d515a969aef204a0eef979e4c73c5c0bd2659b1fd5123588fa2624fd0e030`
- `fusion_audit.json`: `421f76d2ef9e3e7f3fcec01bbc507bae09327ae6269f156be76085fcf0afc2ef`

The four baseline conflict labels are not confirmed biological disagreements. The sequence
adapter currently exposes large GO sets, EC, Pfam, orthologous groups, and labels, while
the structure metadata exposes InterPro and labels. Without a configured mapping bundle,
compatible functions expressed in different namespaces remain disjoint. GO ontology
relationships and EC hierarchy are still outside this characterized mapping bundle.

## Characterized mapping bundle

On 2026-10-22, `scripts/build_phase2_mapping_bundle.py` resolved the five observed
eggNOG Pfam names against the official Pfam 38.2 name table and verified their integrated
entries through InterPro 110.0. The bundle contains both name and accession forms, ten
conservative full-name synonyms from reviewed UniProtKB/Swiss-Prot 2026_03, exact source
snapshots, review decisions, checksums, and validation outputs.

With the bundle enabled, five Pfam contributions consolidated into InterPro candidates.
The four computational conflicts became `PARTIAL_CONSENSUS`; P00720 remained
`SEQUENCE_ONLY`. No query became `CONSENSUS`. A repeat run with the same configuration
was equivalent across all 12 compared artifacts. The synonym rows were loaded and
audited but none matched this run's observed labels, so the measured status changes came
exclusively from official Pfam-to-InterPro integration mappings.

The bundle is scoped to this characterized smoke set. Its synonym subset is derived
from those reviewed proteins and must not be treated as independent Phase 3 benchmark
truth. Build a benchmark-independent frozen release before evaluation.
