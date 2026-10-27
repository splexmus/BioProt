# ARCHITECTURE.md

## 1. System objective
Build a modular, reproducible pipeline that retrieves functional evidence for a query protein from independent sequence and structure channels, fuses those signals at the function level, optionally retrieves literature, and generates an evidence-linked research report.

## 2. Major components

```text
Input
  ↓
Query Resolver
  ├─ Sequence Retriever
  └─ Structure Retriever
         ↓
Evidence Normalizer
         ↓
Function Candidate Builder
         ↓
Cross-Modal Comparator
         ↓
Fusion / Reranking
         ↓
Optional Literature Retriever
         ↓
Context Builder
         ↓
Optional LLM Generator
         ↓
Citation Verifier + Confidence Calibrator
         ↓
Final Research Report
```

## 3. Input layer
Supported target inputs:

- UniProt accession
- FASTA sequence
- batch FASTA
- future: natural-language question resolving to one or more proteins

Implemented Phase 1 query model:

```python
class ProteinQuery:
    query_id: str
    sequence: str
    description: str | None
```

## 4. Sequence retrieval

### Responsibilities
- run eggNOG-mapper / MMseqs2-based annotation against locally stored databases
- optionally run HMMER, BLAST, or DIAMOND baselines
- retain raw evidence and normalized annotation identifiers

### Minimum output schema

```text
query_id
target_id
tool
database
database_version
sequence_identity
alignment_coverage
evalue
bitscore
orthologous_group
protein_name
go_terms
ec_numbers
kegg_terms
interpro_ids
pfam_ids
raw_output_path
```

Not every tool supplies every field; missing values must be explicit nulls, not fabricated.

## 5. Structure retrieval

### Responsibilities

1. resolve a UniProt accession from the input or an explicit, provenance-bearing mapping step
2. request AlphaFold DB metadata through its REST API
3. download and cache only the required predicted PDB/mmCIF model
4. execute Foldseek locally against the configured local structural database
5. map structural hits to protein identifiers/functional metadata
6. optionally retrieve experimental PDB structures through a separate, labelled adapter

AlphaFold DB is the query-model acquisition service. It is not the structural search
backend: Foldseek and its target database remain local.

The Phase 1 resolver accepts only a validated bare UniProt accession or a standard
`sp|ACCESSION|...` / `tr|ACCESSION|...` FASTA identifier. Other identifiers produce an
`ACCESSION_UNRESOLVED` acquisition row and do not disable the sequence branch. If the
AlphaFold metadata includes `uniprotSequence`, it must exactly match the query sequence.

### AlphaFold acquisition manifest

Keep one record per attempted model lookup, including unsuccessful lookups:

```text
query_id
requested_uniprot_accession
resolution_method
api_base_url
request_url
http_status
alphafold_entry_id
model_version
structure_format
source_structure_url
retrieved_at
sha256
cache_path
status
sequence_compatible
```

Suggested status values are `CACHED`, `DOWNLOADED`, `NOT_FOUND`, `HTTP_ERROR`, and
`ACCESSION_UNRESOLVED`. Preserve the raw JSON response separately. Do not fabricate a
structure when the API has no model for the query.

### Minimum output schema

```text
query_id
target_structure_id
target_uniprot_id
tool
database
database_version
foldseek_evalue
foldseek_score
tm_score
alignment_length
query_coverage
target_coverage
sequence_identity
protein_name
go_terms
ec_numbers
interpro_ids
supfam_ids
structure_source
experimental_structure
raw_output_path
```

If Foldseek output does not include a field directly, do not infer it unless a documented post-processing step computes it.

Foldseek itself does not supply function labels. An optional target-metadata TSV joins
`target_structure_id` to chain-level SIFTS UniProt, GO, EC and InterPro annotations,
plus protein name, SUPFAM identifiers, source, experimental status, and source
accession. Missing metadata stays null. Phase 3 uses the SIFTS-resolved UniProt sequence
catalog—not Foldseek `fident`—for strict close-homolog exclusions.

