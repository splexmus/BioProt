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

Status: **steps 2.1-2.10 implemented on 2026-10-21; quality-gated v2 ranking added on
2026-10-26; controlled mappings remain optional and namespace gaps remain explicit.**

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
- biological-source deduplication, capped support aggregation, structure-quality gates,
  and raw-evidence offline rescoring **(complete: 2026-10-26)**
- conservative v2 profile selected on development and checked without primary-endpoint
  regression on validation/test; powered scientific validation remains pending

## Phase 3 — Benchmarking

Status: **3.1-3.9 development pilot complete on 2026-10-25.**

### 3.1 Benchmark contract
- exact correctness and gold-evidence policy **(complete)**
- primary endpoint, hierarchy rules, inclusion/exclusion, and leakage thresholds **(complete)**
- claim rules and required reproducibility outputs **(complete)**

### 3.2 Characterized dataset
- curate versioned reviewed-protein manifest **(pilot complete: 60 queries)**

### 3.3 Leakage-controlled splits
- MMseqs2 cluster assignment and reference prohibited-target manifest **(pilot complete)**
- resolve benchmark targets and PDB chains through the exclusion catalog **(complete in 3.6)**

### 3.4 Difficulty strata
- closest-allowed Swiss-Prot reference identity bins **(pilot complete)**
- preserve retrieval-specific target resolution and exclusions **(complete in 3.6)**

### 3.5 Metrics
- retrieval, dual-retrieval, function, confidence-interval implementation **(complete)**
- subgroup paired randomization and Holm adjustment **(complete)**

### 3.6 Principal baselines
- B2 sequence-only, B3 structure-only, B4 deterministic dual retrieval **(complete)**

### 3.7 Mapping ablations
- no mapping, InterPro2GO, EC2GO, GO synonyms, all combined **(complete)**

### 3.8 Biological error analysis
- rescue, failure, incorrect agreement, metadata gaps, unavailable models **(complete)**

### 3.9 Reproducible benchmark package
- manifests, versions, commands, raw results, per-query and aggregate metrics **(complete)**

Exit criteria:
- development-pilot result: no measurable overall B4 benefit over B2; paired test-set
  FR@10 difference +0.0556, 95% CI 0.0000-0.1667 **(complete)**
- statistically powered final benchmark remains future work

## Phase 4 — Literature RAG

Status: **Phase 4.0-4.7 engineering implementation is complete. The human-provenanced
20-query v4 run passes the separate Phase 5 development-transition policy, while its
frozen scientific exit remains `FAIL` because six retrieval-quality checks missed their
thresholds.**

- frozen relevance, evidence-role, review, entity/organism, access, and packet-limit
  contract **(4.0 complete)**
- typed query, article, chunk, hit, biological-reference, and evidence-packet schemas
  plus JSON Schema export **(4.1 complete)**
- deterministic query builder with explicit gold-label exclusion, source-neutral query
  variants, checksummed manifest, and CLI **(4.2 complete)**
- PubMed metadata/abstract and PMC ESearch-filtered Open Access full-text adapters with immutable raw
  response caching and explicit access failures **(4.3 implemented; live pilot complete)**
- identifier deduplication and section-aware chunking **(4.4 implemented)**
- BM25 lexical/character-vector/hybrid retrieval and deterministic reranking
  **(4.5 implemented as baseline)**
- compact evidence packet builder **(4.6 implemented)**
- complete candidate-pool review table; lexical/vector/hybrid/reranked pooled metrics;
  retrieval/citation/entity/organism/experiment/contradiction checks; and frozen pilot
  thresholds **(4.7 implemented; expert annotations and passing result pending)**

Exit criteria:
- literature retrieval precision/recall evaluation on a 20-query human-labelled subset
  **(evaluated; scientific thresholds not met)**
- Phase 5 engineering transition **(PASS_FOR_PHASE5_DEVELOPMENT; not a scientific pass)**

