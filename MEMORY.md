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
Default target is Python 3.11 using the locked Pixi environment with conda-forge and
Bioconda for scientific command-line tools plus PyPI for the editable local package.

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
Phases 1 and 2.1-2.10 are complete as reproducible baselines. Phase 1 has synthetic
fixture adapters and validated real adapters for local
eggNOG-mapper, AlphaFold DB REST model acquisition/cache, and local Foldseek. The full
Foldseek target metadata contains 1,562,650 unique targets joined to SIFTS/Swiss-Prot.
A five-protein characterized integration run completed on 2026-10-16 with five sequence
hits, four compatible AlphaFold models, forty annotated Foldseek hits, and one correctly
retained sequence-only query after AlphaFold HTTP 404. A second run produced equivalent
stable query, sequence, structure, merge, acquisition, configuration, and run-provenance
artifacts. Phase 2 adds namespaced candidate grouping, explicit annotation-quality
rules, query-level six-state classification, optional versioned mapping and synonym
inputs, explicit evidence-quality reranking, alternatives, and an audit report. The
real characterized Phase 2 baseline retained four computational conflicts and one
sequence-only query; unconfigured namespace gaps are not biological conclusions.

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
- 2026-10-07: implemented the real Phase 1 adapters and a non-destructive 32 GB demo
  storage profile at `/media/splexmus/Splexmus/dualrag-demo`. The device is intentionally
  treated as adapter/demo storage, not a full research database deployment; database
  versions must be verified before external execution.
- 2026-10-08: selected `/media/splexmus/My Passport/dualrag` as the full Phase 1 data
  root with a soft 2 TB project budget. The local targets remain eggNOG plus Foldseek
  PDB; AlphaFoldDB is not mirrored. At selection time the NTFS volume was mounted
  read-only, so downloads remain blocked until it is safely remounted writable.
- 2026-10-08: moved the intended data root to the ext4 volume at
  `/media/splexmus/4TB_HDD/dualrag`. It was also observed mounted read-only with
  `errors=remount-ro`; three eggNOG archives left by mapper 2.1.13 were zero bytes.
  Pin the final v2 mapper (2.1.15) for eggNOG 5.0.2 compatibility. The tested Bioconda
  build still contained the retired URL, so use the repository's resumable installer
  against `downloads.eggnogdb.org` after the filesystem is repaired and writable.
- 2026-10-08: eggNOG-mapper 2.1.15 constrains DIAMOND to 2.0.x. The resolved Phase 1
  environment therefore records DIAMOND 2.0.15, Foldseek 9.427df8a, and MMseqs2
  16.747c6; executable and database versions remain mandatory run provenance.
- 2026-10-16: built the SIFTS/Swiss-Prot Foldseek metadata table and added a reviewed
  five-protein integration fixture. Real run `a23128c71537f105` completed all retrieval
  boundaries; P00720 correctly recorded AlphaFold `NOT_FOUND`. Current pairwise conflict
  labels are not biologically interpretable until Phase 2 function-level reconciliation.
- 2026-10-16: closed Phase 1 after a second real run produced the same run ID and
  equivalent stable outputs across seven artifacts. Added `dualrag compare-runs` with
  explicit volatile-field normalization: output paths, timestamps, cache-vs-download
  state, and parallel cross-query block order do not affect equivalence; within-query
  hit order and scientific values do.
- 2026-10-16: made Pixi the supported environment workflow. `pixi.toml` contains the
  intentional Linux Phase 1 dependencies and tasks; `pixi.lock` fixes the full
  Conda/PyPI solve. Two real characterized Pixi runs were equivalent across all seven
  artifacts. Historical Conda-to-Pixi output remains provenance-distinct because Python
  changed and historical eggNOG version capture accidentally included the current
  checkout Git hash, while retrieved biological values were unchanged. Version capture
  now runs outside the checkout. The exported Conda YAML files remain legacy snapshots.
- 2026-10-16: completed Phase 2.1-2.3 as a transparent baseline. Candidate assertions
  are grouped by controlled namespace or normalized label; generic annotations remain
  visible but unclear. Query classification uses exact shared candidates, and
  `fixed-weight-v1` preserves modality scores while adding an explicit agreement bonus.
  Real run `c58a7106523c471c` emitted 628 candidates, four computational conflicts, and
  one sequence-only result. No semantic equivalence or biological resolution is claimed
  until controlled cross-namespace mappings are added and benchmarked.