## 6. Evidence normalization
Raw metrics have different scales and meanings. Keep both raw and normalized values.

Example normalized evidence object:

```json
{
  "query_id": "Q9XXXX",
  "candidate_function_id": "EC:6.2.1.1",
  "candidate_function_label": "acetyl-CoA synthetase",
  "modality": "sequence",
  "normalized_score": 0.91,
  "raw_metrics": {
    "identity": 0.72,
    "coverage": 0.95,
    "evalue": 1e-80
  },
  "provenance": {
    "tool": "eggnog-mapper",
    "tool_version": "...",
    "database": "eggNOG",
    "database_version": "..."
  }
}
```

Normalization functions must be versioned and benchmarked.

## 7. Candidate-function builder
Group heterogeneous hits by candidate biological function rather than by target protein alone.

Preferred identifiers, from strongest structured representation to weaker free text:

1. EC identifier where applicable
2. GO term(s)
3. InterPro/Pfam/domain family
4. orthologous group
5. normalized protein/function label

Do not treat two free-text descriptions as equivalent solely because an LLM says they are similar. Use controlled identifiers/ontology relations when possible, semantic similarity only as supplemental evidence.

Implemented Phase 2.1 writes `function_candidates.tsv`. Candidate rows retain separate
best sequence and structure scores, source-hit IDs/counts, informativeness decisions,
candidate-level status, deterministic rank, fusion version, and run provenance.

## 8. Cross-modal comparison
Required status enum:

```python
CrossModalStatus = Literal[
    "CONSENSUS",
    "PARTIAL_CONSENSUS",
    "SEQUENCE_ONLY",
    "STRUCTURE_ONLY",
    "CONFLICT",
    "INSUFFICIENT_EVIDENCE",
]
```

Possible first-pass logic:

```text
informative seq + informative struct + compatible function -> CONSENSUS
informative seq + informative struct + same family/broader relation -> PARTIAL_CONSENSUS
informative seq only -> SEQUENCE_ONLY
informative struct only -> STRUCTURE_ONLY
informative seq + informative struct + incompatible -> CONFLICT
neither informative -> INSUFFICIENT_EVIDENCE
```

Implemented Phase 2.2 writes one query-level decision and reason to
`fusion_summary.tsv`. Root GO terms and explicitly generic free-text labels are retained
as unclear candidates instead of being discarded. Exact label normalization is a
deterministic fallback; ontology and cross-namespace mappings are never inferred.

Phase 2.4-2.6 optionally load versioned mapping and synonym TSVs. `EXACT` relations
consolidate candidates under the declared canonical ID while retaining aliases and
mapping provenance. `BROADER`, `NARROWER`, and `RELATED` relations can establish
partial compatibility but never exact consensus or candidate merging. Every input is
checksummed in `fusion_audit.json`.

## 9. Fusion / reranking
A simple development score may be used only as a baseline:

```text
S(function) =
  w_seq * S_seq
+ w_struct * S_struct
+ w_domain * S_domain
+ w_agree * S_agreement
+ w_lit * S_literature
```

Implemented Phase 2.7-2.8 keeps the fixed-weight score and exposes three separate
quality features: identifier specificity, modality support, and independent-hit
support. `evidence-quality-v1` reranks with `0.8 * fixed score + 0.2 * quality score`.
Both components and all features remain in `function_candidates.tsv`; none is a
probability or calibrated confidence.

The production `quality-gated-v2` profile extends this baseline without collapsing the
modalities. It deduplicates evidence by biological accession, applies a capped bonus
for independent sources, retains raw modality maxima, and adjusts structure-derived
function transfer using query coverage, target coverage, and TM-score. Low-rank
functions from target pools deeper than ten require three independent supports and are
downweighted. All gates, ranks, raw scores, adjusted scores, and counts remain auditable.
The frozen `fixed-weight-v1` profile remains reproducible for benchmark comparison.

