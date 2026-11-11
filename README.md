# Dual-Retrieval RAG for Protein Function Research

This repository contains the **completed Phase 1 dual-retrieval implementation and
Phase 2 function-fusion baseline**. FASTA input is resolved into two independent
evidence channels, normalized separately, grouped into function candidates, classified,
and ranked without hiding modality-specific evidence. Both an offline fixture backend
and real eggNOG-mapper + AlphaFold DB REST + local Foldseek adapters are available.

The release-pinned full Pfam-to-InterPro mapping workflow is documented in
[`docs/INTERPRO_PFAM_MAPPING.md`](docs/INTERPRO_PFAM_MAPPING.md).

The default `fixture` backend requires no biological databases, downloads, or network
access. Its records are synthetic and exist only to exercise schemas, provenance,
agreement states, and reproducibility. It does **not** predict the supplied sequence's
real function.

## Quick start (no external data)

```bash
pixi install --locked
pixi run smoke-fixture
```

This works on Linux and natively on Windows. Windows gets the pure-Python core;
real sequence and structure searches need Linux or WSL2. See `ENVIRONMENT.md#windows`.

The output directory contains raw channel outputs, `sequence_results.tsv`,
`structure_results.tsv`, the Phase 1 `merged_results.tsv`, Phase 2
`function_candidates.tsv`, `fusion_summary.tsv`, `conflicts.tsv`, `alternatives.tsv`,
and `fusion_audit.json`, a query manifest,
a config snapshot, run metadata, and a command log.

Compare two completed runs while excluding only documented volatile fields:

```bash
pixi run python -m dualrag compare-runs \
  --first results/run1 \
  --second results/run2 \
  --output results/reproducibility.json
```

Validation:

```bash
pixi run validate
```

Run the complete safe offline process test, including two reproducible Phase 1-2 fixture
runs and Phase 4 query construction:

```bash
pixi run test-all-processes
```

See `docs/TESTING_ALL_PROCESSES.md` for real-database, literature, Ollama, calibration,
and exploratory Phase 8 testing steps and their scientific interpretation boundaries.
For a phase-by-phase operator walkthrough, use `docs/USER_MANUAL.md`. The implemented
`dualrag analyze` command accepts FASTA or one UniProt accession, runs Phase 1-2, and
writes a deterministic summary/status with sequence and structure support separated,
provisional ranking scores labelled as non-probabilities, and the failed Phase 6
calibration status exposed explicitly. Graphical-interface work is tracked in
`docs/USER_INTERFACE_PLAN.md`.

Every `analyze` run also writes `calibration/calibration_report.md`, JSON and candidate
diagnostics. Supply `--calibration-model PATH` to include a saved cohort model's status
and checksum in the applicability report. The current benchmark model is incompatible
with native eggNOG/Foldseek analysis features, so its probabilities are not applied.
When literature is enabled, `literature/top_literature.md` and TSV list the top ten
retrieved passages per query. Ollama reports include both the external Phase 6
assessment and retrieved literature references. See `docs/PHASE6_CALIBRATION.md`.

```bash
pixi run python -m dualrag analyze \
  --uniprot P69905 \
  --config config/4tb-hdd.yaml \
  --output /media/splexmus/4TB_HDD1/dualrag/analyses/P69905-v1
```

Add local literature and an explicitly experimental grounded Ollama report with:

```bash
pixi run python -m dualrag analyze \
  --uniprot P69905 \
  --config config/4tb-hdd.yaml \
  --output /media/splexmus/4TB_HDD1/dualrag/analyses/P69905-report-v1 \
  --literature local \
  --literature-index /media/splexmus/4TB_HDD1/dualrag/literature/indexes/phase4-exit-development-v4.sqlite3 \
  --report ollama \
  --allow-unvalidated-phase4
```

`check-tools` is diagnostic: missing executables are reported, but fixture mode remains
fully usable. External mode fails closed until real database versions replace the
`UNVERIFIED` placeholders.

Pixi is the supported environment manager. `pixi.toml` declares intentional Phase 1
dependencies and `pixi.lock` pins the complete solve. See `ENVIRONMENT.md` for setup,
upgrade policy, and project-specific advantages and limitations.

Accepted structure accessions are explicit UniProt-style FASTA identifiers such as
`P69905` or `sp|P69905|HBA_HUMAN`. Other headers are recorded as unresolved and retain
the sequence channel without making an AlphaFold request.

## Web demo

A browser demo runs without any biological databases:

```bash
pixi run demo
```

It lets you run the pipeline on built-in synthetic cases, explore real predictions for 47
benchmark proteins against curated labels, and see the scientific status with confidence
intervals. To publish it as a free public link, see `docs/DEMO.md`.

## Scientific boundaries

- Fixture annotations are synthetic test data, never biological evidence.
- Scores are deterministic PoC normalization features, not calibrated confidence.
- `CONFLICT` is retained as evidence; it is never averaged away.
- Missing metrics are blank TSV cells and explicit `None` values internally.
- No LLM or literature layer is present in this milestone.
- An incomplete target database is not a research-complete search space.

See `ARCHITECTURE.md`, `DATA.md`, and `docs/POC.md` for contracts and extension points.
The complete Phase 2.1-2.10 rules, mapping schemas, reranking formula, outputs,
validation, and scientific limitations
are documented in `docs/PHASE2_FUSION.md`.

Build a portable, checksummed mapping bundle from official InterPro/Pfam and reviewed
UniProt records with `scripts/build_phase2_mapping_bundle.py`. The characterized bundle
validated on 2026-10-22 is packaged under `dist/` for copying to external storage.

