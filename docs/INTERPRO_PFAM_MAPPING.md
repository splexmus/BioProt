# Full InterPro/Pfam mapping bundle

BioProt can build a release-pinned Pfam-to-InterPro exact-mapping bundle without
installing the full InterProScan distribution:

```bash
pixi run python scripts/build_interpro_pfam_mapping_bundle.py \
  --output /media/splexmus/4TB_HDD1/dualrag/databases/metadata/interpro111-pfam39-mapping-v1
```

The builder downloads the official InterPro 111.0 XML/release notes and Pfam 39.0 clan
table from immutable release directories; records URLs, sizes, SHA-256 digests;
and emits both Pfam-accession and Pfam-short-name mappings. It refuses to overwrite a
non-empty directory and downloads through temporary `.part` files.

The bundle generated on 2026-11-08 resolved InterPro 111.0 and Pfam 39.0, with 47,143
integrated Pfam accessions and 94,286 exact accession/name mapping rows. `EXACT` means
that the Pfam signature is integrated into the InterPro entry. It does not mean that a
shared domain establishes complete-protein function.

`config/4tb-hdd-interpro111-weights-v1.yaml` is the editable experimental profile. Its
current values are `0.55` sequence, `0.20` structure, and `0.25` agreement, followed by
`0.75` base-score and `0.25` evidence-quality reranking. This is an ablation profile,
not a replacement for the frozen benchmark configuration. Any selected profile requires
new calibration.

## Development rerun

The requested combined mapping/weight profile was rescored on preserved evidence for
the 552-protein development split. It was not evaluated on sealed test labels.

| Metric | Previous dual | New dual | Difference |
| --- | ---: | ---: | ---: |
| Function Recall@1 | 0.3747 | 0.3742 | -0.0005 |
| Function Recall@5 | 0.7052 | 0.6942 | -0.0110 |
| Function Recall@10 | 0.8090 | 0.8049 | -0.0040 |
| Precision@10 | 0.3363 | 0.3354 | -0.0010 |
| MRR | 0.7551 | 0.7530 | -0.0022 |
| nDCG@10 | 0.7140 | 0.7104 | -0.0036 |

The new dual-minus-sequence Recall@10 estimate remained positive at 0.0511, with a
95% bootstrap interval of 0.0352 to 0.0681. InterPro Recall@10 was 0.9317 and Pfam
Recall@10 was 0.9822 after making domain evaluation alias-aware. The requested weights
therefore remain an experimental ablation: they did not improve the previous development
profile and must not replace the frozen scientific configuration.

The 2026-11-08 run was generated under `/tmp` because `/media/splexmus/4TB_HDD1` was
mounted read-only. Re-run the documented build command after the filesystem is safely
mounted read-write, then use the versioned configuration.

The development rescore used preserved raw evidence and these additional runner flags:

```text
--fusion-mappings <bundle>/mappings.tsv
--sequence-weight 0.4 --structure-weight 0.3 --agreement-weight 0.3
--base-score-weight 0.7 --quality-weight 0.3
--fusion-version quality-gated-v3-interpro111-weights0433
--rerank-version support-aggregated-v3-quality073
```

The runner records mapping/projection checksums, effective weights, and both version
labels in `retrieval_summary.json`.

The same settings can be loaded directly by the benchmark runner with:

```text
--config config/4tb-hdd-interpro111-weights-v1.yaml
```

Explicit benchmark flags still override values loaded from the configuration.

## Current config-driven rerun

On 2026-11-08, the current YAML profile (`0.55/0.20/0.25` fusion and `0.75/0.25`
reranking) was applied to the preserved development evidence using `--config` directly.

| Metric | Previous dual | Config-driven dual | Difference |
| --- | ---: | ---: | ---: |
| Function Recall@1 | 0.3747 | 0.3792 | +0.0045 |
| Function Recall@5 | 0.7052 | 0.7065 | +0.0013 |
| Function Recall@10 | 0.8090 | 0.8077 | -0.0013 |
| Precision@10 | 0.3363 | 0.3364 | +0.0001 |
| MRR | 0.7551 | 0.7590 | +0.0039 |
| nDCG@10 | 0.7140 | 0.7169 | +0.0029 |

Dual-minus-sequence Recall@10 was `0.0528` with a 95% bootstrap interval of
`0.0372-0.0696`. This remains exposed development evidence, not a validation result.

### Reproduce by rescoring preserved evidence

The HDD must be mounted read-write. Choose a new output directory to avoid overwriting
an existing scientific run:

```bash
RUN=/media/splexmus/4TB_HDD1/dualrag/benchmarks/runs/step6-interpro111-config-development-v3
SOURCE=/media/splexmus/4TB_HDD1/dualrag/benchmarks/runs/step6-devval-retrieval-v2-development-fix

mkdir -p "$RUN/raw"
cp "$SOURCE/raw/sequence_evidence.tsv" \
   "$SOURCE/raw/structure_evidence.tsv" \
   "$SOURCE/raw/alphafold_acquisition.tsv" \
   "$SOURCE/raw/structure_exclusions.tsv" \
   "$RUN/raw/"

pixi run python scripts/run_phase3_benchmark.py \
  --config config/4tb-hdd-interpro111-weights-v1.yaml \
  --dataset /media/splexmus/4TB_HDD1/dualrag/benchmarks/step3-merged-reviewed-v1-pipeline \
  --swissprot-dat /media/splexmus/4TB_HDD1/dualrag/databases/uniprot/swissprot/current/uniprot_sprot.dat.gz \
  --output "$RUN" \
  --mapping-projections benchmark/phase3-mappings-v2/mapping_projections.tsv \
  --reuse-raw-evidence \
  --target-pool-k 100
```

Evaluate only the development split:

```bash
pixi run python scripts/evaluate_phase3.py \
  --dataset /media/splexmus/4TB_HDD1/dualrag/benchmarks/step3-merged-reviewed-v1-pipeline \
  --run "$RUN" \
  --output "$RUN/evaluation-development" \
  --go-obo benchmark/phase3-mappings-v1/sources/go-basic.obo \
  --go-ic benchmark/phase3-mappings-v1/go_mf_information_content.tsv \
  --evaluation-split development
```

Do not change `--evaluation-split` to `test`; the sealed test remains prohibited.