Phase 2.9 writes `alternatives.tsv` with deterministic top candidates, score deltas,
and a configurable near-tie flag. Phase 2.10 writes `fusion_audit.json` with status and
candidate counts, mapping checksums, mapping coverage, and explicit limitations. Both
files participate in repeat-run comparison.

Weights are hyperparameters to be calibrated on validation data. The project should compare:

- fixed weighted sum
- learning-to-rank / logistic calibration
- pairwise reranker
- ontology-aware consensus score

Implemented Phase 2.3 uses the versioned baseline
`0.4 * sequence + 0.4 * structure + 0.2 * agreement`, where exact function agreement
has bonus 1.0 and shared family evidence has bonus 0.5. It emits `conflicts.tsv` for
disjoint informative modalities. The fused value is a ranking feature, not confidence.

## 10. Literature retrieval
Literature retrieval is downstream of candidate function creation.

Phase 4.0-4.1 freezes contract `phase4-literature-v1` and defines typed
`LiteratureQuery`, `ArticleMetadata`, `LiteratureChunk`, `LiteratureHit`,
`BiologicalEvidenceReference`, and `EvidencePacket` records. Query records accept only
protein/candidate evidence from upstream retrieval and forbid undeclared fields, which
prevents benchmark gold labels from silently entering query construction. All records
use explicit identifiers, source/access states, timezone-aware timestamps, and
versioned processing provenance.

Literature hits are passage-level records. Article metadata remains attached through
PMID/PMCID/DOI and source article ID; chunks retain section, offsets, checksum, source
URL, access status, and chunker version. Evidence-role assignment is separate from the
retrieval score. Direct support or contradiction requires a primary experimental
passage and an explicit entity-match basis; reviews are background only in v1.

Evidence packets enforce the frozen limits of 10 unique articles, 20 passages, and 3
passages per article. They reference compact upstream biological evidence rather than
copying full result tables or papers. See `docs/LITERATURE_CONTRACT.md`.

Phase 5.1 fills those compact biological references from leakage-filtered Phase 3
evidence, bounded to five sequence and five structure hits per query. Each record keeps
raw metrics, normalized rank, annotations, tool/database versions, artifact provenance,
and experimental-versus-predicted structure status when available. The current benchmark
uses MMseqs2/Swiss-Prot for its rankable sequence channel and Foldseek/PDB-SIFTS for its
structure channel. No gold labels enter this enrichment step.

Phase 4.2 implements the deterministic boundary between biological retrieval and source
adapters. `build-literature-queries` reads only the query, candidate, fusion,
alternative, sequence-hit, and run-provenance artifacts. It selects ranked informative
candidates and provenance-bearing sequence homologs, then emits atomic terms and
source-neutral Boolean variants. Structural matches are not automatically labelled as
homologs. PubMed field syntax, transport, and returned query translation remain inside
the Phase 4.3 adapter.

Phase 4.3-4.6 is implemented in `dualrag.literature`. The PubMed adapter performs
deterministic ESearch followed by batched XML EFetch, and the PMC adapter requires a
positive PMC OA-service response before acquiring full text. Raw responses and parsed
records remain separate. Section-aware chunks feed independently normalized BM25 and
character-trigram vector scores; a versioned rule reranker adds entity, organism, and
section features without assigning support. The packet builder enforces the frozen
article/chunk limits and retains `UNASSESSED` roles. Phase 4.7 reads manual labels only
after retrieval and emits descriptive metrics; it never feeds labels back into queries.

Inputs:
- query protein
- organism/taxonomy
- top function candidates
- selected homolog identifiers

Sources:
- PubMed
- PMC Open Access where full text is required

Prefer section-aware chunking:
- title/abstract
- methods
- results
- discussion
- protein-specific paragraphs
- figure/table captions when parsed reliably

Metadata to retain:
- PMID/PMCID
- DOI
- title
- year
- journal
- section
- source URL/identifier
- retrieval score

## 11. Context builder
Never send complete raw result files to the LLM. Build a compact evidence packet:

