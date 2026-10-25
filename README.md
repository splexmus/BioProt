# Dual-Retrieval RAG for Protein Function Research

This repository contains the **completed Phase 1 dual-retrieval implementation and
Phase 2 function-fusion baseline**. FASTA input is resolved into two independent
evidence channels, normalized separately, grouped into function candidates, classified,
and ranked without hiding modality-specific evidence. Both an offline fixture backend
and real eggNOG-mapper + AlphaFold DB REST + local Foldseek adapters are available.

The default `fixture` backend requires no biological databases, downloads, or network
access. Its records are synthetic and exist only to exercise schemas, provenance,
agreement states, and reproducibility. It does **not** predict the supplied sequence's
real function.

## Quick start (no external data)

```bash
pixi install --locked
pixi run smoke-fixture
```

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

`check-tools` is diagnostic: missing executables are reported, but fixture mode remains
fully usable. External mode fails closed until real database versions replace the
`UNVERIFIED` placeholders.

Pixi is the supported environment manager. `pixi.toml` declares intentional Phase 1
dependencies and `pixi.lock` pins the complete solve. See `ENVIRONMENT.md` for setup,
upgrade policy, and project-specific advantages and limitations.

Accepted structure accessions are explicit UniProt-style FASTA identifiers such as
`P69905` or `sp|P69905|HBA_HUMAN`. Other headers are recorded as unresolved and retain
the sequence channel without making an AlphaFold request.

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
