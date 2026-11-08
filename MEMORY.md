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
- 2026-11-08: added a full release-pinned InterPro/Pfam mapping builder. The verified
  temporary bundle used InterPro 111.0 and Pfam 39.0 and emitted 94,286 exact
  accession/name mappings for 47,143 integrated Pfam signatures. A development-only
  rerun of the requested 0.4/0.3/0.3 fusion and 0.7/0.3 reranking weights slightly
  reduced all principal dual ranking metrics versus the previous profile, so the new
  weights remain an ablation and do not replace frozen settings. The HDD was read-only;
  permanent bundle installation remains an operator step after a safe read-write mount.
- 2026-11-08: the Phase 3 runner now accepts `--config` for Foldseek paths, mapping and
  synonym inputs, quality gating, fusion/reranking weights, and version labels. The
  current config-driven development rescore used 0.55/0.20/0.25 fusion and 0.75/0.25
  reranking. It slightly improved Recall@1, Recall@5, MRR, and nDCG but reduced
  Recall@10 from 0.8090 to 0.8077; it remains an ablation and no sealed labels were read.
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
- 2026-10-27: assessed the human-labelled 20-query Phase 4 v4 run with a separate
  `phase4-to-phase5-development-v1` transition policy. It records
  `PASS_FOR_PHASE5_DEVELOPMENT` because readiness/provenance checks pass, while the
  frozen scientific exit remains `FAIL`; recall@10, nDCG@10, citation precision/recall,
  entity correctness, and organism correctness remain below threshold. Phase 5 must
  retain the scientific-gate override, treat this literature conservatively, and keep
  confidence `NOT_CALIBRATED` until those gates and later calibration are completed.
- 2026-10-27: completed Phase 5.1 bounded biological-evidence enrichment. The v4 HDD
  packet set now has a separate checksummed `evidence_packets.biological-v1.jsonl` with
  up to five leakage-filtered records per modality: 80 MMseqs2/Swiss-Prot sequence hits
  and 70 Foldseek/PDB-SIFTS structure hits across 20 queries. Six queries correctly have
  no allowed structure hit. Context/prompt v2 keeps modalities separate, preserves raw
  metrics and provenance, reads no benchmark gold labels, and retains `NOT_CALIBRATED`.
- 2026-10-27: Phase 5 Markdown renderer v2 now shows sequence retrieval, structure
  retrieval, and cross-modal interpretation as separate topics with bounded raw metrics,
  annotations, and provenance. Prompt v3 requests modality-specific claims, and verifier
  v2 warns when available sequence or structure evidence is not discussed. Generation
  adapter v4 deterministically adds conservative top-hit modality claims when Gemma omits
  them while retaining the unchanged raw model response.
- 2026-10-27: recorded `PASS_FOR_PHASE6_DEVELOPMENT` after project-owner acceptance of
  Phase 5 output; blinded expert comparison remains pending. Implemented Phase 6
  `phase6-platt-v1`, which estimates exact top-1 Tier-A EC/GO-MF correctness from the B4
  ranking score. It fitted 51 examples from 36 development proteins and evaluated 15
  examples from nine validation proteins; the exposed test split was excluded. Validation
  Brier improved 0.3069 to 0.2729, ECE 0.2387 to 0.1824, and log-loss 0.9071 to 0.7406.
  This remains `DEVELOPMENT_PILOT_NOT_FOR_PRODUCTION` due to the tiny validation cohort.
- 2026-10-27: generated the versioned 20-row Phase 5 human-review table from
  `phase5-ollama-biological-sections-full-v1`. It pre-fills report checksums, evidence and
  claim counts, cross-modal status, and verifier findings while leaving controlled human
  judgments blank; six structure-unavailable cases are prefilled `NA`. Added the review
  guide and a ten-step post-Phase-6 scientific-validation plan to `ROADMAP.md`.
- 2026-10-28: the project owner completed all 20 Phase 5 development-review rows for the
  preserved `gemma3:4b` run: 16 accept, 2 revise, 2 reject; 14 useful, 3 partly useful,
  3 not useful; all rows recorded no unsupported claims. This does not transfer to a new
  model variant or replace blinded validation. New Phase 5 runs now default to the locally
  installed `gemma4:more`; the old run remains immutable and the Gemma 4 variant requires
  its own smoke/full run and review before freeze. Step 3 now has a detailed scientific
  panel plan: 200 proteins is a floor, with adaptive expansion (expected near 800) until
  cluster-aware validation and untouched-test splits each contain at least 100
  query-namespace examples.
