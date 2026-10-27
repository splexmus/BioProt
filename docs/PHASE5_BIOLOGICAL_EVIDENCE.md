# Phase 5.1 bounded biological evidence

Phase 5.1 enriches each compact evidence packet with the actual top retrieval records
that produced the upstream candidates. Sequence and structure remain separate so an LLM
cannot hide a cross-modal conflict behind a combined score.

For the current Phase 3 benchmark, the sequence records are leakage-filtered MMseqs2
hits against frozen Swiss-Prot. They are not eggNOG-mapper hits: Phase 3 deliberately
used MMseqs2 because it exposes a ranked target list that can be filtered for prohibited
homologs. The structure records are leakage-filtered Foldseek matches against the local
PDB/SIFTS-backed target database.

Each query receives at most five records per modality. Sequence records retain target,
identity, coverage, E-value, bitscore, annotations, normalization, tool, database and
version. Structure records retain the Foldseek target, mapped UniProt/PDB identifiers,
E-value, score, TM-score, alignment and coverage metrics, annotations, structure source,
and whether the target structure is experimental. Missing fields remain absent.

The records are computational evidence. A Foldseek match is not automatically a homolog
or an exact-function match, transferred annotations are not experimental confirmation,
and normalized scores are ranking values rather than probabilities. No benchmark gold
labels are read by the enrichment command.

Create the enriched v4 packets on the external drive:

```bash
scripts/enrich_phase5_biological_evidence.sh
```

This writes:

```text
evidence_packets.biological-v1.jsonl
evidence_packets.biological-v1.manifest.json
```

`scripts/run_phase5_ollama.sh` automatically prefers the enriched packet file when it
exists. Use `--packets FILE` to select a packet artifact explicitly.

## Report presentation

Markdown renderer v2 presents biological retrieval in dedicated sections:

- `Sequence retrieval support` lists MMseqs2 targets, identity, coverage, E-value,
  bitscore, annotations, ranking score, and provenance.
- `Structure retrieval support` lists Foldseek targets, TM-score, query/target coverage,
  Foldseek scores, annotations, structure source, experimental status, and provenance.
- `Cross-modal interpretation` preserves the upstream agreement/conflict state and
  claims that explicitly combine both modalities.

Prompt v3 requests a separate evidence-linked claim for every available modality. The
deterministic verifier warns when sequence or structure records exist but the generated
report does not discuss that modality. Raw retrieval sections are still rendered even
when the model omits a narrative claim. Generation adapter v4 also inserts a conservative
top-hit interpretation for an omitted modality; the preserved raw Ollama response makes
this system-added text distinguishable and auditable.
