# Phase 2 function-level fusion

Phase 2 adds a derived, function-level layer without changing or replacing the Phase 1
retrieval tables. Sequence and structure evidence remain independently inspectable.
The implementation is a transparent baseline for benchmarking, not a calibrated
functional prediction or experimental validation.

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

## Output files

| File | Granularity | Purpose |
| --- | --- | --- |
| `function_candidates.tsv` | candidate per query | grouped evidence, separate modality scores, rank |
| `fusion_summary.tsv` | query | status, reason, counts, top candidate |
| `conflicts.tsv` | conflicting query | compact disagreement report |

The existing `merged_results.tsv` remains the Phase 1 hit-pair table and is not silently
redefined as a function-level result.

## Validation results

The synthetic fixture produces all required states: `CONSENSUS`, `PARTIAL_CONSENSUS`
in focused unit tests, `SEQUENCE_ONLY`, `STRUCTURE_ONLY`, `CONFLICT`, and
`INSUFFICIENT_EVIDENCE`. The complete fixture pipeline emits 23 candidate rows, five
query summaries, and one conflict row.

The 2026-10-16 characterized integration run (`c58a7106523c471c`) used real eggNOG,
AlphaFold acquisition/cache, Foldseek PDB search, and SIFTS/Swiss-Prot target metadata:

- 5 queries
- 5 sequence hits
- 40 structure hits
- 628 grouped candidate rows
- 4 computational `CONFLICT` summaries
- 1 `SEQUENCE_ONLY` summary for P00720 after AlphaFold `NOT_FOUND`

Two final runs under package version 0.2.0 were equivalent across all ten stable Phase 1
and Phase 2 artifacts. The new derived-table digests were:

- `function_candidates.tsv`: `802dc60c6a98bf396a39eead8e378dda17f2e1972fcd387383ef8dea9f0890e0`
- `fusion_summary.tsv`: `616f1aba2755a8c458818b5ba813b32b91f024205c32811158c414e1539f9a7d`
- `conflicts.tsv`: `29115077fff4952fc15b90f39ce69cc6e5601da656b75561db2db83ba27a479e`

The four conflict labels are not confirmed biological disagreements. The sequence
adapter currently exposes large GO sets, EC, Pfam, orthologous groups, and labels, while
the structure metadata exposes InterPro and labels. This version does not include a
versioned Pfam-to-InterPro mapping, GO ontology relationships, EC hierarchy, or curated
synonym mapping. Consequently, compatible functions expressed in different namespaces
remain disjoint. Adding and benchmarking those mappings is the next scientific
improvement, not a reason to hide the present conflicts.
