# Plan: user-friendly BioProt interface

Status: CLI milestones 1, 2, and the initial deterministic summary are implemented;
literature/report orchestration and graphical UI remain planned

## Goal

Allow a user to start with exactly one of:

- a FASTA file; or
- a UniProt accession such as `P69905`.

The interface should guide the user from validated input to an auditable hypothesis
without exposing internal file wiring or weakening scientific boundaries.

## Proposed simplest interface

Build one orchestration command on top of the existing typed modules:

```bash
pixi run python -m dualrag analyze \
  --fasta my_protein.fasta \
  --output /media/splexmus/4TB_HDD1/dualrag/analyses/my-protein-v1

pixi run python -m dualrag analyze \
  --uniprot P69905 \
  --output /media/splexmus/4TB_HDD1/dualrag/analyses/P69905-v1
```

Exactly one of `--fasta` and `--uniprot` must be supplied. The first release should be a
CLI, not a web application: it reuses current code, is scriptable on workstations/HPC,
and provides a stable contract for a later graphical interface.

## User choices

Keep the initial options small:

```text
--fasta FILE | --uniprot ACCESSION      required input
--output DIR                            required run directory
--literature none|local|online          default: local
--report none|ollama                     default: none
--email ADDRESS                          required only for online literature
--resume                                 continue a recorded interrupted run
```

Database paths, model defaults, thresholds, and scientific policies stay in versioned
configuration rather than becoming dozens of command-line flags.

## Proposed workflow

```text
FASTA file OR UniProt accession
              ↓
Input validation and accession resolution
              ↓
Sequence retrieval ───── Structure acquisition/search
              ↓                    ↓
       independent normalized evidence
              ↓
Mapping, candidates, cross-modal state, alternatives
              ↓
Evidence sufficiency → predict or ABSTAIN
              ↓
Optional local/online literature retrieval
              ↓
Optional grounded Ollama report
              ↓
summary.md + status.json + complete phase artifacts
```

## Milestone 1 — Unified input resolver (implemented)

Implement first because every later screen and command depends on trustworthy identity.

For `--uniprot`:

1. Validate accession syntax.
2. Retrieve the canonical UniProt FASTA and metadata through one configurable adapter.
3. Cache the raw response and record retrieval time, source URL, release where available,
   accession status/replacement, taxonomy, and SHA-256 sequence checksum.
4. Reject ambiguous, deleted, or incompatible records with an actionable message.

For `--fasta`:

1. Validate amino-acid alphabet, non-empty sequences, and unique identifiers.
2. Parse a UniProt accession only when the supported header pattern matches.
3. If no accession is resolved, run sequence retrieval and explicitly mark AlphaFold
   structure acquisition unavailable unless a later documented resolver succeeds.
4. Never assume arbitrary FASTA text is a valid accession.

Tests must mock UniProt HTTP responses and cover valid, obsolete, missing, malformed,
multi-record, and sequence-mismatch cases.

## Milestone 2 — Single-run orchestrator (Phase 1-2 implemented)

Add an `analyze` service that calls existing Phase 1, Phase 2, and Phase 4 functions. It
should not duplicate eggNOG, Foldseek, fusion, or literature logic.

Required behavior:

- preflight tool/database/HDD checks before expensive work;
- refuse overwrite; support manifest-based `--resume`;
- create one run identifier and directory tree;
- record each stage as `PENDING`, `RUNNING`, `COMPLETE`, `UNAVAILABLE`, `FAILED`, or
  `SKIPPED`;
- allow sequence-only completion when AlphaFold is unavailable;
- stop report generation if evidence packets are invalid;
- never access benchmark gold labels.

Suggested output layout:

```text
analysis-run/
├── input/
│   ├── query.fasta
│   └── input_manifest.json
├── biological/
│   ├── sequence_results.tsv
│   ├── structure_results.tsv
│   ├── function_candidates.tsv
│   ├── fusion_summary.tsv
│   ├── conflicts.tsv
│   └── alternatives.tsv
├── literature/
│   ├── literature_hits.jsonl
│   └── evidence_packets.jsonl
├── report/
│   ├── report.md
│   └── verification.json
├── status.json
├── summary.md
└── run_manifest.json
```

