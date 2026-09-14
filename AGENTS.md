# AGENTS.md — Dual-Retrieval RAG for Protein Function Research

## Purpose
This repository implements a research-grade Dual-Retrieval RAG system for protein function prediction. It combines two independent biological retrieval channels:

1. **Sequence retrieval** — run eggNOG-mapper and optional MMseqs2/HMMER/BLAST/DIAMOND against databases stored on local external SSD/HPC storage.
2. **Structure retrieval** — fetch only the required predicted model through the AlphaFold DB REST API, cache it locally, and search it with Foldseek against a locally stored structure database. Experimental PDB retrieval remains an optional, separately labelled path.

The system keeps both channels separate long enough to measure agreement, disagreement, and modality-specific rescue. It then fuses evidence, optionally retrieves supporting literature from PubMed/PMC, and uses an LLM to generate a citation-grounded functional hypothesis with calibrated confidence.

## Repository map
Read these before major edits:

- `README.md` — project summary and quick start.
- `ARCHITECTURE.md` — system design, modules, data flow, schemas.
- `MEMORY.md` — durable project decisions and current status.
- `ROADMAP.md` — staged implementation plan and milestones.
- `ENVIRONMENT.md` — Conda/Python/bioinformatics dependencies and storage plan.
- `EVALUATION.md` — benchmark design, baselines, metrics, and ablations.
- `DATA.md` — database policy, local/external storage, caching, and provenance.
- `docs/REFERENCES.md` — research papers that motivate the design.

## Core scientific principle
Do not collapse sequence and structure evidence into one score too early.

For each query protein maintain:

- `R_seq`: sequence-derived evidence
- `R_struct`: structure-derived evidence
- `R_lit`: optional literature evidence

Classify cross-modal state as one of:

- `CONSENSUS`
- `PARTIAL_CONSENSUS`
- `SEQUENCE_ONLY`
- `STRUCTURE_ONLY`
- `CONFLICT`
- `INSUFFICIENT_EVIDENCE`

A disagreement is a research result, not an error to hide.

## First implementation target
The first working milestone is deliberately small:

```text
FASTA / UniProt ID
   ├── local eggNOG/MMseqs2 database search -> sequence_results.tsv
   └── AlphaFold DB REST API -> query model cache
                                  └── local Foldseek database search
                                             -> structure_results.tsv
                                  ↓
                           normalize + merge
                                  ↓
                           merged_results.tsv
```

Do not add an LLM until this biological retrieval pipeline is reproducible and benchmarked.

## Coding rules
- Python target: **3.11** unless compatibility forces a change.
- Prefer small, typed, testable modules over framework-heavy orchestration.
- Use `pathlib.Path`, type hints, dataclasses/Pydantic models, and explicit schemas.
- Separate tool wrappers from scientific logic.
- Never parse command output with fragile positional assumptions when a documented TSV/JSON format is available.
- Preserve raw tool outputs; write normalized outputs to separate files.
- Every derived table must carry provenance: tool, version, database version/date, parameters, source identifier.
- Use deterministic seeds where applicable.
- Log commands and versions used for every benchmark run.
- Prefer TSV/Parquet for tabular results; JSON/YAML for configuration and metadata.
- Do not hard-code machine-specific paths. Read paths from `config/config.yaml` or environment variables.

## External tools
Expected command-line dependencies include:

- MMseqs2
- eggNOG-mapper
- Foldseek
- HMMER
- BLAST+ and/or DIAMOND

Treat these as subprocess tools with explicit version checks. Do not reimplement their core algorithms in Python.

The AlphaFold DB integration is an HTTP adapter, not a subprocess tool. It retrieves
existing predicted models; it does not run AlphaFold or perform structural similarity
search. Foldseek remains responsible for structure search.

## Database rules
- Keep large databases outside the Conda environment and outside Git.
- Store the eggNOG and Foldseek target databases locally on external SSD/HPC storage.
- Do **not** mirror AlphaFoldDB. Query its REST API by UniProt accession, download only
  required models, and keep a bounded local cache for reproducibility and reuse.
- The AlphaFold REST API supplies query models only. It does not replace the local
  Foldseek target database or perform Foldseek similarity search.
- Never commit large databases, structures, model weights, generated indexes, or experiment output to Git.

## AlphaFold REST API rules

