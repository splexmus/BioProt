# Dual-Retrieval RAG for Protein Function Research

This repository currently contains a **Phase 1 proof of concept**: FASTA input is
resolved into two independent evidence channels, normalized separately, and merged
without collapsing sequence and structure evidence into one score.

The default `fixture` backend requires no biological databases, downloads, or network
access. Its records are synthetic and exist only to exercise schemas, provenance,
agreement states, and reproducibility. It does **not** predict the supplied sequence's
real function.

## Quick start (no external data)

```bash
PYTHONPATH=src conda run -n bioinfo python -m dualrag run \
  --config config/config.yaml \
  --input tests/fixtures/queries.fasta \
  --output results/poc
```

The output directory contains raw channel outputs, `sequence_results.tsv`,
`structure_results.tsv`, `merged_results.tsv`, a query manifest, a config snapshot,
run metadata, and a command log.

Validation:

```bash
PYTHONPATH=src conda run -n bioinfo python -m dualrag check-tools
conda run -n bioinfo pytest -q
conda run -n bioinfo ruff check src tests
```

`check-tools` is diagnostic: missing executables are reported, but fixture mode remains
fully usable. The planned production boundary uses local eggNOG and Foldseek databases
plus on-demand AlphaFold DB REST retrieval. It remains gated until the adapters and
verified database-version manifests are configured.

## Scientific boundaries

- Fixture annotations are synthetic test data, never biological evidence.
- Scores are deterministic PoC normalization features, not calibrated confidence.
- `CONFLICT` is retained as evidence; it is never averaged away.
- Missing metrics are blank TSV cells and explicit `None` values internally.
- No LLM or literature layer is present in this milestone.

See `ARCHITECTURE.md`, `DATA.md`, and `docs/POC.md` for contracts and extension points.