- 2026-10-16: corrected eggNOG-mapper provenance capture. Its version command consulted
  the current working Git repository, so suffixes previously interpreted as mapper build
  identifiers were actually DualRAG commits. Version checks now run outside the checkout
  and record the stable package version `emapper-2.1.15`.
- 2026-10-21: completed Phase 2.4-2.10 without introducing an LLM. Versioned mapping
  and synonym TSVs are optional; exact mappings consolidate aliases, while broader,
  narrower, and related mappings yield only partial compatibility. The fixed-weight
  score remains visible beside explicit evidence-quality features and deterministic
  reranking. `alternatives.tsv` reports near ties, and `fusion_audit.json` records
  mapping checksums, counts, and limitations. These scores are ranking features, not
  confidence or experimental validation. Real run `27665c3b0f2402db` emitted 628
  candidates and 25 alternatives; two identical-config runs were equivalent across
  all 12 compared artifacts. With no mapping files configured, four conflicts remain
  explicitly computational and the audit records zero mapped contributions.
- 2026-10-22: built a portable characterized mapping bundle from Pfam 38.2,
  InterPro 110.0, and reviewed UniProtKB/Swiss-Prot 2026_03 records. Five official
  Pfam integrations changed four computational conflicts to `PARTIAL_CONSENSUS` while
  P00720 remained `SEQUENCE_ONLY`; no query became full consensus. The synonym subset
  is source-curated but smoke-set-derived, did not affect this run, and must not be used
  as independent Phase 3 benchmark truth. Identical mapped runs were equivalent across
  12 artifacts.
- 2026-10-22: froze Phase 3.1 contract `phase3-benchmark-v1`. The primary endpoint is
  macro exact EC/GO-MF Function Recall@10 with paired 10,000-replicate bootstrap for
  B4-minus-B2. InterPro/Pfam are secondary consistency endpoints, never complete-function
  correctness. Tier A requires experimental function evidence. Splits keep 30%-identity,
  80%-coverage MMseqs2 clusters intact; primary retrieval excludes exact queries and
  targets at least 90% identical with at least 80% bidirectional coverage. Smoke-derived
  synonyms are prohibited from the primary benchmark, and test labels remain hidden
  until configuration freeze.
- 2026-10-25: completed the Phase 3.2-3.4 development pilot `phase3-pilot-v1` from
  checksummed UniProtKB/Swiss-Prot 2026_03. It contains 60 canonical Tier-A queries,
  60 intact MMseqs2 clusters split 42/9/9, 138 Swiss-Prot reference exclusions, and
  frozen closest-allowed-reference difficulty strata. This pilot develops and tests the
  benchmark machinery; it is not statistically powered. Phase 3.6 must resolve actual
  eggNOG targets and SIFTS/PDB chains and enrich GO publication provenance before a
  final benchmark claim.
- 2026-10-25: completed the Phase 3.5-3.9 development benchmark. The real run used
  leakage-filtered MMseqs2/Swiss-Prot for B2 and AlphaFold plus local Foldseek/SIFTS for
  B3, with 46 models available and 14 unavailable. On the untouched nine-query test
  split, FR@10 was B2 0.722, B3 0.250, and B4 0.778. The paired B4-minus-B2 estimate
  was +0.0556 with 95% CI 0.0000-0.1667, so the frozen claim rule yields
  `NO_MEASURABLE_OVERALL_BENEFIT`. This is a small development result, not a powered
  final scientific benchmark.
- 2026-10-26: screened the supplied 60-protein panel as the separate external case
  `phase3-external-panel-v1`, without changing the frozen pilot splits. Forty-seven
  proteins passed frozen Swiss-Prot 2026_03 Tier-A and pilot-cluster rules; twelve
  lacked admissible EC/GO-MF gold and F9VMT6 overlapped an exposed pilot cluster. Only
  P25583 and P28321 met the <=30% closest-allowed-identity rule. The real rerun obtained
  43 AlphaFold models and 412 allowed Foldseek hits. FR@10 was B2 0.743, B3 0.444 and
  B4 0.745; paired B4-minus-B2 was +0.0015 with 95% CI -0.0590 to 0.0532, again yielding
  `NO_MEASURABLE_OVERALL_BENEFIT`. Architecture labels remain provisional because no
  positional InterProScan source was available.