- 2026-10-28: changed new Phase 5 runs to the installed custom `gemma4:more` model and
  generation pipeline v5. The model's default hidden reasoning and 16,384-token budget
  caused 300/900-second timeouts; `think=false` produced one valid smoke, but repeated
  4,096- and 8,192-token runs truncated JSON after consuming their budgets. The model is
  selected but not frozen and must pass a repeated-query reliability pilot before a full
  run. V5 records thinking/output limits in provenance and preserves invalid raw Ollama
  responses. The reviewed `gemma3:4b` run remains the accepted development reference.
- 2026-10-28: merged the three user-supplied UniProt nomination exports into
  `step3-merged-reviewed-v1`. Supplied review status, explicitly including v2, is accepted
  only from the `Reviewed` column; frozen Swiss-Prot 2026_03 supplies all scientific
  eligibility and gold provenance. After Tier-A screening and exposed-cluster exclusion,
  the HDD dataset contains 788 proteins in 660 intact clusters: 552 development, 118
  validation, and 118 test, with 171 validation and 172 test query-namespace examples.
  Checksums and independent invariants pass with no exposed accession/checksum overlap.
  Status remains development-only until test labels are moved to controlled storage;
  remote-homology power is limited because only 10 queries fall in the 20-30% stratum.
- 2026-10-28: created a non-overwriting pipeline-facing view of the merged Step 3 dataset
  with zero test-gold rows and a separate mode-0700 test-label vault. The vault contains
  792 rows for 118 proteins; SHA-256 is
  `b4e18359502e860bb52e9b30914e21e80cb31d5ff0bf5ebfc2b890bb22568904`.
  This is procedural filesystem separation, not historical third-party blinding, because
  the complete gold file existed before sealing and accessions/names remain visible.
  Never use vault contents to tune retrieval, mappings, prompts, or thresholds.
- 2026-10-28: completed scientific-validation Step 5 by freezing
  `phase6-scientific-calibration-gate-v2` before new validation predictions. The gate
  requires at least 100 evaluable examples/75 proteins, at least 80% prediction coverage,
  Brier <=0.22, log-loss <=0.65, ECE <=0.10, and at least 0.02 improvement over raw for
  each metric. LOW/MODERATE/HIGH accuracy must be monotonic; HIGH requires at least 30
  examples, 85% point accuracy, and a 70% Wilson lower bound. The thresholds are a
  project-specific conservative predeclaration, not a universal standard. Test remains
  one-time-only after validation model selection and parameter freeze.
- 2026-11-07: ran the Step 6 development/validation retrieval and frozen calibration
  gate without test-gold access. The 670-query run acquired 666 AlphaFold models (313
  cached, 353 downloaded, four unavailable), retained 17,679 sequence and 31,718
  structure hits, and excluded 7,576 prohibited or unresolved structure hits. On 118
  validation proteins, B4 dual and B2 sequence-only EC/GO-MF metrics were identical:
  Recall@10 0.6864 and paired difference 0.0 (95% bootstrap CI 0.0 to 0.0). Structure
  improved InterPro Recall@10 from 0.8717 to 0.9236 but produced no EC/GO-MF structure
  rescue. The calibration sample gate passed (155 examples, 111 proteins, 90.6%
  coverage), but Platt, isotonic, and multifeature logistic each failed at least one
  frozen requirement. Status is `FAIL_SCIENTIFIC_CALIBRATION_GATE`; no calibrator was
  selected, test gold remains unopened, and Step 7 is prohibited.
- 2026-11-07: completed Phase 6 recovery priorities 1-3 without using validation/test
  outcomes for the new comparison. Fixed the `IPR...` versus `InterPro:IPR...`
  projection-key mismatch. Built `pdb_metadata.v2.tsv` for 1,562,650 targets with
  GO-MF-only SIFTS annotations (1,028,244 targets), EC (549,754), InterPro (1,467,150),
  Pfam (853,806), and row-level source provenance. Mapping bundle v2 filters all
  projections to non-root GO Molecular Function. Domain-derived GO candidates remain
  separate from direct GO, carry `DOMAIN_PROJECTION:INTERPRO2GO`, a
  `DOMAIN_DERIVED_FUNCTION` flag, and a 0.75 reliability cap. Development-only
  evaluation on 552 proteins improved dual versus sequence Recall@10 from 0.7549 to
  0.8090 (difference 0.0541; 95% bootstrap CI 0.0379-0.0712) and produced 25 structure
  rescues. Top-1 recall was slightly lower and precision@10 fell, so ranking and
  calibration remain development tasks. The old validation failure is unchanged and
  sealed test labels remain prohibited.
