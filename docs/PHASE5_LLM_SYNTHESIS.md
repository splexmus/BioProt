# Phase 5 grounded LLM synthesis

Phase 5 converts compact evidence packets into structured, evidence-linked research
hypotheses. It does not experimentally confirm protein function and does not generate
calibrated confidence. Phase 6 owns confidence calibration.

## Current development entry status

The normal entry gate is a Phase 4 `PASS`. Development may explicitly use
`--allow-unvalidated-phase4`; outputs then record
`EXPERIMENTAL_UNVALIDATED_PHASE4_OVERRIDE`. Under this override, `UNASSESSED`
literature is retrieved context only and cannot become direct support or contradiction.
The v4 Phase 4 run separately records `PASS_FOR_PHASE5_DEVELOPMENT`, which authorizes
this engineering work without changing its scientific exit status of `FAIL`. Keep the
override until the frozen Phase 4 scientific thresholds pass. New Phase 5 generation
manifests copy this transition status as `phase4_development_transition_status`.

## Flow

```text
EvidencePacket -> bounded GenerationContext -> Ollama structured JSON
               -> deterministic verifier -> JSON + Markdown report
```

The original report contract is `config/generation-contract-v1.yaml`. Phase 5.1 uses
`config/generation-contract-v2.yaml`, context v2, and the v2 prompt templates to expose
bounded sequence and structure records separately. Raw Ollama responses, contexts,
parsed reports, verification findings, and checksummed manifests are preserved for each
run. Prompt v3 and Markdown renderer v2 require and display distinct sequence and
structure support topics. See `docs/PHASE5_BIOLOGICAL_EVIDENCE.md`.

## Ollama setup

Start Ollama in another terminal if it is not already managed as a service:

```bash
ollama serve
```

Initialize the default local model:

```bash
pixi run python -m dualrag init-ollama --model gemma3:4b
```

The model download is stored by Ollama, not inside the repository or Pixi environment.

## One-query experimental smoke run

```bash
scripts/enrich_phase5_biological_evidence.sh
scripts/run_phase5_ollama.sh smoke \
  --phase4-run phase4-exit-development-v4 \
  --run-name phase5-ollama-biological-v1 \
  --query-id P01040
```

## Full experimental run

```bash
scripts/run_phase5_ollama.sh run \
  --phase4-run phase4-exit-development-v4 \
  --run-name phase5-ollama-biological-v1
```

Remove `--allow-unvalidated-phase4` from the underlying command after Phase 4 passes.

## Verification boundary

The deterministic verifier checks evidence identifiers, reference metadata, controlled
identifiers, use of unassessed literature, and common overclaim language. It cannot
establish whether an arbitrary natural-language interpretation is biologically true.
Human expert evaluation remains required for the Phase 5 exit criterion.

The LLM does not control evidence roles. After structured generation, the adapter
deterministically assigns claim inference levels from cited record types and inserts the
candidate-grounded computational function claim when needed. The unchanged raw Ollama
response is retained so this normalization remains auditable.