```text
QUERY
SEQUENCE EVIDENCE
STRUCTURE EVIDENCE
DOMAIN/ONTOLOGY EVIDENCE
CROSS-MODAL STATUS
LITERATURE EVIDENCE
ALTERNATIVE HYPOTHESES
INSTRUCTIONS / CLAIM BOUNDARIES
```

Phase 5 context contract v2 exposes biological records as
`SEQUENCE_RETRIEVAL_HIT` and `STRUCTURE_RETRIEVAL_HIT`. Both are computational
predictions, their normalized scores are not confidence probabilities, and Foldseek
matches are not relabelled as sequence homologs.

## 12. LLM generator

Phase 6 confidence is external to the LLM. Calibrator v1 maps the B4 top-1 ranking score
to an estimated probability of exact Tier-A EC/GO-MF correctness. It is fitted only on
the development split, evaluated on validation, and never reads literature labels or
LLM self-confidence. Diagnostic evidence features remain exported for future larger
cohorts but are not fitted in the small pilot.
Required output fields:

- predicted function
- calibrated confidence class/score supplied by system
- sequence evidence
- structural evidence
- domain evidence
- literature support
- agreement/conflict explanation
- alternatives
- uncertainty
- suggested validation experiments (clearly labeled as recommendations)
- citations

The generator must distinguish inference from experimental evidence.

Implemented Phase 5 uses a local Ollama adapter with schema-constrained JSON. The normal
entry gate requires Phase 4 `PASS`; an explicit development override records
`EXPERIMENTAL_UNVALIDATED_PHASE4_OVERRIDE`. Candidate functions and selected homologs
become citable context records. The LLM does not assign final evidence roles: the
adapter derives computational, indirect-homolog, and background roles from cited record
types, preserves the raw response, and keeps confidence `NOT_CALIBRATED`.

## 13. Citation verification
For each externally sourced statement check:

1. Is there a citation?
2. Does the cited source support the claim?
3. Is the protein/species context correct?
4. Does the claim overstate predicted evidence as experimental evidence?

## 14. Confidence calibration
Confidence is an external model/function, not an LLM opinion.

Potential features:
- top sequence score
- top structure score
- sequence/structure coverage
- agreement status
- domain consistency
- number of independent supporting hits
- taxonomy distance
- literature support
- contradiction indicators

Calibration methods to test:
- logistic regression
- isotonic regression
- Platt scaling
- simple threshold baseline

## 15. File layout

```text
src/dualrag/
├── models.py
├── config.py
├── cli.py
├── sequence/
│   ├── eggnog.py
│   ├── mmseqs.py
│   └── hmmer.py
├── structure/
│   ├── alphafold.py
│   ├── pdb.py
│   └── foldseek.py
├── normalization/
│   ├── sequence.py
│   └── structure.py
├── fusion/
│   ├── candidates.py
│   ├── agreement.py
│   ├── scoring.py
│   └── calibration.py
├── literature/
│   ├── ncbi.py
│   ├── chunking.py
│   └── ranking.py
├── rag/
│   ├── context.py
│   ├── generator.py
│   └── citation_verifier.py
└── evaluation/
    ├── retrieval.py
    ├── function.py
    ├── citations.py
    └── reports.py
```

## 16. Non-goals for MVP
Do not build these before Phase 1 is validated:

- full AlphaFoldDB mirror
- custom protein language model training
- agentic multi-step autonomous experimentation
- Neo4j production graph
- fine-tuning an LLM
- automatic wet-lab validation

## 17. Offline proof-of-concept implementation

The first executable implementation uses synthetic TSV fixture adapters at the same
boundary where eggNOG/MMseqs2 and Foldseek adapters will connect. It implements FASTA
parsing, typed evidence schemas, separate versioned normalization, raw-output
preservation, deterministic provenance, and evidence merge. External execution fails
closed until verified database manifests and real adapters are available. See
`docs/POC.md` for the exact contract and scientific limitations.

The next structure adapter follows a hybrid boundary: AlphaFold DB REST for query-model
acquisition, followed by local Foldseek execution against a versioned local database.