- 2026-11-07: completed recovery priorities 4-5 prospectively. A development-only,
  five-fold cluster-aware search selected the direct-evidence ranking profile, and
  development CV selected a multifeature L2 logistic calibrator fitted on 821 examples
  from 552 proteins. A new cluster-independent cohort of 150 reviewed proteins was run
  without gold access; 125 AlphaFold models were usable, 22 were unavailable, and three
  sequence mismatches were explicitly retained as sequence-only cases. Predictions,
  model parameters, mappings, Foldseek metadata provenance, contracts, Pixi lock, and
  the Python code tree were hashed before validation gold was revealed. Frozen dual
  Recall@10 improved from 0.6047 sequence-only to 0.6402 (paired difference 0.0356; 95%
  bootstrap CI 0.0117-0.0639), but top-1 recall, MRR, and Precision@10 declined. The
  calibration sample gate passed with 175 examples from 138 proteins and 92.6% coverage,
  while Brier 0.2581, log-loss 0.7089, ECE 0.1661, and LOW/HIGH group sizes failed the
  frozen contract. Final status remains `FAIL_SCIENTIFIC_CALIBRATION_GATE`; validation
  gold was accessed once, original test gold was not accessed, and test evaluation is
  still prohibited.
- 2026-11-07: added sequence-anchored ranking v3 and an explicit
  ranking -> evidence sufficiency -> top-1-or-abstain -> calibration pipeline. The
  development-selected ranker keeps the sequence top-1, admits at most one
  structure-only candidate per namespace, and improved development Recall@1, Recall@10,
  and MRR over sequence-only. On the previously revealed 150-protein cohort, ranking
  alone improved Recall@10 from 0.6047 to 0.6302 (difference 0.0256; 95% CI
  0.0044-0.0522) and improved Recall@1/MRR, while Precision@10 remained lower. The first
  80%-coverage sufficiency policy transferred at only 59.8% and was rejected. A revised
  development policy targeting 95% coverage accepted 86.2% of the old cohort; only one
  of 26 abstained calls would have been correct. Accepted-call Brier 0.2470, log-loss
  0.6865, and ECE 0.1060 improved over the previous frozen model but still fail the
  scientific gate. This revision was influenced by already-revealed validation results,
  is exploratory only, and requires a new frozen validation cohort. Test gold remains
  unopened and prohibited.
- 2026-11-07: recorded `PASS_FOR_NEW_VALIDATION_BUILD` for the improved Phase 6
  ranking/sufficiency branch. The pass is limited to development continuation: ranking
  Recall@10 has a positive bootstrap interval, Recall@1 and MRR exceed sequence-only,
  accepted coverage is 86.2%, only 3.8% of abstentions would have been correct, and all
  three calibration metrics improved modestly. Scientific calibration remains
  `FAIL_SCIENTIFIC_CALIBRATION_GATE`; confidence is not production-ready and sealed
  test access remains prohibited. The next allowed action is a fully frozen run on a
  new cluster-independent validation cohort.
- 2026-11-07: completed that new frozen validation on 300 reviewed proteins and 403
  eligible query-namespace cases, excluding all 938 proteins used previously. The
  sample gate passed with 324 accepted cases from 243 proteins and 80.4% coverage;
  only 6.3% of abstentions would have been correct. The retrospective ranking gain did
  not replicate: dual-minus-sequence Recall@10 was 0.0046 with 95% CI -0.0140 to
  0.0233. Calibration improved raw Brier 0.3138 to 0.2571, log-loss 0.9925 to 0.7076,
  and ECE 0.2333 to 0.1377, but missed all absolute limits and produced only seven HIGH
  and zero LOW cases. Status remains `FAIL_SCIENTIFIC_CALIBRATION_GATE`; test gold was
  not accessed and is still prohibited.
