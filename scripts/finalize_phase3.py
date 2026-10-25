from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from dualrag import __version__
from dualrag.io import read_tsv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize the Phase 3 reproducibility package.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--mappings", type=Path, required=True)
    parser.add_argument("--pdb-metadata-manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return (result.stdout or result.stderr).strip()


def metric(rows: list[dict[str, str]], baseline: str, name: str) -> dict[str, str]:
    return next(row for row in rows if row["baseline"] == baseline and row["metric"] == name)


def main() -> None:
    args = parse_args()
    provenance = args.run / "provenance"
    provenance.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        args.pdb_metadata_manifest,
        provenance / "phase3-pdb-metadata.tsv.manifest.json",
    )
    shutil.copyfile(
        args.mappings / "manifest.json",
        provenance / "phase3-mapping-manifest.json",
    )
    shutil.copyfile(
        args.mappings / "go_ic_manifest.json",
        provenance / "phase3-go-ic-manifest.json",
    )
    shutil.copyfile(
        args.dataset / "source_manifest.json",
        provenance / "phase3-dataset-source-manifest.json",
    )
    repository_root = Path(__file__).parents[1]
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "phase": "3.1-3.9",
        "dataset_id": args.dataset.name,
        "contract_id": "phase3-benchmark-v1",
        "random_seed": 42,
        "git": {
            "commit": command_output(["git", "rev-parse", "HEAD"]),
            "status": command_output(["git", "status", "--short"]),
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "dualrag": __version__,
            "pixi_lock_sha256": sha256(repository_root / "pixi.lock"),
            "mmseqs2": command_output(["mmseqs", "version"]),
            "foldseek": command_output(["foldseek", "version"]),
        },
        "inputs": {
            "dataset_manifest_sha256": sha256(args.dataset / "source_manifest.json"),
            "mapping_manifest_sha256": sha256(args.mappings / "manifest.json"),
            "go_ic_manifest_sha256": sha256(args.mappings / "go_ic_manifest.json"),
            "pdb_metadata_manifest_sha256": sha256(args.pdb_metadata_manifest),
        },
        "commands": [
            "scripts/build_phase3_dataset.py",
            "scripts/build_phase3_mapping_resources.py",
            "python -m dualrag.structure.metadata",
            "scripts/run_phase3_benchmark.py",
            "scripts/evaluate_phase3.py",
            "scripts/finalize_phase3.py",
        ],
        "claim_scope": (
            "Development pilot only. The untouched test split has nine queries and is not "
            "a statistically powered release benchmark."
        ),
    }
    (args.run / "reproducibility_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    aggregate = read_tsv(args.run / "evaluation" / "aggregate_metrics.tsv")
    comparison = json.loads(
        (args.run / "evaluation" / "primary_comparison.json").read_text(encoding="utf-8")
    )
    cross = json.loads(
        (args.run / "evaluation" / "cross_modal_metrics.json").read_text(encoding="utf-8")
    )
    retrieval = json.loads((args.run / "retrieval_summary.json").read_text(encoding="utf-8"))
    b2 = metric(aggregate, "B2_SEQUENCE_ONLY", "function_recall_at_10")
    b3 = metric(aggregate, "B3_STRUCTURE_ONLY", "function_recall_at_10")
    b4 = metric(aggregate, "B4_DUAL_DETERMINISTIC", "function_recall_at_10")
    b2_interval = f"{float(b2['ci_lower']):.3f}-{float(b2['ci_upper']):.3f}"
    b3_interval = f"{float(b3['ci_lower']):.3f}-{float(b3['ci_upper']):.3f}"
    b4_interval = f"{float(b4['ci_lower']):.3f}-{float(b4['ci_upper']):.3f}"
    b2_coverage = metric(aggregate, "B2_SEQUENCE_ONLY", "candidate_coverage")
    b3_coverage = metric(aggregate, "B3_STRUCTURE_ONLY", "candidate_coverage")
    b4_coverage = metric(aggregate, "B4_DUAL_DETERMINISTIC", "candidate_coverage")
    report = f"""# Phase 3 scientific benchmark report

Run ID: `phase3-run-v1`  
Dataset: `phase3-pilot-v1`  
Contract: `phase3-benchmark-v1`  
Primary split: untouched test, 9 queries

## Result

| Baseline | FR@10 | 95% bootstrap interval |
|---|---:|---:|
| B2 sequence only | {float(b2['estimate']):.3f} | {b2_interval} |
| B3 structure only | {float(b3['estimate']):.3f} | {b3_interval} |
| B4 deterministic dual | {float(b4['estimate']):.3f} | {b4_interval} |

The paired B4-minus-B2 estimate is {float(comparison['estimate']):.4f}; its 95% interval
is {float(comparison['ci_lower']):.4f} to {float(comparison['ci_upper']):.4f}. Therefore
the contract conclusion is **{comparison['conclusion']}**. The positive point estimate
does not establish improvement because the interval is not entirely above zero.

## Retrieval coverage

- AlphaFold: {retrieval['alphafold_status_counts'].get('DOWNLOADED', 0)} models available;
  {retrieval['alphafold_status_counts'].get('NOT_FOUND', 0)} unavailable.
- Allowed B2 hits after leakage filtering: {retrieval['sequence_allowed_hit_count']}.
- Allowed B3 hits after SIFTS and homology filtering: {retrieval['structure_allowed_hit_count']}.
- Excluded structure hits: {retrieval['structure_exclusion_count']}.
- Candidate coverage on test: B2 {float(b2_coverage['estimate']):.3f},
  B3 {float(b3_coverage['estimate']):.3f}, B4 {float(b4_coverage['estimate']):.3f}.

## Cross-modal error analysis over all 60 pilot queries

- both channels correct: {cross['counts'].get('both_correct', 0)};
- sequence rescue: {cross['counts'].get('sequence_rescue', 0)};
- structure rescue: {cross['counts'].get('structure_rescue', 0)};
- incorrect consensus: {cross['counts'].get('incorrect_consensus', 0)};
- both fail or are missing: {cross['counts'].get('both_fail_or_missing', 0)}.

No structure-rescue example occurred in this pilot. That is a result, not evidence that
structure retrieval can never rescue weak-sequence queries. The pilot contains only one
query in the 20-30% bin and none in the <=20% bin.

## Mapping ablations

Five configurations were executed: no mapping, InterPro2GO, EC2GO/GO mapping, curated
GO Molecular Function names/exact synonyms, and all mappings. Mapping projections came
from official GO external2go files and GO release 2026-07-26. They were frozen before
test scoring. See `evaluation/mapping_ablation_metrics.tsv` and
`evaluation/mapping_ablation_contrasts.tsv`.

## Limitations

- This is a 60-query development pilot with only 9 untouched test queries.
- B2 uses leakage-filterable MMseqs2/Swiss-Prot retrieval because eggNOG-mapper emits
  annotations rather than the required ranked, filterable hit list.
- Fourteen queries had no AlphaFold model, reducing B3 coverage without removing them.
- Difficulty was defined against frozen Swiss-Prot; database-specific target resolution
  is preserved in the raw exclusion artifacts.
- GO experimental rows still need release-matched GOA publication identifiers before
  promotion to a final gold-standard release.
- Scores are ranking features and are not calibrated confidence estimates.

## Reproducibility artifacts

- `predictions.tsv` and `ablation_predictions.tsv`;
- `raw/sequence_evidence.tsv`, `raw/structure_evidence.tsv`, acquisition and exclusions;
- `evaluation/per_query_metrics.tsv`, aggregate metrics, subgroup tests and error table;
- hierarchical EC, GO Lin-BMA and exact InterPro/Pfam secondary metrics;
- `reproducibility_manifest.json`, provenance manifests and `CHECKSUMS.sha256`.
"""
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    checksum_path = args.run / "CHECKSUMS.sha256"
    files = sorted(
        path
        for path in args.run.rglob("*")
        if path.is_file() and path != checksum_path
    )
    checksum_path.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(args.run)}\n" for path in files),
        encoding="utf-8",
    )
    print(f"finalized {args.run} with {len(files)} checksummed files")


if __name__ == "__main__":
    main()
