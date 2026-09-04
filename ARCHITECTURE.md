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

Internal query model:

```python
class ProteinQuery:
    protein_id: str | None
    sequence: str
    organism: str | None
    tax_id: int | None
    task: str = "protein_function_prediction"
```

## 4. Sequence retrieval

### Responsibilities
- run eggNOG-mapper / MMseqs2-based annotation
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
1. locate an experimental PDB structure where appropriate, otherwise retrieve AlphaFoldDB model if available
2. cache structure files
3. execute Foldseek against configured structural database
4. map structural hits to protein identifiers/functional metadata

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
interpro_ids
supfam_ids
structure_source
experimental_structure
raw_output_path
```

If Foldseek output does not include a field directly, do not infer it unless a documented post-processing step computes it.

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

Weights are hyperparameters to be calibrated on validation data. The project should compare:

- fixed weighted sum
- learning-to-rank / logistic calibration
- pairwise reranker
- ontology-aware consensus score

## 10. Literature retrieval
Literature retrieval is downstream of candidate function creation.

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

## 12. LLM generator
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