## Phase 5 — LLM synthesis

Status: **`PASS_FOR_PHASE6_DEVELOPMENT` based on project-owner acceptance of the
grounded output and completed deterministic report verification. Blinded expert
comparison remains pending, so this is not a scientific Phase 5 pass.**

- structured, bounded prompt/context with versioned templates **(implemented)**
- grounded typed report schema with `NOT_CALIBRATED` confidence **(implemented)**
- local Ollama adapter with structured JSON output and raw-response preservation
  **(implemented)**
- deterministic citation/evidence-link verifier **(implemented)**
- controlled-identifier and experimental-overclaim checks **(implemented)**
- Phase 5.1 bounded biological evidence: top five leakage-filtered sequence and
  structure records, separate modalities, raw metrics and provenance **(complete)**
- separate sequence-support, structure-support, and cross-modal report sections with
  modality-discussion verification **(complete)**
- human/expert evaluation sample **(pending)**
- versioned 20-report human-review table and instructions **(template complete; review pending)**

Exit criteria:
- generated reports are more useful without reducing factual grounding

## Phase 6 — Confidence calibration

Status: **engineering-complete development pilot. Platt calibration fitted on 51
development examples and evaluated on 15 validation examples; exposed test excluded.**

- collect prediction/evidence features **(complete)**
- fit external Platt calibrator on development data **(complete)**
- validation reliability diagram / Brier score / ECE / log-loss **(complete)**
- define descriptive LOW/MODERATE/HIGH labels **(complete)**

Exit criteria:
- confidence correlates with empirical correctness on held-out characterized proteins
  **(development evidence only; larger newly locked cohort pending)**

## Next execution plan — scientific validation

1. Complete the 20-report Phase 5 human-review table and summarize acceptance,
   unsupported claims, modality interpretation, citation grounding, and usefulness.
   **(complete for the preserved `gemma3:4b` development run: 16 accept, 2 revise,
   2 reject; a new `gemma4:more` variant requires its own review)**
2. Freeze the current development system: Git commit, Pixi lock, contracts, prompts,
   Ollama model, database releases, manifests, and checksums. **(blocked from freeze:
   `gemma4:more` is selected but repeated schema-constrained smokes timed out or
   truncated; complete a small reliability pilot, full run, and review first)**
3. Build a new characterized panel of at least 200 reviewed proteins with experimental
   Tier-A EC or GO-MF labels, taxonomic/function diversity, and substantial low-identity
   representation. Exclude the existing 60 proteins and prohibited homolog clusters.
   Treat 200 proteins as a floor and expand the panel until Step 4 has at least 100
   validation and 100 untouched-test query-namespace examples. See
   `docs/SCIENTIFIC_VALIDATION_PANEL.md`.
4. Assign cluster-aware development/validation/test splits. Target at least 100
   query-namespace examples in validation and 100 in a completely untouched test set.
5. Freeze Phase 6 scientific thresholds before revealing new evaluation labels: improved
   Brier/log-loss over raw scores, ECE target, monotonic confidence-group accuracy,
   minimum group sizes, and a predeclared high-confidence accuracy target.
6. Run Phase 1-5 without gold-label access, freeze predictions/reports/confidence, then
   reveal validation labels. Compare raw score, Platt, isotonic, and multifeature logistic
   calibration using development/validation only.
7. Freeze the selected calibrator and evaluate the untouched test set exactly once,
   including EC, GO-MF, difficulty, taxonomy, and cross-modal subgroups.
8. Add calibrated confidence to future reports only after the unseen evaluation passes;
   keep confidence separate from experimental confirmation and literature truthfulness.
9. Evaluate optional Phase 7 GraphRAG only through an ablation against this non-graph
   baseline. Proceed only if grounding, contradiction handling, or expert usefulness
   improves measurably.
10. Begin the Phase 8 uncharacterized-protein study only after the calibrated pipeline
    and evidence boundaries are frozen.

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
