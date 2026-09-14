# MEMORY.md — Durable Project Context

> This is a human-maintained project memory file. It is not a substitute for source code, tests, or versioned experiment metadata. Update it only for durable decisions, major discoveries, or project-status changes.

## Project identity
Working title: **Dual-Retrieval RAG for Protein Function Prediction**.

Goal: build a research framework that combines independent sequence-based and structure-based protein retrieval, explicitly measures their agreement/conflict, retrieves supporting literature when useful, and generates evidence-grounded functional hypotheses with calibrated confidence.

## Research motivation
The project is inspired by three supplied papers:

1. **ProtPen** — combines eggNOG-mapper sequence annotation with Foldseek structural similarity searches and shows the complementarity of the two modalities for protein function prediction.
2. **MicroTraitLLM** — demonstrates a microbe-focused RAG workflow using NCBI/PMC article retrieval, article summarization, final synthesis, and citation-oriented output.
3. **GLEAR** — demonstrates dual-driven retrieval and graph/path-based reasoning before LLM generation; the transferable idea is to retrieve coherent evidence relationships rather than only isolated chunks.

See `docs/REFERENCES.md` for exact papers and project-specific takeaways.

## Durable design decisions

### D1 — Independent retrieval channels
Sequence and structure retrieval must remain independently inspectable. Do not immediately average them into a single score.

### D2 — Explicit cross-modal status
Every query should eventually receive one cross-modal state:

- CONSENSUS
- PARTIAL_CONSENSUS
- SEQUENCE_ONLY
- STRUCTURE_ONLY
- CONFLICT
- INSUFFICIENT_EVIDENCE

### D3 — Biological retrieval before LLM
The LLM is not the first milestone. The first milestone is reproducible dual retrieval with normalized evidence tables.

### D4 — Evidence-aware output
A final function prediction must expose the evidence that produced it: sequence hits, structure hits, domains/controlled identifiers, literature support, alternatives, and uncertainty.

### D5 — Confidence is computed externally
Do not use free-form LLM confidence as the final scientific confidence score. Confidence should be calibrated from retrieval/evidence features on validation data.

### D6 — Literature is a support layer
PubMed/PMC retrieval is used to support, verify, or contextualize candidate functions after biological retrieval. It should not be the sole source of protein function inference in the main pipeline.

### D7 — Optional graph layer comes later
GraphRAG is an advanced phase, not MVP. First prove that sequence + structure retrieval outperforms single-modality baselines.

### D8 — Storage strategy
The eggNOG and Foldseek target databases live locally outside Git and Conda, preferably
on fast external SSD or HPC/shared storage. AlphaFoldDB is not mirrored: query models
are retrieved through the AlphaFold DB REST API and cached on demand with provenance.

### D9 — Python environment
Default target is Python 3.11 using Conda/Bioconda for scientific command-line tools and Python libraries for orchestration, normalization, ranking, RAG, and evaluation.

## Current proposed tool stack

Sequence:
- eggNOG-mapper
- MMseqs2
- HMMER
- BLAST+/DIAMOND as optional comparators

Structure:
- AlphaFold DB REST API for predicted query-model acquisition
- local Foldseek executable and locally stored target database
- optional, separately labelled PDB retrieval
- Gemmi/Biopython for structure parsing

Metadata / annotation:
- UniProt
- InterPro/Pfam
- GO
- KEGG/EC where licensing/access and project use permit

RAG:
- FAISS initially
- sentence-transformers / transformers
- PubMed/PMC via NCBI APIs
- hosted or local LLM only after retrieval is stable

Optional graph:
- NetworkX for prototype
- Neo4j if persistent graph storage/path querying becomes necessary

## Storage estimate
Plan for approximately **250–600 GB** for a practical local research setup with databases, caches, indexes, results, and temporary files. Use a **2 TB SSD** as a comfortable starting point. A 4 TB SSD is preferable for multi-organism experiments and repeated benchmark snapshots.

Storage is dominated by databases and temporary/index files, not Python packages.

## Planned data flow

```text
Query protein
  ├─ sequence branch -> sequence evidence
  └─ structure branch -> structure evidence
             ↓
      evidence normalization
             ↓
     cross-modal comparison
             ↓
      candidate functions
             ↓
     optional literature RAG
             ↓
       structured LLM context
             ↓
   hypothesis + confidence + citations
```

## Benchmark philosophy
Evaluate retrieval separately from generation.

Important comparisons:
- LLM alone
- literature RAG only
- sequence-only retrieval/RAG
- structure-only retrieval/RAG
- dual sequence+structure retrieval
- dual RAG + literature
- optional graph-enhanced system

Important ablations:
- remove sequence retrieval
- remove structure retrieval
- remove agreement score
- remove domain evidence
- remove reranker
- remove literature retrieval
- remove graph/path layer
- remove confidence calibration

## Dataset philosophy
Use at least:

1. Gold-standard characterized proteins with experimentally supported functions.
2. Difficult proteins stratified by sequence identity to test whether structure retrieval rescues remote cases.
3. Uncharacterized/hypothetical proteins for coverage, specificity, agreement, and expert-review experiments.

Avoid naïve random splits that leak highly similar homologs between development and test. Prefer cluster-aware splitting.

## Open research questions
- What normalization makes sequence and structure scores comparable without destroying modality-specific meaning?
- How should function-level agreement be determined: exact identifiers, ontology relations, semantic similarity, or a hybrid?
- What reranking method best combines retrieval quality, domain consistency, taxonomy, and literature evidence?
- How should confidence be calibrated and evaluated?
- What is the best benchmark for conflict resolution between sequence and structure evidence?
- At what sequence-identity regime does structure retrieval provide the largest rescue benefit?
- Does a graph/path evidence representation improve final groundedness enough to justify its complexity?

## Current implementation status
A Phase 0/1 proof of concept is implemented with synthetic fixture adapters. It parses
FASTA, preserves raw fixture outputs, normalizes sequence and structure hits separately,
emits the three Phase 1 TSV tables, classifies transparent baseline agreement states,
and records run provenance. This validates orchestration and data contracts only; real
bioinformatics retrieval remains gated until external databases and adapters are
configured and integration-tested.

## Update policy
When a durable decision changes, append a short entry below rather than silently rewriting history.

### Decision log
- Initial project memory created: dual retrieval first; LLM second; external SSD database layout; graph layer deferred.
- 2026-09-04: added an offline synthetic-fixture PoC so schemas, provenance,
  reproducibility, and merge behavior can be tested without downloading databases.
  Fixture annotations must never be interpreted as protein-function predictions.
- 2026-09-14: fixed the Phase 1 deployment boundary: eggNOG and Foldseek databases are
  local; AlphaFold DB is accessed through REST only for required query models, which
  are cached with checksums and acquisition metadata. AlphaFold REST does not replace
  local Foldseek similarity search.
