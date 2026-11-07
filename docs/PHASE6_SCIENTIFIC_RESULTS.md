# Phase 6 scientific validation result

Run date: 2026-11-07  
Status: `FAIL_SCIENTIFIC_CALIBRATION_GATE`  
Test gold accessed: no

## Scope

The run used the development/validation-only view of `step3-merged-reviewed-v1`:

- 552 development proteins;
- 118 validation proteins;
- 670 total queries;
- zero test queries or test-gold rows.

The sealed test-label vault was not opened. Because validation selected no acceptable
calibrator, the one-time Step 7 test evaluation is not permitted.

## Retrieval result

The frozen `quality-gated-v2` run produced:

| Item | Result |
|---|---:|
| AlphaFold models | 666 usable; 4 unavailable |
| Acquisition provenance | 313 cached; 353 downloaded; 4 not found |
| Allowed sequence hits | 17,679 |
| Allowed structure hits | 31,718 |
| Excluded structure hits | 7,576 |
| Principal predictions | 13,982 |

Sequence and structure evidence remain separate in the raw output. Exclusions include
prohibited homologs and PDB chains without usable UniProt/SIFTS identity.

## Sequence versus structure

On the 118-protein validation split, B2 sequence-only and B4 deterministic dual
retrieval had identical EC/GO-MF metrics:

| Metric | Sequence-only | Dual |
|---|---:|---:|
| Function Recall@1 | 0.3071 | 0.3071 |
| Function Recall@5 | 0.6145 | 0.6145 |
| Function Recall@10 | 0.6864 | 0.6864 |
| Precision@1 | 0.6102 | 0.6102 |
| MRR | 0.7047 | 0.7047 |
| nDCG@10 | 0.6490 | 0.6490 |

The paired dual-minus-sequence Recall@10 estimate is 0.0 with a 95% bootstrap interval
of 0.0 to 0.0. All evaluated top-1 EC/GO-MF predictions remained sequence-only, so the
calibration inputs were byte-identical between the sequence and dual runs.

Structure was still useful for domain evidence:

| Domain metric | Sequence-only | Structure-only | Dual |
|---|---:|---:|---:|
| InterPro exact Recall@10 | 0.8717 | 0.7979 | 0.9236 |
| Pfam exact Recall@10 | 0.9300 | 0.0000 | 0.9300 |

Therefore the current structure channel adds InterPro coverage, but the present
PDB/SIFTS metadata and mapping path do not convert that evidence into EC/GO-MF rescue.

## Calibration result

The validation evaluation contained 155 query-namespace examples from 111 proteins with
90.6% candidate coverage, so the frozen minimum sample-size gate passed.

| Method | Brier | Log loss | ECE | Gate |
|---|---:|---:|---:|---|
| Raw ranking score | 0.2476 | 0.6886 | 0.1500 | baseline |
| Platt logistic | 0.2269 | 0.6467 | 0.0428 | fail |
| Isotonic regression | 0.2228 | 0.6309 | 0.0577 | fail |
| Multifeature L2 logistic | 0.2191 | 0.6281 | 0.0275 | fail |

Multifeature logistic met the aggregate metric limits but generated zero LOW and only 11
HIGH examples. The frozen contract requires at least 20 LOW, 20 MODERATE, and 30 HIGH
examples. Isotonic had 7 LOW and 9 HIGH; Platt had 2 LOW and no HIGH. No method passed
all checks, so no calibrator was selected or frozen.

## Artifacts

- Retrieval: `/media/splexmus/4TB_HDD1/dualrag/benchmarks/runs/step6-devval-retrieval-v1`
- Calibration: `/media/splexmus/4TB_HDD1/dualrag/calibration/runs/step6-devval-dual-v1`
- Retrieval evaluation:
  `/media/splexmus/4TB_HDD1/dualrag/benchmarks/evaluations/step6-devval-dual-v1`

## Next allowed work

Do not evaluate the sealed test set. Improve the structure-to-function path using only
development data, then rerun a newly frozen validation procedure. The first target is
to preserve the observed InterPro gain while mapping structure-derived domain evidence
to function only where the mapping is biologically defensible. The Gemma 4 Phase 5
report branch also remains separately blocked on reliability and review.

## Development repair after the frozen failure

On 2026-11-07, priorities 1-3 were repaired using development data only for the new
performance comparison:

1. normalized bare `IPR...` structure identifiers to `InterPro:IPR...` mapping keys;
2. built PDB metadata v2 with GO-MF, EC, InterPro, Pfam, SIFTS release provenance, and
   checksums;
