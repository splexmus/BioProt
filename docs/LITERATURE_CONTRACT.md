# Phase 4 literature retrieval contract

Contract ID: `phase4-literature-v1`  
Status: frozen for Phase 4.2-4.7 implementation  
Machine-readable form: `config/literature-contract-v1.yaml`

## Purpose and scope

This contract defines what DualRAG considers relevant literature and how retrieved text
may be represented before search adapters, ranking, or evaluation are implemented. It
covers PubMed metadata/abstract retrieval, PMC Open Access full text, deterministic
query construction, document normalization, retrieval, reranking, and compact evidence
packets. It does not authorize Phase 5 LLM generation.

Literature contextualizes candidate functions produced by biological retrieval. It
does not override stronger sequence or structure evidence and cannot convert a putative
function into experimental confirmation.

## Unit of retrieval

The retrieval unit is a passage (`LiteratureChunk`) from one uniquely resolved article.
Article identity is deduplicated in this order:

1. PMID;
2. PMCID;
3. normalized DOI;
4. source-specific article identifier when none of the above exists.

The system ranks passages but preserves their parent article metadata. Duplicate
versions must be linked rather than counted as independent support.

## What counts as relevant

A passage is relevant when it materially helps assess one of the query protein's
retrieved candidate functions and satisfies at least one of these conditions:

- it studies the exact query accession or an explicitly resolved equivalent;
- it studies a provenance-linked homolog and connects an experiment to the candidate
  function;
- it reports an assay, phenotype, perturbation, binding observation, catalytic result,
  or structural result that bears directly on the candidate;
- it contains a credible contradiction or boundary condition for the candidate.

A family name, shared domain, pathway mention, or keyword match without a traceable
protein/function connection is background at most. It is not direct support.

## Evidence roles

Each retrieved hit begins as `UNASSESSED`. A later manual gold label or explicit,
versioned classifier may assign one of these roles:

- `SUPPORT`: a primary experimental passage reports evidence consistent with the
  candidate claim and links it to the exact protein or a clearly identified homolog;
- `CONTRADICTION`: a primary experimental passage reports an incompatible function,
  loss of the proposed activity under an appropriate test, different specificity, or
  another result that directly challenges the candidate;
- `BACKGROUND`: useful context, methods, prior-knowledge summary, family/domain
  information, or a review without direct primary evidence for the claim;
- `IRRELEVANT`: no material connection to the candidate after entity and organism
  checking;
- `UNASSESSED`: retrieval output not yet assigned an evidence role.

Absence of a relevant paper, missing abstract, missing full text, or retrieval failure
is never a contradiction and never evidence that the proposed function is absent.

## Primary articles and reviews

Reviews are acceptable for terminology, background, alternative hypotheses, and
finding primary references. In contract v1, a review passage cannot receive `SUPPORT`
or `CONTRADICTION`; those roles require a primary experimental article and a passage
containing the relevant result. An abstract from a primary article may be retrieved and
ranked, but its `ABSTRACT_ONLY` status must remain visible and it should rank below an
equivalent results passage from legally available full text.

Methods passages establish assay context but do not alone prove the reported result.
Introduction passages are background unless they contain a clearly attributable result
from the current study. Results passages and reliable figure/table captions receive the
strongest section prior; discussion text is supportive only when traceable to a result
in the same article.

## Entity and organism compatibility

Entity matching is recorded independently from relevance:

- `EXACT_ACCESSION`: exact query accession or documented replacement;
- `EXACT_NAMED_PROTEIN`: exact protein and organism but accession not stated;
- `TRACEABLE_HOMOLOG`: homolog accession or relationship is explicit and provenance is
  retained;
- `FAMILY_ONLY`: only a family/domain-level relationship;
- `NONE` or `UNRESOLVED`.

Organism matching is one of `EXACT_TAXON`, `SAME_SPECIES`, `RELATED_TAXON`,
`HETEROLOGOUS_SYSTEM`, `MISMATCH`, or `UNRESOLVED`. The source organism and assay host
must not be collapsed. Evidence from a homolog or heterologous system remains labelled
and cannot silently become exact-protein evidence.

Protein names alone are insufficient when they are ambiguous. A valid hit must retain
the text span or structured identifier that produced the entity assignment.

## Retrieval limits

For each protein query, contract v1 returns at most:

- 10 unique articles;
- 20 total passages;
- 3 passages from one article;
- 1,200 characters per passage after normalization.

Adapters may retrieve a larger candidate pool before ranking. Limits are applied only
after identifier deduplication and entity checks. Contradictions are not removed to make
room for additional supportive passages. If fewer valid passages exist, the packet is
smaller and records the reason; padding with weak matches is prohibited.