- 2026-10-26: selected the conservative `quality-gated-v2` fusion profile from
  development/validation behavior and regression-checked it against `fixed-weight-v1`.
  The nine-query v1 test split was already exposed, so it is not fresh v2 confirmation. V2
  deduplicates biological sources, adds a capped independent-support bonus, gates
  structure transfer by coverage/TM-score, and can rescore preserved TSV evidence
  offline. Development B4 FR@10 changed 0.557 to 0.575; validation remained 0.796 and
  test remained 0.778. The 50-hit profile is experimental because it reduces precision.
  This engineering/ranking improvement does not change the Phase 3 conclusion
  `NO_MEASURABLE_OVERALL_BENEFIT` or establish calibrated biological confidence.
- 2026-10-26: froze Phase 4.0 contract `phase4-literature-v1` and implemented Phase 4.1
  typed schemas. Literature is passage-level, downstream evidence; direct support or
  contradiction requires a primary experimental passage and explicit entity matching,
  while reviews are background only. PubMed does not imply full-text access, and access
  failure is not negative biological evidence. Queries forbid undeclared fields to
  prevent benchmark-label leakage. Packets are capped at 10 articles, 20 chunks, and 3
  chunks per article. Adapters, retrieval, and labelled evaluation remain pending.
- 2026-10-26: completed Phase 4.2 deterministic literature-query construction.
  `build-literature-queries` reads a fixed allowlist of biological-run artifacts,
  rejects unexpected context columns, selects ranked informative candidates and
  provenance-bearing sequence homologs, and emits source-neutral query variants plus a
  checksummed manifest. Structural matches are not called homologs. Phase 4.3 PubMed is
  specified as an ESearch-to-batched-EFetch metadata/abstract adapter with raw response
  preservation, rate limiting, retries, caching, deduplication, and secret redaction;
  network retrieval remains pending.
- 2026-10-26: implemented Phase 4.3-4.7 engineering flow. PubMed ESearch/batched
  EFetch and PMC OA-gated acquisition preserve raw responses, checksums, licenses,
  access failures, caching, and redacted configuration. Section-aware chunking feeds
  independent BM25 and character-trigram vector features plus a deterministic
  biological reranker; retrieved passages remain `UNASSESSED`. Compact packets enforce
  the 10-article/20-chunk/3-per-article limits. Manual evaluation reports retrieval,
  citation, entity, organism, primary-experiment, and contradiction metrics, but live
  scientific completion remains pending expert labels. The HDD runner refuses internal
  fallback; `/media/splexmus/4TB_HDD1` was read-only during validation.
- 2026-10-26: the five-query v3 audit exposed that labels covering only final hits make
  citation recall tautological and do not measure missed candidates. Added pooled
  evaluation v2: every PubMed candidate passage retains lexical, vector, hybrid, and
  reranker ranks; the enriched review TSV must be completely human-labelled; and
  thresholds require at least 20 queries and five contradiction passages. Added a
  leakage-safe Phase 3 development-query builder and HDD exit-benchmark runner. The
  user's terminal showed `/dev/sda1` mounted read-write; sandbox read-only visibility is
  not authoritative for their terminal.
- 2026-10-27: implemented an experimental Phase 5 local-Ollama generation path while
  Phase 4 remains unvalidated. The default gate still requires Phase 4 `PASS`; an
  explicit override marks every output `EXPERIMENTAL_UNVALIDATED_PHASE4_OVERRIDE`,
  treats UNASSESSED literature only as background, and fixes confidence to
  `NOT_CALIBRATED`. The LLM selects schema-bounded evidence IDs, while the system assigns
  evidence roles and inserts the candidate-grounded computational function claim. A
  20-query `gemma3:4b` development run completed with 20 `PASS_WITH_WARNINGS` verifier
  results, all warnings caused by the deliberate Phase 4 bypass. This is engineering
  validation only; semantic truth and Phase 5 usefulness still require expert review.
