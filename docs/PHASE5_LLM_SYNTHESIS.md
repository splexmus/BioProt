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
pixi run python -m dualrag init-ollama --model gemma4:more
```

The model download is stored by Ollama, not inside the repository or Pixi environment.
`gemma4:more` is the default for new runs. The completed 20-report human review applies
only to the preserved `gemma3:4b` run; a Gemma 4 run is a new system variant and must
receive its own smoke test, full-run manifest, and human review before it is frozen.
The runner uses a 1,800-second request timeout because the larger model can exceed the old
300-second limit during report generation; override it with `--timeout SECONDS` when
appropriate.
The local `gemma4:more` Modelfile requests up to 16,384 output tokens. BioProt caps each
report request at 8,192 with Ollama's `num_predict` option so a malformed or non-terminating
structured response cannot consume that entire budget. Override the cap explicitly with
`--max-output-tokens N`; changing it creates a new generation configuration.
BioProt also sends `think: false`. Hidden reasoning from this custom model consumed the
entire output budget without emitting `message.content`; report generation requires the
auditable schema-bounded final answer, not an unrecorded reasoning stream.
Generation pipeline v5 records `think` and `num_predict` in every query record, the run
manifest, and the parameters hash because changing either setting creates a distinct
model configuration.

### Gemma 4 compatibility status

`gemma4:more` is installed and selected for new experimental runs, but it is not frozen.
The original thinking-enabled requests timed out at both 300 and 900 seconds. With
`think: false`, one 4,096-token smoke generated a valid report, while later 4,096- and
8,192-token repetitions produced truncated JSON after consuming their full budgets.
Do not start the 20-report run until a small repeated-query pilot establishes an
acceptable completion rate. Pipeline v5 preserves the raw Ollama response even when
schema validation fails so truncation and repetition remain auditable.

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
