# Pipeline v2: quality-gated function retrieval

`quality-gated-v2` improves the ranking stage without hiding or deleting raw sequence
or structure evidence. It is the production profile in `config/4tb-hdd.yaml`. The
original `fixed-weight-v1` remains available through configs that do not enable the new
options and as the frozen Phase 3 baseline.

## Why this change was needed

The v1 scorer used only the best score per modality. Consequently, three independent
proteins supporting a function counted the same as one hit, repeated PDB assemblies
could look like independent support, and a high Foldseek score with weak query/target
coverage could transfer a function too strongly. Increasing the target pool also
introduced unsupported low-rank annotations.

V2 addresses those ranking failures. It does not change the underlying MMseqs2,
eggNOG, AlphaFold, or Foldseek algorithms and it does not turn ranking scores into
biological confidence.

## Changes

### 1. Independent biological support aggregation

Contributions are deduplicated by biological source before counting support:

- sequence: UniProt source accession, falling back to the target ID;
- structure: SIFTS-resolved target UniProt accession, falling back to the structure ID.

For a function with `n` independent sources, the per-modality score is:

```text
maximum = best quality-adjusted hit score
support_fraction = min((n - 1) / (3 - 1), 1)
aggregated = maximum + (1 - maximum) * 0.15 * support_fraction
```

The bonus is deliberately capped. Repeated copies of one biological protein do not
increase `n`.

### 2. Structure-quality gate

Function transfer from a structure hit is multiplied by an explicit reliability term
derived from query coverage, target coverage, and TM-score. The production thresholds
are 0.50 for all three metrics:

```text
ratio_i = clamp(metric_i / threshold_i, 0, 1)
geometric_quality = (ratio_qcov * ratio_tcov * ratio_tm) ** (1 / 3)
reliability = 0.20 + 0.80 * geometric_quality
```

A missing metric is treated as a zero ratio. The 0.20 floor retains weak structural
evidence for inspection rather than erasing it. Raw normalized scores remain in
`structure_max_score`; the adjusted value is in `structure_score`. Quality flags stay
on candidate rows, and the number of gated contributions is recorded in the audit.

### 3. Sequence-favouring fusion weights

The v2 development profile uses:

```text
0.50 * sequence + 0.30 * quality-gated structure + 0.20 * agreement
```

The structure channel remains separately visible. This weighting reflects the current
pilot, in which sequence retrieval is more reliable than structure-only annotation
transfer. It is a validation-selected ranking profile, not a universal biological law.

### 4. Safe deeper retrieval

The benchmark runner can retain more than ten targets with `--target-pool-k`. Hits
ranked 1-10 are direct evidence. A function found only below rank 10 is retained only
when at least three independent biological sources support it, and its score and any
agreement bonus are multiplied by 0.50.

The production profile keeps `top_k: 10`. The 50-target profile is an experimental
recall mode because it produced more candidates and lower precision in this pilot.

### 5. Offline rescoring

`--reuse-raw-evidence` reads the preserved sequence, structure, exclusion, and
AlphaFold-acquisition TSVs and reruns mapping/fusion without Swiss-Prot, Foldseek, the
external drive, or public APIs. It fails closed if a required raw file is missing.

Example:

```bash
pixi run python scripts/run_phase3_benchmark.py \
  --dataset benchmark/phase3-pilot-v1 \
  --swissprot-dat /not-used-when-reusing-raw \
  --output benchmark/phase3-pipeline-v2-conservative \
  --tmp-dir /tmp/dualrag-v2 \
  --mapping-projections benchmark/phase3-mappings-v1/mapping_projections.tsv \
  --synonyms benchmark/phase3-mappings-v1/synonyms.tsv \
  --target-pool-k 10 \
  --quality-gated-fusion \
  --reuse-raw-evidence
```

### 6. Additional audit columns

`function_candidates.tsv` and benchmark `ablation_candidates.tsv` now expose:

- best raw sequence and structure scores;
- quality-adjusted modality scores;
- maximum structure reliability and gated-evidence count;
- explicit structure-quality flags;
- best source rank for each modality;
- agreement reliability;
- counts of deduplicated biological sources.

The audit records all thresholds, support parameters, deep-filter counts, and gated
contribution counts.

## Foldseek function metadata

Foldseek similarity alone has no GO/EC function labels. The target metadata must use
the current schema, including `go_terms` and `ec_numbers`. Rebuild it from the frozen
SIFTS/Swiss-Prot inputs when the external drive is mounted:

```bash
pixi run python -m dualrag.structure.metadata \
  --data-root /media/splexmus/4TB_HDD1/dualrag \
  --output /media/splexmus/4TB_HDD1/dualrag/databases/foldseek/pdb_metadata.tsv \
  --work-dir /tmp
```

The builder writes through a temporary file, atomically replaces the output, and writes
a checksummed manifest with GO, EC, InterPro, name, and UniProt coverage counts. The
drive was not mounted while v2 was finalized, so this repository change does not claim
that the external file was rebuilt in this session.

## Benchmark result

The conservative profile rescored the same preserved, leakage-filtered evidence as v1.

| Split | Profile | B4 FR@5 | B4 FR@10 | P@10 | MRR |
|---|---|---:|---:|---:|---:|
| Development (42) | v1 | 0.507 | 0.557 | 0.202 | 0.512 |
| Development (42) | v2 | 0.528 | 0.575 | 0.204 | 0.517 |
| Validation (9) | v1 | 0.796 | 0.796 | 0.328 | 0.685 |
| Validation (9) | v2 | 0.796 | 0.796 | 0.328 | 0.685 |
| Test (9; previously exposed) | v1 | 0.750 | 0.778 | 0.340 | 0.583 |
| Test (9; previously exposed) | v2 | 0.750 | 0.778 | 0.340 | 0.583 |

Validation nDCG@10 changed from 0.6846 to 0.6831. Test nDCG@10 was unchanged at
0.6157. Development and validation behavior selected the conservative v2 profile. The
test split had already been exposed by the v1 report, so its unchanged result is a
regression check, not fresh confirmatory evidence.

The scientific conclusion remains `NO_MEASURABLE_OVERALL_BENEFIT`: the test set has
only nine proteins, and v2 did not improve the held-out B4 result over v1 or establish
that dual retrieval beats sequence-only retrieval. Detailed machine-readable
comparisons are in
`benchmark/phase3-pipeline-v2-conservative/comparison/profile_comparison.tsv`.

## Interpretation

V2 improves evidence accounting and development-set ranking. It is not experimental
validation of a protein function, not calibrated confidence, and not proof of a general
dual-retrieval advantage. A larger preregistered benchmark, especially in the <=30%
identity strata, is still required.
