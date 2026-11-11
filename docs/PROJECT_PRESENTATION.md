---
marp: true
title: BioProt — Dual-Retrieval RAG for Protein Function Research
description: Current project architecture, phases, pipeline, results, and scientific status
paginate: true
---

# BioProt

## Dual-Retrieval RAG for Protein Function Research

**Current project presentation**  
Status date: **11 November 2026**

> An auditable research instrument for generating protein-function hypotheses—not experimental confirmation.

---

# Research problem and objective

## Problem

- Sequence similarity can miss remote relationships.
- Structure similarity can recover shared folds but may not establish exact function.
- Database annotations may be incomplete, broad, or contradictory.
- LLMs can overstate evidence unless claims remain linked to sources.

## Objective

Combine **independent sequence, structure, and literature evidence** while preserving:

- provenance and raw measurements;
- agreement, conflict, and missing evidence;
- alternative hypotheses and uncertainty;
- reproducible evaluation before report generation.

---

# System architecture

```text
FASTA / UniProt accession
          │
          ▼
     Query resolver
       ┌──┴────────────┐
       ▼               ▼
Sequence retrieval  Structure retrieval
eggNOG / MMseqs2    AlphaFold DB → Foldseek
       │               │
       └── separate normalization ──┘
                       ▼
        Function candidates + mappings
                       ▼
       Cross-modal comparison and ranking
                       ▼
        Literature retrieval (optional)
                       ▼
       Evidence packet → local LLM report
                       ▼
       Verification, abstention, calibration
```

**Trust boundary:** retrieval scores are ranking features, not probabilities or experimental proof.

---

# End-to-end analysis pipeline

1. Validate FASTA or resolve a UniProt accession.
2. Run the sequence and structure branches independently.
3. Preserve raw outputs; normalize each modality separately.
4. Build EC, GO-MF, InterPro, Pfam, SUPFAM, ortholog-group, and label candidates.
5. Classify `CONSENSUS`, `PARTIAL_CONSENSUS`, modality-only evidence, `CONFLICT`, or insufficient evidence.
6. Apply quality gates, mappings, deterministic ranking, alternatives, and audit output.
7. Optionally retrieve PubMed/PMC passages into a separate `R_lit` channel.
8. Build a bounded evidence packet and optional grounded local-LLM report.
9. Emit a prediction or `ABSTAIN`; attach calibrated confidence only after a scientific gate passes.

---

# Phase 0 — Repository and environment

## Status: Engineering complete

- Python 3.11 environment managed and locked with Pixi.
- Configurable storage for large external databases.
- CLI skeleton, logging, version capture, fixtures, and checksums.
- External tool availability and versions are detected explicitly.
- Offline fixture runs remain available without biological databases.

## Result

The software environment and validation commands are reproducible. Synthetic fixtures test engineering behavior only and cannot support biological claims.

---

# Phase 1 — Biological dual retrieval

## Sequence channel

- Local eggNOG-mapper and MMseqs2 retrieval.
- Raw and normalized sequence evidence retained.

## Structure channel

- On-demand AlphaFold DB query-model acquisition and cache.
- Local Foldseek search against a PDB-derived database.
- SIFTS/UniProt metadata enrichment with predicted and experimental structures distinguished.

## Result

- Five-protein characterized integration completed.
- Five sequence results; four compatible AlphaFold models; one explicit `NOT_FOUND`.
- Forty Foldseek hits; repeat runs produced equivalent stable artifacts.

---

# Phase 2 — Function-level fusion

## Status: Engineering complete

- Groups heterogeneous hits into controlled function candidates.
- Supports versioned mappings and curated synonyms.
- Keeps exact, broader, narrower, and related relations distinct.
- Preserves six cross-modal states, conflicts, alternatives, and near ties.
- `quality-gated-v2` deduplicates biological sources, caps support bonuses, and downweights weak structure transfer using coverage and TM-score.

## Result

Fusion is deterministic and auditable. Its score ranks hypotheses but is **not calibrated confidence**.

---

# Phase 3 — Benchmarking

## Design

- Reviewed, experimentally supported Tier-A EC/GO-MF labels.
- Cluster-aware leakage control and prohibited-target manifests.
- B2 sequence-only, B3 structure-only, and B4 dual baselines.
- Function Recall@10, precision, MRR, nDCG, coverage, rescue, and bootstrap intervals.

## Development-pilot result

| Baseline | Function Recall@10 |
|---|---:|
| Sequence only | 0.722 |
| Structure only | 0.250 |
| Dual retrieval | 0.778 |

Dual minus sequence: **+0.0556**, 95% CI **0.0000–0.1667** → `NO_MEASURABLE_OVERALL_BENEFIT`.

---

# Phase 4 — Literature RAG

## Status: Engineering complete; scientific exit failed

- PubMed metadata/abstract and eligible PMC Open Access retrieval.
- PMID/PMCID/DOI deduplication and section-aware chunking.
- BM25, character-vector, hybrid retrieval, deterministic reranking, and SQLite index.
- Evidence roles: support, contradiction, background, irrelevant, or unassessed.

## Labelled evaluation

- 20 proteins and 1,569 manually reviewed passages.
- Contradiction Recall@10: **0.667** — passed.
- Recall@10: **0.462**; citation precision: **0.539**.
- Entity correctness: **0.326**; organism correctness: **0.368**.

The literature layer may support development, but it is not scientifically validated.