Phase 3.1 is frozen in `docs/BENCHMARK_CONTRACT.md` with a machine-readable counterpart
at `config/benchmark-contract-v1.yaml`. It defines exact correctness, the primary
EC/GO-MF endpoint, gold evidence, leakage exclusions, statistical reporting, and claim
rules before benchmark proteins are collected.

The Phase 3.2-3.4 development pilot, including its 60-protein dataset,
leakage-controlled splits and difficulty strata, is explained in
`docs/PHASE3_DATASET.md` and stored under `benchmark/phase3-pilot-v1/`.

The completed Phase 3 development benchmark, including B2/B3/B4 results, mapping
ablations, error analysis and reproducibility artifacts, is reported in
`docs/PHASE3_REPORT.md` and stored under `benchmark/phase3-run-v1/`.

The supplied 60-protein candidate panel was screened and rerun as an independent
external case without modifying the original test split. Screening retained 47
proteins, and the complete result is in `docs/PHASE3_EXTERNAL_PANEL_REPORT.md`, with
dataset and run artifacts under `benchmark/phase3-external-panel-v1/` and
`benchmark/phase3-external-panel-run-v1/`.

The production fusion profile is now `quality-gated-v2`. It deduplicates repeated
biological sources, rewards independent support with a capped bonus, reduces weak
structure-function transfer using coverage/TM-score gates, and supports safe offline
rescoring from preserved raw evidence. It improved development FR@10 from 0.557 to
0.575 while preserving validation and the previously exposed test FR@10. This is a ranking
improvement, not a new biological-validation claim; the Phase 3 conclusion remains
`NO_MEASURABLE_OVERALL_BENEFIT`. See `docs/PIPELINE_V2.md`.

Phase 4.0-4.1 is frozen in `docs/LITERATURE_CONTRACT.md` with machine-readable policy
in `config/literature-contract-v1.yaml` and generated JSON schemas in
`config/literature-schemas-v1.json`. Typed records for literature queries, articles,
chunks, hits, and compact evidence packets live in `dualrag.literature.schemas`.
Phase 4.3-4.7 is now implemented as an executable, evaluation-gated pipeline. PubMed
provides metadata/abstracts, PMC OA provides eligible full text, and all retrieved
passages remain `UNASSESSED` until explicit annotation. No LLM claim generation is
enabled inside Phase 4.

Phase 4 also supports a persistent, checksummed SQLite chunk/vector index for offline
hybrid search without repeated PubMed calls. Build and search instructions are in
`docs/LITERATURE_VECTOR_INDEX.md`. The current overall evidence and failed scientific
gates are summarized in `docs/SCIENTIFIC_STATUS_REPORT.md`.

Phase 5 now has an experimental local-Ollama path. It rejects unvalidated Phase 4 input
by default; the explicit development override keeps literature as background, records
the bypass, and emits `NOT_CALIBRATED` confidence. See
`docs/PHASE5_LLM_SYNTHESIS.md`. Phase 5.1 adds at most five leakage-filtered MMseqs2
sequence hits and five Foldseek structure hits to each compact packet while preserving
raw metrics and provenance. Run:

```bash
pixi run python -m dualrag init-ollama --model gemma4:more
scripts/enrich_phase5_biological_evidence.sh
scripts/run_phase5_ollama.sh smoke \
  --run-name phase5-ollama-biological-v1 \
  --query-id P01040
```

Phase 6 has a development-only external confidence calibrator. It estimates exact top-1
EC/GO-MF correctness from the B4 ranking score, never from LLM self-confidence. Run:

```bash
scripts/run_phase6_calibration.sh
```

The current 15-example validation result is useful for engineering but too small for
production confidence. See `docs/PHASE6_REPORT.md`.

Phase 4.2 now builds deterministic, leakage-safe literature queries from completed
biological runs:

```bash
pixi run python -m dualrag build-literature-queries \
  --run results/my-biological-run \
  --output results/my-literature-queries \
  --context query_context.tsv
```

See `docs/PHASE4_QUERY_BUILDER.md`. Run Phase 4.3-4.6 on external storage with:

```bash
scripts/run_phase4_on_hdd.sh \
  --queries results/my-literature-queries/literature_queries.jsonl \
  --email you@example.org \
  --run-name phase4-pilot-v1
```

The runner creates the Phase 4.7 manual-label template. Full stage behavior, outputs,
limitations, and the evaluation command are in `docs/PHASE4_PIPELINE.md`.

For the ≥20-query pooled evaluation required by the Phase 4 exit gate, use
`scripts/run_phase4_exit_benchmark.sh`. It builds leakage-safe development queries from
Phase 3 artifacts, preserves all method-ranked candidates, generates an annotation TSV
with passage context, and applies the pre-frozen thresholds after human review. See
`docs/PHASE4_EXIT_BENCHMARK.md`.

For the full external-HDD database setup, including the writable-mount preflight,
eggNOG installation, Foldseek PDB download, provenance finalization, and validation,
see [Phase 1 data installation](docs/PHASE1_DATA_INSTALL.md). The current production
profile is [`config/4tb-hdd.yaml`](config/4tb-hdd.yaml).

After the core eggNOG and Foldseek databases are installed, preview or run the
resumable full-data downloader with:

```bash
scripts/download_phase1_full_data.sh --data-root "$DUALRAG_DATA_ROOT" --dry-run
scripts/download_phase1_full_data.sh --data-root "$DUALRAG_DATA_ROOT" --yes
```

A reviewed five-protein external integration fixture is available at
`tests/fixtures/phase1_characterized.fasta`, with source labels and checksums in
`tests/fixtures/phase1_characterized_manifest.tsv`. See the Phase 1 installation guide
for the real-database invocation and `docs/PHASE1_CHARACTERIZED_RUN.md` for the
validated result and repeat-run evidence.
