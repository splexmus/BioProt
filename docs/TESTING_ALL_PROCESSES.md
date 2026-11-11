# User-friendly testing of the complete BioProt process

## One safe command

From the repository root:

```bash
pixi install --locked
pixi run test-all-processes
```

This is the routine test to run after changing code. The same command works on Windows
(PowerShell), where it runs `scripts/test_all_processes.py` instead of the Bash script.
It uses temporary files in the system temp directory, removes them when finished, does not use the network, does not write to the HDD,
and never reads sealed scientific test labels.

## What the command tests

| Process | Automated check | Meaning of PASS |
|---|---|---|
| Environment | Pixi environment and CLI import | Python package can start |
| Unit contracts | Complete `pytest` suite | Schemas and scientific logic pass their fixtures |
| Static quality | Ruff | No configured lint/import errors |
| External tools | `check-tools` | Availability is reported; missing optional tools are warnings |
| Phase 1 | Synthetic sequence and structure fixture | Both retrieval adapters produce valid normalized records |
| Phase 2 | Fixture fusion | Candidates, agreement, conflict, alternatives, and audits are produced |
| Reproducibility | Two fixture runs compared | Stable biological outputs are identical |
| Phase 4.2 | Literature-query builder | Leakage-safe queries can be constructed from biological evidence |
| Vector index | Unit-tested build/search/overwrite protection | Persistent offline literature search contract works |
| Phase 4-6 runners | Bash syntax and help | User-facing runner interfaces are loadable |

A PASS here means **engineering regression checks passed**. Synthetic fixture results
are not biological predictions, and this command does not change a scientific gate.

## Test a real new protein through Phase 1-2

Create `my_protein.fasta`, then run:

```bash
export DUALRAG_DATA_ROOT=/media/splexmus/4TB_HDD1/dualrag
export DUALRAG_RESULTS="$DUALRAG_DATA_ROOT/results"

PYTHONPATH=src pixi run python -m dualrag run \
  --config config/4tb-hdd.yaml \
  --input my_protein.fasta \
  --output "$DUALRAG_RESULTS/my-protein-v1"
```

Check these outputs:

```text
sequence_results.tsv       sequence evidence
structure_results.tsv      structure evidence or explicit unavailability
merged_results.tsv         Phase 1 normalized channels
function_candidates.tsv    Phase 2 candidates
fusion_summary.tsv         cross-modal state
conflicts.tsv              disagreements retained for review
fusion_audit.json          scoring and provenance
run_metadata.json          versions and commands
```

This real run needs the configured databases, external tools, and writable HDD. An
unavailable AlphaFold model must produce a sequence-only result, not a false negative.

## Test Phase 3 benchmarking

Phase 3 is a scientific evaluation, not a routine smoke test. Use only a development or
validation split whose access is authorized. Do not open the sealed Phase 6 test vault.

The current authoritative results are already documented in `docs/PHASE3_REPORT.md` and
`docs/PHASE6_RANKING_SUFFICIENCY_RESULTS.md`. Re-running an exposed benchmark is useful
for regression testing but cannot provide new confirmatory evidence.

## Test Phase 4 literature retrieval

First build queries from a real biological run:

```bash
pixi run python -m dualrag build-literature-queries \
  --run "$DUALRAG_RESULTS/my-protein-v1" \
  --output "$DUALRAG_RESULTS/my-protein-literature-queries"
```

Choose one of two paths.

### Offline local-vector search

```bash
pixi run python -m dualrag search-literature-index \
  --queries "$DUALRAG_RESULTS/my-protein-literature-queries/literature_queries.jsonl" \
  --index /media/splexmus/4TB_HDD1/dualrag/literature/indexes/phase4-exit-development-v4.sqlite3 \
  --output /media/splexmus/4TB_HDD1/dualrag/literature/runs/my-protein-vector-v1 \
  --top-k 20
```

### Online PubMed/PMC acquisition

```bash
export NCBI_API_KEY="your-existing-key"

scripts/run_phase4_on_hdd.sh \
  --queries "$DUALRAG_RESULTS/my-protein-literature-queries/literature_queries.jsonl" \
  --email YOUR_REAL_EMAIL@example.org \
  --run-name my-protein-literature-v1
```

Online acquisition expands the local corpus. Offline search only searches documents
already stored in the selected index. Missing literature is not negative functional
evidence.

## Test Phase 5 report generation

Start Ollama, then run a single-packet smoke test before a full run:

```bash
ollama serve

scripts/run_phase5_ollama.sh smoke \
  --phase4-run my-protein-literature-v1 \
  --run-name my-protein-phase5-v1 \
  --model gemma4:more
```

Review the generated Markdown report and verifier output. Confirm that sequence support,
structure support, literature evidence, conflicts, alternatives, and uncertainty remain
separate. The current Phase 4 override and `NOT_CALIBRATED` confidence must remain.

## Test Phase 6 calibration

Phase 6 is not a routine command for a single protein. It needs a characterized,
cluster-separated cohort with frozen predictions and authorized labels. The current
scientific gate is `FAIL_SCIENTIFIC_CALIBRATION_GATE`, so do not run or inspect the
sealed test split. Development-only calibration can be invoked with a new run name:

```bash
scripts/run_phase6_calibration.sh --run-name phase6-development-check-v1
```

Passing software tests does not override Brier, log-loss, ECE, confidence-group, or
sample-size requirements.

## Phase 7 and Phase 8

- Phase 7 GraphRAG is optional and not implemented; test it only as an ablation against
  the non-graph baseline.
- Phase 8 may run as an explicitly exploratory uncharacterized-protein pilot. Require
  accession/checksum exclusion, homology-cluster checks, separate modalities, expert
  review, `NOT_CALIBRATED`, and `ABSTAIN`. It is not an official validated Phase 8 study
  until the earlier scientific gates pass.

## How to report results

Use one of these exact conclusions:

- `PASS_ENGINEERING_OFFLINE_TESTS` — routine script passed.
- `PASS_REAL_RETRIEVAL_SMOKE` — real databases/API were exercised successfully.
- `FAIL_ENGINEERING_TEST` — code, schema, command, or reproducibility failed.
- `FAIL_SCIENTIFIC_GATE` — software worked, but a frozen scientific threshold failed.
- `INSUFFICIENT_EVIDENCE` — a protein lacks enough evidence for a supported hypothesis.

Never convert an engineering PASS into a biological-validation claim.