- Use a configurable base URL; do not scatter endpoint strings through the code.
- Prefer a supplied UniProt accession. For FASTA-only input, use an explicit accession
  resolution step and record its provenance; never assume a FASTA header is valid.
- Treat HTTP 404 as `model unavailable`, not as a negative function result.
- Use timeouts, bounded retries with backoff, and respectful request pacing.
- Preserve raw metadata responses separately from downloaded PDB/mmCIF files.
- Record the requested accession, endpoint, AlphaFold entry/model version, retrieval
  time, source URL, checksum, and cache path in an acquisition manifest.
- Verify that the returned accession and sequence are compatible with the query.
- Never label an AlphaFold model as experimental. If no model is available, retain the
  sequence channel and record the structure channel as unavailable.

Suggested environment variables:

```bash
DUALRAG_DATA_ROOT=/external_ssd/dualrag
EGGNOG_DATA_DIR=$DUALRAG_DATA_ROOT/databases/eggnog
DUALRAG_FOLDSEEK_DB=$DUALRAG_DATA_ROOT/databases/foldseek/pdb
DUALRAG_ALPHAFOLD_API_URL=https://alphafold.ebi.ac.uk/api
DUALRAG_TMP=$DUALRAG_DATA_ROOT/tmp
DUALRAG_RESULTS=$DUALRAG_DATA_ROOT/results
```

## Scientific safety / claims
- The system produces **putative functions / hypotheses**, not experimental confirmation.
- Do not describe a prediction as validated unless the supporting source explicitly provides experimental evidence.
- Distinguish experimental PDB structures from predicted AlphaFold structures.
- Distinguish a close sequence homolog from a remote structural analog/homolog.
- Preserve uncertainty and conflicting evidence in user-facing reports.
- The LLM must not invent function, EC number, GO term, pathway, citation, active site, or experimental result.

## Retrieval and fusion rules
- Normalize sequence and structure scores separately before fusion.
- Keep raw metrics such as identity, coverage, E-value, bitscore, Foldseek score/TM-score where available.
- Functional names should be normalized before comparing agreement, ideally using controlled identifiers (GO, EC, InterPro, Pfam, orthologous groups) plus semantic comparison.
- Fusion weights and confidence thresholds are experimental hyperparameters. They must be calibrated on validation data, not chosen by the LLM.
- Literature retrieval supports or contextualizes biological hypotheses; it does not override stronger primary sequence/structure evidence without an explicit rule.

## LLM rules
When an LLM is introduced:

- Supply a structured evidence packet, not raw database dumps.
- Require evidence-linked claims.
- Require explicit uncertainty and alternatives.
- Use an external confidence/calibration module; do not use the LLM's self-reported confidence as the final score.
- Run citation verification before accepting a generated report.

## Testing expectations
Before marking work complete:

1. Run unit tests for changed Python modules.
2. Run formatting/linting checks.
3. Run a tiny smoke test on a small FASTA fixture where external tools are available.
4. Mock AlphaFold HTTP responses in unit tests; routine tests must not depend on the public service.
5. If an external API/database/tool is unavailable, mock only the boundary and clearly report what was not executed.
6. Never claim an integration test passed if the actual API, bioinformatics executable, or database was absent.

Suggested commands once implemented:

```bash
pytest -q
ruff check src tests
python -m dualrag --help
```

## Preferred repository structure

```text
dual_rag/
├── AGENTS.md
├── MEMORY.md
├── README.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── ENVIRONMENT.md
├── EVALUATION.md
├── DATA.md
├── environment.yml
├── config/
│   └── config.yaml
├── src/dualrag/
│   ├── sequence/
│   ├── structure/
│   ├── retrieval/
│   ├── fusion/
│   ├── literature/
│   ├── rag/
│   ├── evaluation/
│   └── cli.py
├── tests/
├── scripts/
└── docs/
    └── REFERENCES.md
```

## Change discipline
For non-trivial architectural changes:

1. Read `MEMORY.md` and `ARCHITECTURE.md`.
2. State which interface/data contract changes.
3. Update tests.
4. Update relevant documentation in the same change.
5. If a previous durable decision is intentionally reversed, update `MEMORY.md` with the new decision and reason.

## Immediate priority
Build Phase 1 first: local eggNOG sequence retrieval, AlphaFold REST model acquisition,
local Foldseek structure retrieval, normalization, and merge. The RAG/LLM layer comes
after retrieval quality can be measured independently.
