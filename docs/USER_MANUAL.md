# BioProt user manual: run each phase step by step

Version: 2026-11-07  
Current status: engineering workflow operational; scientific calibration not passed

This manual separates routine analysis of one protein from cohort-level scientific
benchmarking. Commands are run from `/home/splexmus/Documents/BioProt`.

## Choose your goal

| Goal | Phases to use |
|---|---|
| Check that the installation works | 0, then the offline test |
| Analyze one new protein | 0, 1, 2, optionally 4 and 5 |
| Benchmark retrieval scientifically | 3 |
| Evaluate literature retrieval | 4.7 |
| Generate a grounded draft report | 5 |
| Calibrate confidence on a characterized cohort | 6 |
| Test GraphRAG | 7, optional and not implemented |
| Study uncharacterized proteins | 8, exploratory pilot only |

Phases 3 and 6 are cohort evaluations. Do not run them for a single protein and do not
open sealed test labels merely to obtain a result.

## Phase 0 — Install and check the environment

```bash
cd /home/splexmus/Documents/BioProt
pixi install --locked
pixi run test-all-processes
```

Expected final message:

```text
SAFE OFFLINE TEST: PASS
```

This proves the software and synthetic data flow work. It does not prove biological
accuracy. Confirm the external drive and tools before a real run:

```bash
findmnt -T /media/splexmus/4TB_HDD1/dualrag
pixi run python -m dualrag check-tools
```

The eggNOG database warning must be resolved for real sequence retrieval. Database
installation and provenance instructions are in `docs/PHASE1_DATA_INSTALL.md`.

## Prepare the input

### Option A — You already have a FASTA file

Use one or more canonical amino-acid sequences:

```fasta
>sp|P69905|HBA_HUMAN
MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTY...
```

For AlphaFold acquisition, the header must contain a validated UniProt accession such
as `P69905` or `sp|P69905|HBA_HUMAN`. A FASTA-only identifier may still use the sequence
channel, but structure acquisition can remain unavailable.

### Option B — You only have a UniProt accession

The current `run` command does not accept a bare accession. Download the canonical
FASTA from UniProt first and inspect it:

```bash
mkdir -p inputs
ACCESSION=P69905
curl --fail --location \
  "https://rest.uniprot.org/uniprotkb/${ACCESSION}.fasta" \
  --output "inputs/${ACCESSION}.fasta"
head -n 2 "inputs/${ACCESSION}.fasta"
```

Do not continue if the request fails, returns an obsolete/replaced accession without a
documented mapping, or returns a sequence different from the sequence you intend to
study. Direct, validated accession input is planned but not implemented yet.

## Phase 1 — Retrieve sequence and structure evidence

Set storage locations once per shell:

```bash
export DUALRAG_DATA_ROOT=/media/splexmus/4TB_HDD1/dualrag
export DUALRAG_RESULTS="$DUALRAG_DATA_ROOT/results"
```

Run the real-data profile. This command also performs Phase 2 fusion after retrieval:

```bash
INPUT=inputs/P69905.fasta
RUN_NAME=P69905-analysis-v1

pixi run python -m dualrag run \
  --config config/4tb-hdd.yaml \
  --input "$INPUT" \
  --output "$DUALRAG_RESULTS/$RUN_NAME"
```

Phase 1 outputs:

| File | Meaning |
|---|---|
| `queries.tsv` | Parsed query identifiers and sequences |
| `sequence_results.tsv` | eggNOG-derived sequence evidence |
| `structure_results.tsv` | Foldseek structural matches |
| `alphafold_acquisition.tsv` | Model availability, source, checksum, and compatibility |
| `merged_results.tsv` | Normalized modalities, still independently visible |
| `run_metadata.json` | Versions, parameters, counts, and provenance |

Checks:

1. Confirm `synthetic_fixture_data` is false in `run_metadata.json`.
2. Confirm sequence hits have database/tool provenance.
3. Confirm an AlphaFold structure is labelled predicted, never experimental.
4. A missing model should be recorded as unavailable and retain sequence evidence.

## Phase 2 — Inspect mapping, fusion, conflict, and alternatives

Phase 2 runs automatically inside the Phase 1 command. Review:

| File | Question answered |
|---|---|
| `function_candidates.tsv` | Which controlled functions are candidates? |
| `fusion_summary.tsv` | Do sequence and structure agree? |
| `conflicts.tsv` | Which informative modalities disagree? |
| `alternatives.tsv` | Which close alternative hypotheses remain? |
| `fusion_audit.json` | Which mappings, weights, gates, and support rules were used? |

Allowed cross-modal states are `CONSENSUS`, `PARTIAL_CONSENSUS`, `SEQUENCE_ONLY`,
`STRUCTURE_ONLY`, `CONFLICT`, and `INSUFFICIENT_EVIDENCE`. A fused score is a ranking
feature, not probability or experimental confirmation.

## Phase 3 — Benchmark retrieval on characterized proteins

Skip this phase for ordinary single-protein analysis. It tests B2 sequence-only, B3
structure-only, and B4 dual retrieval on cluster-separated characterized proteins.

Re-score the preserved development evidence without rerunning external retrieval:

```bash
pixi run python scripts/run_phase3_benchmark.py \
  --dataset benchmark/phase3-pilot-v1 \
  --swissprot-dat /not-used-when-reusing-raw \
  --output benchmark/phase3-manual-check-v1 \
  --tmp-dir /tmp/dualrag-phase3-manual-check \
  --mapping-projections benchmark/phase3-mappings-v1/mapping_projections.tsv \
  --synonyms benchmark/phase3-mappings-v1/synonyms.tsv \
  --target-pool-k 10 \
  --quality-gated-fusion \
  --reuse-raw-evidence
```

Use a new output directory. Previously revealed data can test regression but cannot
provide new confirmatory evidence. The current overall conclusion remains no measurable
general dual-retrieval benefit on the newest independent cohort.

## Phase 4 — Retrieve supporting literature

### 4.1 Build literature queries

```bash
BIO_RUN="$DUALRAG_RESULTS/P69905-analysis-v1"
QUERY_RUN="$DUALRAG_RESULTS/P69905-literature-queries-v1"

pixi run python -m dualrag build-literature-queries \
  --run "$BIO_RUN" \
  --output "$QUERY_RUN"
```

If the FASTA header does not provide protein name, organism, and taxonomy, supply the
approved context TSV described in `docs/PHASE4_QUERY_BUILDER.md`.

### 4.2 Search the existing local literature index

```bash
INDEX=/media/splexmus/4TB_HDD1/dualrag/literature/indexes/phase4-exit-development-v4.sqlite3
LIT_RUN=/media/splexmus/4TB_HDD1/dualrag/literature/runs/P69905-vector-v1

pixi run python -m dualrag search-literature-index \
  --queries "$QUERY_RUN/literature_queries.jsonl" \
  --index "$INDEX" \
  --output "$LIT_RUN" \
  --top-k 20
```

This performs no network requests and searches only the stored corpus.

### 4.3 Acquire new PubMed/PMC records when needed

```bash
export NCBI_API_KEY="your-existing-key"

scripts/run_phase4_on_hdd.sh \
  --queries "$QUERY_RUN/literature_queries.jsonl" \
  --email YOUR_REAL_EMAIL@example.org \
  --run-name P69905-literature-online-v1
```

Missing papers or inaccessible full text are not negative biological evidence. Inspect
`literature_hits.jsonl` and `evidence_packets.jsonl`. Hits remain `UNASSESSED` until
manual review.

### 4.4 Evaluate literature retrieval

Phase 4.7 requires complete human labels over the candidate pool. Follow
`docs/PHASE4_EXIT_BENCHMARK.md`; do not reuse a partial hit-only label table to claim
recall. The current frozen Phase 4 scientific exit remains `FAIL`.

## Phase 5 — Generate a grounded draft report

The current generic Phase 5 runner is best supported by the preserved Phase 4 benchmark
packet layout. Start with one report:

```bash
ollama serve
```

In another terminal:

```bash
scripts/run_phase5_ollama.sh smoke \
  --phase4-run phase4-exit-development-v4 \
  --run-name phase5-manual-smoke-v1 \
  --model gemma4:more
```

Check the Markdown report and verifier result. It must discuss sequence evidence,
structure evidence, cross-modal state, literature, alternatives, and uncertainty as
separate topics. Current reports retain the Phase 4 development override and
`NOT_CALIBRATED` confidence.

For a new single-protein run, automatic biological-evidence enrichment is a known
interface gap: the existing convenience script expects the Phase 3 benchmark layout.
Do not manually copy incompatible tables merely to make generation run; this is included
in the interface plan.

## Phase 6 — Calibrate confidence on a cohort

Do not run Phase 6 for one protein. A development-only regression command is:

```bash
scripts/run_phase6_calibration.sh --run-name phase6-manual-development-check-v1
```

The current status is `FAIL_SCIENTIFIC_CALIBRATION_GATE`. Do not access the sealed test
labels, attach calibrated probabilities to new reports, or lower thresholds after
seeing results.

## Phase 7 — Optional GraphRAG

Phase 7 is not implemented and is not required for single-protein analysis. Implement it
only as an ablation against the current non-graph retrieval baseline. It must demonstrate
measurable improvement before adoption.

## Phase 8 — Exploratory uncharacterized-protein study

Phase 8 may currently run only as a development pilot:

1. Record accession, sequence checksum, organism, selection reason, and annotation state.
2. Exclude exact accessions, identical sequences, and prohibited homology clusters from
   evaluation/reference leakage as required by the study contract.
3. Run Phases 1, 2, 4, and optionally 5.
4. Preserve modality disagreement and alternative hypotheses.
5. Use `NOT_CALIBRATED`, `ABSTAIN`, or `INSUFFICIENT_EVIDENCE` where appropriate.
6. Require expert review and prioritize only plausible candidates for experiments.

Do not describe a Phase 8 hypothesis as a newly discovered or validated function.

## Final interpretation checklist

Before sharing a result, answer yes to all applicable questions:

- Are the input accession and sequence checksum recorded?
- Are sequence and structure evidence shown separately?
- Is an AlphaFold model clearly labelled predicted?
- Are conflicts and unavailable modalities visible?
- Are literature passages linked to PMID/PMCID/DOI and still correctly scoped?
- Is confidence labelled `NOT_CALIBRATED` under the current status?
- Is the conclusion worded as a putative function or hypothesis?
- Can another user reproduce the run from its manifest and commands?

For routine regression testing, use `docs/TESTING_ALL_PROCESSES.md`.