---

# Phase 5 — Grounded LLM synthesis

## Status: Development pass only

- Bounded structured context rather than raw database dumps.
- Separate sequence, structure, literature, conflict, and alternative sections.
- Local Ollama generation with raw-response preservation.
- Deterministic evidence-link, identifier, citation, and overclaim checks.
- Confidence remains `NOT_CALIBRATED`.

## Human review of 20 reports

- **16 accept**, 2 revise, 2 reject.
- 14 useful, 3 partly useful, 3 not useful.
- No unsupported claims were recorded.

The assessment was not blinded; expert baseline comparison remains pending.

---

# Phase 6 — Ranking, abstention, and calibration

## Current result

- Sequence-anchored ranking prevents weak structural evidence from displacing a stronger sequence top-1.
- Evidence sufficiency emits a prediction or explicit `ABSTAIN`.
- A third independent 300-protein cohort showed:
  - dual Recall@10 **0.6004** versus sequence-only **0.5578**;
  - gain **+0.0426**, 95% CI **0.0257–0.0619**.

## Calibration gate: Failed

- Accepted coverage: **80.5%**.
- Brier: **0.2392** (required ≤0.22).
- Log-loss: **0.6698** (required ≤0.65).
- ECE: **0.0807** (passed ≤0.10).
- Only one HIGH and zero LOW cases.

Test labels remain sealed; production confidence is not authorized.

---

# Phase 7 — Optional GraphRAG

## Status: Not started; conditional research option

Proposed graph entities:

- proteins and sequences;
- structures and domains;
- EC/GO functions and pathways;
- publications and evidence links.

## Decision rule

Prototype with NetworkX first. Introduce a graph database only if an ablation demonstrates measurable improvement in grounding, contradiction handling, or expert usefulness over the simpler pipeline.

---

# Phase 8 — Uncharacterized-protein study

## Status: Not authorized yet

Planned work:

- select biologically relevant unknown proteins;
- generate putative functions with full evidence trails;
- expose alternatives, conflicts, and abstentions;
- obtain expert review;
- prioritize experimental follow-up.

## Entry condition

Begin only after retrieval, literature quality, report grounding, and confidence calibration are frozen and scientifically validated.

---

# Results summary

| Component | Engineering status | Scientific status |
|---|---|---|
| Sequence retrieval | Complete | Strongest exact-function anchor |
| Structure retrieval | Complete | Adds coverage; benefit varies by cohort |
| Dual ranking | Complete | Positive latest cohort; replication still needed |
| Literature RAG | Complete | Frozen scientific exit failed |
| LLM reports | Complete for development | Blinded expert comparison pending |
| Abstention | Complete | Useful risk-control signal |
| Confidence calibration | Complete | Scientific gate failed |
| GraphRAG | Not started | Must earn inclusion by ablation |
| Unknown-protein study | Not started | Blocked by upstream gates |

---

# Discussion

## What worked

- Independent, provenance-rich sequence and structure evidence.
- Reproducible contracts, manifests, checksums, exclusions, and error analysis.
- Explicit conflict and abstention instead of forced predictions.
- A recent independent cohort supports improved top-10 dual recall.

## Remaining weaknesses

- Structure improves recall but can reduce precision.
- Literature retrieval often mismatches protein entity or organism.
- LLM evaluation is development-only and not blinded.
- Calibration lacks reliable LOW/HIGH groups and fails frozen limits.

**Interpretation:** the system is a useful exploratory research instrument, not a validated annotation service.

---

# Next steps

1. Freeze the latest ranking profile without tuning on the evaluated cohort.
2. Validate it once on another independent, cluster-controlled dataset.
3. Improve literature entity/organism matching and evaluate on a new labelled set.
4. Conduct blinded expert comparison of LLM reports against deterministic baselines.
5. Improve calibration while preserving abstention and sealed-test discipline.
6. Evaluate GraphRAG only after a non-graph baseline is frozen.
7. Start Phase 8 only after the scientific gates pass.

---

# Key references and project evidence

## Research methods

- Cantalapiedra et al. (2021), eggNOG-mapper v2 — DOI `10.1093/molbev/msab293`
- Steinegger & Söding (2017), MMseqs2 — DOI `10.1038/nbt.3988`
- Varadi et al. (2022), AlphaFold DB — DOI `10.1093/nar/gkab1061`
- van Kempen et al. (2024), Foldseek — DOI `10.1038/s41587-023-01773-0`
- Mathai & Schulze (2026), ProtPen — DOI `10.1021/acs.jproteome.6c00074`

## Project reports

- `docs/PHASE3_REPORT.md`
- `docs/PHASE4_EXIT_BENCHMARK.md`
- `docs/PHASE5_HUMAN_REVIEW.md`
- `docs/PHASE6_RANKING_SUFFICIENCY_RESULTS.md`
- `docs/SCIENTIFIC_STATUS_REPORT.md`

---

# Final message

## BioProt currently demonstrates:

- a working and reproducible multi-evidence research platform;
- transparent handling of uncertainty, conflict, and abstention;
- promising but cohort-dependent dual-retrieval improvement;
- grounded draft reports suitable for expert review.

## It does not yet demonstrate:

- experimental confirmation of predicted functions;
- consistently superior dual retrieval across cohorts;
- scientifically validated literature retrieval;
- production-ready calibrated confidence.

**All outputs remain putative, evidence-linked hypotheses.**