3. separated direct target functions from domain-derived GO projections. Domain-derived
   candidates carry `DOMAIN_PROJECTION:INTERPRO2GO`, the
   `DOMAIN_DERIVED_FUNCTION` quality flag, and a 0.75 reliability cap.

Mapping bundle v2 also filters InterPro2GO and EC2GO targets through GO OBO, retaining
only non-root Molecular Function terms. It contains 18,610 projections rather than the
34,953 unfiltered v1 rows.

Development-only evaluation on 552 proteins produced:

| Metric | Sequence-only | Structure-only | Dual |
|---|---:|---:|---:|
| Function Recall@1 | 0.3769 | 0.2733 | 0.3747 |
| Function Recall@5 | 0.6768 | 0.5333 | 0.7052 |
| Function Recall@10 | 0.7549 | 0.6054 | 0.8090 |
| Precision@10 | 0.4806 | 0.3107 | 0.3363 |
| MRR | 0.7460 | 0.5954 | 0.7551 |
| Candidate coverage | 0.9601 | 0.9873 | 1.0000 |

The paired dual-minus-sequence Recall@10 improvement is 0.0541 with a 95% bootstrap
interval of 0.0379 to 0.0712. Structure rescued 25 development proteins; sequence
rescued 55. InterPro Recall@10 improved from 0.9024 to 0.9330 and Pfam from 0.9547 to
0.9816.

This repair restores measurable structure contribution, but the larger candidate pool
reduces precision and does not improve top-1 recall. These results are exploratory
development evidence. They do not retroactively pass the frozen validation gate.

### Priorities 4-5 prospective rerun

Priority 4 selected a ranking profile using only five cluster-aware development folds.
It adds a 0.04 bonus for direct structure-target evidence, subtracts 0.05 from
structure-only candidates, and retains at most two structure-only candidates per
namespace. Development dual Recall@10 was 0.7951 versus 0.7549 for sequence-only;
Precision@10 improved from the unbounded repaired dual result of 0.3363 to 0.3766.

Priority 5 selected multifeature L2 logistic calibration using development-only
cluster-aware cross-validation. The final model was fitted on 821 query-namespace
examples from 552 proteins. Before validation labels were read, the project froze the
ranked predictions, candidate evidence, ranking profile, calibrator, mappings, database
manifest, contract, Pixi lock, and the 96-file Python code tree.

The fresh validation cohort contains 150 reviewed proteins in clusters independent of
the previous 788-protein benchmark. Retrieval completed for every protein: 125 usable
AlphaFold models, 22 not found, and three sequence mismatches recorded as structure
unavailable. The latter no longer abort the sequence channel.

Frozen validation ranking results:

| Metric | Sequence-only | Frozen dual |
|---|---:|---:|
| Function Recall@1 | 0.3648 | 0.3426 |
| Function Recall@10 | 0.6047 | 0.6402 |
| Precision@10 | 0.3476 | 0.2486 |
| MRR | 0.5360 | 0.5125 |
| Candidate coverage | 0.8467 | 0.9200 |

The paired dual-minus-sequence Recall@10 improvement was 0.0356 with a 95% bootstrap
interval of 0.0117 to 0.0639. Thus structure improved top-10 function recall and
coverage on this cohort, while top-1 recall, MRR, and precision remained worse.

The frozen calibrator improved substantially over the raw score but failed the
predeclared scientific gate:

| Metric | Raw score | Frozen calibrator | Required maximum |
|---|---:|---:|---:|
| Brier score | 0.3738 | 0.2581 | 0.22 |
| Log loss | 1.3172 | 0.7089 | 0.65 |
| ECE | 0.3286 | 0.1661 | 0.10 |

The sample-size gate passed with 175 examples from 138 proteins and 92.6% coverage.
However, only 10 LOW and three HIGH predictions were produced, below the required 20
and 30. Status remains `FAIL_SCIENTIFIC_CALIBRATION_GATE`; the original sealed test
labels were not accessed and must remain sealed.

Repair artifacts:

- Mapping bundle: `benchmark/phase3-mappings-v2`
- PDB metadata:
  `/media/splexmus/4TB_HDD1/dualrag/databases/foldseek/pdb_metadata.v2.tsv`
- Development run:
  `/media/splexmus/4TB_HDD1/dualrag/benchmarks/runs/step6-devval-retrieval-v2-development-fix`
- Development evaluation:
  `/media/splexmus/4TB_HDD1/dualrag/benchmarks/evaluations/step6-development-v2-priority1-3`
- Frozen ranking:
  `/media/splexmus/4TB_HDD1/dualrag/benchmarks/ranking/phase6-fresh-validation-v1`
- Frozen validation:
  `/media/splexmus/4TB_HDD1/dualrag/calibration/runs/phase6-fresh-validation-v1`
