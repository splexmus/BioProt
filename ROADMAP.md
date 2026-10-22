# ROADMAP.md

## Phase 0 — Repository and environment
Status: **complete; external executables are detected and storage is configurable.**

Deliverables:
- locked Pixi environment (`pixi.toml` + `pixi.lock`)
- `config/config.yaml`
- CLI skeleton
- logging/version capture
- test fixtures
- storage root configuration

Exit criteria:
- environment resolves
- CLI starts
- tool availability/version checks work

## Phase 1 — Biological dual retrieval (highest priority)

Status: **complete. Real adapters, finalized database provenance, Foldseek target
metadata, a five-protein characterized integration run, and repeat-run equivalence
were validated on 2026-10-16.**

### 1A. Sequence branch
- FASTA parsing
- eggNOG-mapper wrapper using a locally stored eggNOG database
- MMseqs2 support
- raw result preservation
- normalized sequence schema

### 1B. Structure branch
- UniProt accession resolution with explicit provenance
- AlphaFold DB REST metadata lookup and on-demand model cache
- AlphaFold acquisition manifest, checksum, timeout, retry, and 404 handling
- optional PDB lookup
- local Foldseek wrapper using a locally stored target database
- optional target-metadata TSV for functional labels and source provenance
- raw result preservation
- normalized structure schema

### 1C. Merge
- join by query ID
- keep multiple hits
- emit `sequence_results.tsv`, `structure_results.tsv`, `merged_results.tsv`

Exit criteria:
- end-to-end smoke test on a small characterized protein set **(complete: 2026-10-16)**
- tool/database versions recorded
- repeat run produces equivalent normalized output **(complete: 2026-10-16)**

## Phase 2 — Function-level fusion

Status: **steps 2.1-2.10 implemented on 2026-10-21; controlled mappings are optional
inputs and unconfigured namespace gaps remain explicit.**

### 2.1 Candidate-function grouping
- namespaced EC, GO, InterPro, Pfam, SUPFAM, orthologous-group, and label candidates **(complete)**
- per-modality scores and source-hit provenance retained **(complete)**

### 2.2 Annotation quality and cross-modal state
- informative vs unclear annotation rules **(complete)**
- query-level six-state classifier with explicit reasons **(complete)**

### 2.3 Fixed baseline and disagreement output
- configurable fixed-weight ranking baseline **(complete)**
- compact conflict report with full candidate table retained **(complete)**

### 2.4 Versioned cross-namespace mappings
- optional TSV with `EXACT`, `BROADER`, `NARROWER`, or `RELATED` relations **(complete)**
- file checksum and mapping source/version retained in the audit **(complete)**

### 2.5 Curated synonyms
- optional, versioned label-to-controlled-ID synonym TSV **(complete)**
- no inferred or LLM-generated synonym equivalence **(complete)**

### 2.6 Candidate consolidation
- exact mappings consolidate aliases while preserving original IDs and provenance **(complete)**
- non-exact relations produce partial compatibility without merging IDs **(complete)**

### 2.7 Evidence-quality features
- identifier specificity, modality support, and independent-hit support exposed separately **(complete)**
- quality feature is explicitly uncalibrated **(complete)**

### 2.8 Deterministic reranking
- configurable base/quality combination with stable tie-breaking **(complete)**
- original fixed-weight score remains available beside rerank score **(complete)**

### 2.9 Alternatives and ambiguity
- top alternatives, score deltas, and configurable near-tie flag **(complete)**
- ambiguity is not reported as confidence **(complete)**

### 2.10 Validation and audit
- deterministic `fusion_audit.json` with mapping checksums, counts, and limitations **(complete)**
- Phase 2 artifacts included in repeat-run comparison **(complete)**

Exit criteria:
- reproduce interpretable categories such as agreement, unclear/partial agreement,
  disagreement, and modality-only retrieval **(complete in unit/fixture tests)**
- real characterized run and 12-artifact repeatability check **(complete: 2026-10-21)**
- mapping, synonym, relation, reranking, alternatives, and audit unit tests **(complete)**
- official Pfam 38.2/InterPro 110.0 mapping bundle and repeat run **(complete: 2026-10-22)**

## Phase 3 — Benchmarking
- curate characterized benchmark proteins
- cluster-aware train/validation/test split
- create sequence-identity strata
- implement retrieval metrics
- implement function-level metrics
- run sequence-only vs structure-only vs dual retrieval

Exit criteria:
- quantified evidence that dual retrieval adds value, or a clear negative result explaining when it does not

## Phase 4 — Literature RAG
- PubMed/PMC retrieval
- metadata preservation
- section-aware chunking
- vector index
- reranker
- evidence packet builder

Exit criteria:
- literature retrieval precision/recall evaluation on a labeled subset

## Phase 5 — LLM synthesis
- structured prompt/context
- grounded report schema
- citation verifier
- hallucination checks
- human/expert evaluation sample

Exit criteria:
- generated reports are more useful without reducing factual grounding

## Phase 6 — Confidence calibration
- collect prediction/evidence features
- train/fit calibration model on validation data
- reliability diagrams / Brier score / ECE
- define confidence labels

Exit criteria:
- confidence correlates with empirical correctness on held-out characterized proteins

## Phase 7 — Optional GraphRAG
- build protein/function/domain/publication graph
- prototype with NetworkX
- evaluate path retrieval
- introduce Neo4j only if required

Exit criteria:
- ablation demonstrates measurable benefit over non-graph dual RAG

## Phase 8 — Uncharacterized protein study
- select biologically relevant unknown proteins
- produce hypotheses with evidence trails
- expert review
- prioritize candidates for experimental follow-up

## Definition of done for research release
- reproducible environment
- versioned database snapshots/metadata
- benchmark dataset manifest
- baseline and ablation results
- documented limitations
- code tests
- no hidden dependence on a private local path/database