## Query-construction boundary

Literature queries may use only:

- query accession, protein name, organism, and taxonomy;
- Phase 2/3 candidate identifiers and labels;
- selected sequence-homolog accessions with identity, coverage, score, and retrieval
  provenance;
- alternative hypotheses;
- cross-modal status.

Gold benchmark labels, evaluation annotations, held-out answers, and manually assigned
literature relevance labels must never construct or expand a query. `LiteratureQuery`
uses an extra-fields-forbidden schema so accidental `gold_labels` or similar fields fail
validation. Query clauses, normalization, escaping, and source-specific translation
must be deterministic and versioned.

`query_terms` contains the ordered atomic terms used by the builder, while
`query_variants` contains complete source-neutral Boolean expressions. A source adapter
may translate field syntax but must not add biological terms or labels.

## Source and access policy

- PubMed supplies identifiers, bibliographic metadata, titles, abstracts, and
  publication types.
- PMC Open Access supplies legally available full text.
- A PMID does not imply that full text is available or licensed for ingestion.
- Publisher pages may be stored as links/metadata unless a separate license permits
  text processing.
- Every acquisition records its source URL, retrieval time, status, and error if any.

Full-text states include `PMC_OPEN_ACCESS`, `ABSTRACT_ONLY`, `METADATA_ONLY`,
`NOT_OPEN_ACCESS`, `NOT_FOUND`, and `RETRIEVAL_ERROR`. These describe access, not
scientific relevance.

## Required provenance

The end-to-end record chain must preserve:

- PMID, PMCID, DOI, title, year, and journal where available;
- query protein, organism/taxonomy, candidate IDs, homologs, and exact query terms;
- article source and URL, acquisition time, and full-text state;
- section type, passage offsets, text checksum, and chunker version;
- lexical, vector, hybrid, and reranker scores when produced;
- final score, rank, retriever/reranker versions, and random seed where applicable;
- entity/organism assignments, evidence role, assignment method, and uncertainty;
- source biological run IDs and parameter hashes.

Raw source responses must be preserved separately from normalized metadata and chunks.

## Schema flow

```text
Phase 2/3 candidates
        ↓
LiteratureQuery
        ↓
ArticleMetadata ──→ LiteratureChunk ──→ LiteratureHit
                                                ↓
BiologicalEvidenceReference ─────────→ EvidencePacket
```

| Record | Purpose |
|---|---|
| `LiteratureQuery` | Frozen, leakage-safe input to deterministic query construction |
| `ArticleMetadata` | Source response normalized at article level, including access state |
| `LiteratureChunk` | Standalone, checksummed passage with citation and section context |
| `LiteratureHit` | Query-to-passage ranking result plus entity, organism, and evidence role |
| `BiologicalEvidenceReference` | Compact pointer back to sequence/structure/domain evidence |
| `EvidencePacket` | Bounded set of biological references, literature hits, alternatives, contradictions, and claim boundaries |

Citation fields are intentionally repeated on `LiteratureChunk` so a serialized index
record remains traceable even when loaded independently from the article table. Python
models are in `src/dualrag/literature/schemas.py`; their exported JSON Schema is
`config/literature-schemas-v1.json`.

## Evidence packet boundary

An `EvidencePacket` contains compact references to sequence, structure, and
domain/ontology evidence plus selected literature hits, alternatives, contradictions,
and claim boundaries. It must not contain complete database dumps or entire papers.
Every literature statement must remain traceable to an article and passage.

The packet is evidence for a later synthesis layer; it is not itself a final function
call or calibrated confidence score.

## Evaluation gate

Phase 4.2-4.6 may proceed using this frozen contract. Phase 4 is not complete until a
manually labelled, versioned dataset evaluates passage-level Precision@K, Recall@K, MRR
or nDCG, citation precision/recall, entity correctness, organism correctness, primary-
experiment retrieval, and contradiction retrieval.

Only after those metrics and error analyses pass a separately frozen acceptance rule
may Phase 5 use literature packets for report generation.

The operational v2 exit evaluation uses a completely judged PubMed candidate pool and
reports pooled recall, not absolute recall over all literature. The final packet limits
do not truncate this evaluation pool. At least 20 human-labelled queries, five labelled
contradiction passages, complete pool judgments, and every threshold in
`config/literature-evaluation-v2.yaml` are required for `PASS`.

## Versioning rule

Changing evidence-role definitions, permitted query inputs, review policy, entity or
organism semantics, final article/chunk limits, or evaluation acceptance rules requires
a new contract version. Editorial clarifications that do not change behavior may amend
this document while retaining the contract ID.

