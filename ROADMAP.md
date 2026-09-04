# ROADMAP.md

## Phase 0 — Repository and environment
Status: **PoC complete with fixture backend; external-tool integration pending.**

Deliverables:
- Conda `environment.yml`
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

Status: **data contracts and offline end-to-end smoke path complete; real eggNOG,
MMseqs2, AlphaFold/PDB, and Foldseek adapters pending external data.**

### 1A. Sequence branch
- FASTA parsing
- eggNOG-mapper wrapper
- MMseqs2 support
- raw result preservation
- normalized sequence schema

### 1B. Structure branch
- UniProt/AlphaFold structure retrieval and cache
- optional PDB lookup
- Foldseek wrapper
- raw result preservation
- normalized structure schema

### 1C. Merge
- join by query ID
- keep multiple hits
- emit `sequence_results.tsv`, `structure_results.tsv`, `merged_results.tsv`

Exit criteria:
- end-to-end smoke test on a small characterized protein set
- tool/database versions recorded
- repeat run produces equivalent normalized output

## Phase 2 — Function-level fusion
- candidate-function grouping
- informative vs unclear annotation rules
- cross-modal status classifier
- first fixed-weight baseline
- conflict report

Exit criteria:
- reproduce interpretable categories such as agreement, unclear/partial agreement, disagreement, and modality-only retrieval

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