- 2026-11-08: prospectively evaluated the InterPro 111.0/Pfam 39.0 weighted pipeline
  on a third 300-protein cluster-independent cohort after excluding all 1,238 proteins
  used by the original benchmark and the first two fresh-validation cohorts. Predictions,
  abstention decisions, configuration, mapping resources, calibration bundle, contract,
  retrieval manifest, and code were checksum-frozen before the labels were revealed.
  Dual Recall@10 was 0.6004 versus 0.5578 for sequence-only (difference 0.0426; 95%
  bootstrap CI 0.0257-0.0619), so this cohort supports a ranking benefit. The sample gate
  passed with 314 accepted cases from 239 proteins and 80.5% coverage, but calibrated
  Brier 0.2392 and log-loss 0.6698 exceeded their frozen maxima; ECE 0.0807 passed.
  Only one HIGH and zero LOW examples were produced, so confidence-group requirements
  also failed. Status remains `FAIL_SCIENTIFIC_CALIBRATION_GATE`; the validation result
  must not be used for another confirmatory retune, and sealed test gold remains
  prohibited.
- 2026-11-07: added a dependency-free persistent Phase 4 SQLite index. It stores
  validated literature chunks and deterministic character-trigram vectors, refuses
  overwrite without `--replace`, and reuses the existing BM25/vector/biological
  reranker plus evidence-packet contracts for offline search. It is an exact-search
  experimental ablation, not a semantic embedding, Phase 4 scientific pass, or
  replacement for periodic PubMed/PMC corpus acquisition.
  The 1,569-chunk HDD index was built and controlled retrieval exactly reproduced the
  failed v4 metrics. Unrestricted search emitted 31,380 candidates and 352 hits; it is
  unlabelled and cannot yet support a retrieval-quality claim.
- 2026-11-07: added `pixi run test-all-processes` as the safe routine engineering test.
  It runs unit/lint/CLI checks, external-tool diagnostics, two reproducible Phase 1-2
  fixture runs, Phase 4 query construction, and Phase 4-6 runner syntax without network,
  HDD writes, Ollama, real databases, or sealed labels. Real scientific stages remain
  separately documented manual checks and cannot inherit the engineering PASS.
- 2026-11-07: added a phase-by-phase operator manual and a user-interface plan. The
  current entry point remains FASTA; bare UniProt accessions must first be resolved to a
  verified canonical FASTA. The planned smallest interface is one resumable
  `dualrag analyze` command with exactly one FASTA/accession input, deterministic summary,
  optional local/online literature, and optional Ollama. A normal single-protein Phase 5
  evidence adapter is required before the planned interface is complete.
- 2026-11-07: implemented the first `dualrag analyze` interface. It requires exactly one
  `--fasta` or `--uniprot`, validates/caches the canonical input and checksums, refuses
  overwrite, runs existing Phase 1-2 modules, and writes `summary.md`, `status.json`, and
  failure logs. Literature/Ollama orchestration, resume, ordinary-run Phase 5 enrichment,
  and a graphical UI remain pending.
- 2026-11-08: extended `dualrag analyze` with `--literature local|online` and
  `--report ollama`. Local mode uses the persistent vector index; online mode uses the
  existing PubMed/PMC adapters and requires an NCBI email. Ordinary Phase 1-2 TSVs are
  enriched into bounded, modality-separated Phase 5 packets before Ollama generation.
  Because Phase 4 remains failed/not evaluated for new runs, report generation requires
  the explicit `--allow-unvalidated-phase4` flag and retains `NOT_CALIBRATED` status.
- 2026-11-08: live-tested the integrated interface on one synthetic query with the HDD
  SQLite literature index and local `gemma4:more`. The first request generated 29
  repetitive claims and truncated at 4,096 tokens. Added contextual JSON-schema bounds
  of eight claims and smaller auxiliary lists; the repeated live run completed one
  report with `PASS_WITH_WARNINGS` and preserved the experimental Phase 4 override.
- 2026-11-08: revised the top-level `dualrag analyze` summary to present sequence and
  structure support as separate per-query topics and label candidate scores as
  provisional ranking features rather than probabilities. The summary and `status.json`
  now expose `FAIL_SCIENTIFIC_CALIBRATION_GATE`, `NOT_CALIBRATED`, and
  `HYPOTHESIS_GENERATION_ONLY`. The Phase 6 cohort calibrator is intentionally not
  applied to ordinary eggNOG/Foldseek single-protein runs because their feature contract
  differs from the benchmark pipeline.