## Milestone 3 — New-protein evidence packet adapter

Remove the current Phase 5 gap by building biological references directly from a normal
single-protein run rather than requiring the Phase 3 benchmark directory layout.

The adapter must:

- accept ordinary Phase 1/2 outputs;
- include at most five sequence and five structure records;
- preserve raw and normalized metrics, target identity, mappings, tool/database versions,
  and predicted-versus-experimental structure status;
- keep sequence and structure topics separate;
- exclude gold labels and never manufacture missing annotations.

## Milestone 4 — Human-readable summary (initial version implemented)

Always generate `summary.md`, even when Ollama is disabled. It should contain:

1. input identity and checksum;
2. run completion and warnings;
3. top sequence-supported functions;
4. top structure-supported functions;
5. cross-modal interpretation;
6. alternatives and conflicts;
7. literature availability and citations;
8. final decision: putative function, `ABSTAIN`, or `INSUFFICIENT_EVIDENCE`;
9. confidence status and scientific limitations;
10. paths to full auditable artifacts.

The deterministic summary must not depend on the LLM. Ollama may add a separately
labelled narrative only after evidence-packet and citation verification.

## Milestone 5 — Progress and error messages

Use plain-language progress:

```text
[1/6] Input validated: P69905, 142 aa
[2/6] Sequence retrieval complete: 10 hits
[3/6] Structure model acquired and verified
[4/6] Foldseek complete: 10 hits
[5/6] Cross-modal state: CONSENSUS
[6/6] Local literature complete: 8 passages
Result: putative function; confidence NOT_CALIBRATED
```

Errors should state the consequence and next action, for example:

```text
AlphaFold model unavailable. Sequence analysis completed; structure evidence is absent.
```

Do not expose raw tracebacks by default. Preserve them in a log for debugging.

## Milestone 6 — Optional local graphical interface

Only after the CLI contract is stable, add a local UI that calls the same orchestrator.
The first screen needs:

- FASTA upload or UniProt accession field;
- analysis name and output location;
- local/online/no-literature selection;
- optional Ollama report checkbox;
- preflight status;
- run/resume button.

The result page should use separate tabs for Summary, Sequence, Structure, Agreement,
Literature, Alternatives/Conflicts, Provenance, and Downloads. It must display
`ABSTAIN`, missing modalities, predicted structures, and `NOT_CALIBRATED` prominently.

Do not add authentication, cloud deployment, multi-user queues, or a large web framework
until a local single-user UI is proven necessary.

## Acceptance tests

The interface is ready for ordinary users only when all of these pass:

- FASTA and UniProt inputs produce the same checksum and biological evidence for the
  same canonical protein;
- invalid accessions and malformed FASTA fail before database work;
- repeated runs are equivalent;
- unavailable AlphaFold models complete as sequence-only;
- local literature works without network access;
- online literature requires email and preserves raw responses without recording keys;
- report claims reference valid evidence IDs and citations;
- no benchmark gold labels enter an ordinary analysis;
- interruption followed by `--resume` does not duplicate or overwrite artifacts;
- one novice can complete a run using only `docs/USER_MANUAL.md`.

## Recommended implementation order

1. Unified input resolver and tests. **Complete**
2. `dualrag analyze` orchestration with Phase 1-2 only. **Complete**
3. Initial deterministic `summary.md` and `status.json`. **Complete**
4. Local literature-index option. **Next**
5. New-protein Phase 5 evidence-packet adapter.
6. Optional online PubMed/PMC and Ollama switches.
7. Repeated novice usability test.
8. Local graphical interface only if the CLI remains a practical barrier.

This plan improves usability without changing scientific thresholds or claiming that the
current Phase 4 or Phase 6 gates passed.
