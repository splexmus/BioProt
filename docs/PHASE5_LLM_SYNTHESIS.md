# Phase 5 grounded LLM synthesis

Phase 5 converts compact evidence packets into structured, evidence-linked research
hypotheses. It does not experimentally confirm protein function and does not generate
calibrated confidence. Phase 6 owns confidence calibration.

## Current entry-gate exception

The normal entry gate is a Phase 4 `PASS`. Development may explicitly use
`--allow-unvalidated-phase4`; outputs then record
`EXPERIMENTAL_UNVALIDATED_PHASE4_OVERRIDE`. Under this override, `UNASSESSED`
literature is retrieved context only and cannot become direct support or contradiction.

## Flow

```text
EvidencePacket -> bounded GenerationContext -> Ollama structured JSON
               -> deterministic verifier -> JSON + Markdown report
```

The contract is `config/generation-contract-v1.yaml`. Prompt templates are versioned in
`prompts/`. Raw Ollama responses, contexts, parsed reports, verification findings, and
checksummed manifests are preserved for each run.

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
scripts/run_phase5_ollama.sh smoke \
  --phase4-run phase4-exit-development-v4 \
  --query-id P01040
```

## Full experimental run

```bash
scripts/run_phase5_ollama.sh run \
  --phase4-run phase4-exit-development-v4 \
  --run-name phase5-ollama-development-v1
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
