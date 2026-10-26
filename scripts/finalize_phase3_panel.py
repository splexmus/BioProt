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
    parser = argparse.ArgumentParser(description="Finalize an external Phase 3 panel case.")
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
    copies = (
        (args.pdb_metadata_manifest, "phase3-pdb-metadata.tsv.manifest.json"),
        (args.mappings / "manifest.json", "phase3-mapping-manifest.json"),
        (args.mappings / "go_ic_manifest.json", "phase3-go-ic-manifest.json"),
        (args.dataset / "source_manifest.json", "phase3-dataset-source-manifest.json"),
    )
    for source, target in copies:
        shutil.copyfile(source, provenance / target)

    root = Path(__file__).parents[1]
    evaluation = args.run / "evaluation"
    aggregate = read_tsv(evaluation / "aggregate_metrics.tsv")
    comparison = json.loads((evaluation / "primary_comparison.json").read_text())
    cross = json.loads((evaluation / "cross_modal_metrics.json").read_text())
    retrieval = json.loads((args.run / "retrieval_summary.json").read_text())
    dataset = json.loads((args.dataset / "summary.json").read_text())
    b2 = metric(aggregate, "B2_SEQUENCE_ONLY", "function_recall_at_10")
    b3 = metric(aggregate, "B3_STRUCTURE_ONLY", "function_recall_at_10")
    b4 = metric(aggregate, "B4_DUAL_DETERMINISTIC", "function_recall_at_10")

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "phase": "3 external-case rerun",
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
            "pixi_lock_sha256": sha256(root / "pixi.lock"),
            "mmseqs2": command_output(["mmseqs", "version"]),
            "foldseek": command_output(["foldseek", "version"]),
        },
        "inputs": {
            "dataset_manifest_sha256": sha256(args.dataset / "source_manifest.json"),
            "panel_input_sha256": sha256(args.dataset / "panel_input.tsv"),
            "mapping_manifest_sha256": sha256(args.mappings / "manifest.json"),
            "go_ic_manifest_sha256": sha256(args.mappings / "go_ic_manifest.json"),
            "pdb_metadata_manifest_sha256": sha256(args.pdb_metadata_manifest),
        },
        "commands": [
            "scripts/build_phase3_panel_case.py",
            "python -m dualrag.structure.metadata",
            "scripts/run_phase3_benchmark.py",
            "scripts/evaluate_phase3.py --evaluation-split external_case",
            "scripts/finalize_phase3_panel.py",
        ],
        "claim_scope": (
            "Independent external candidate-panel case. It does not replace or enlarge "
            "the frozen pilot test split and is not a powered release benchmark."
        ),
    }
    (args.run / "reproducibility_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    def interval(row: dict[str, str]) -> str:
        return f"{float(row['ci_lower']):.3f}-{float(row['ci_upper']):.3f}"

    report = f"""# Phase 3 external candidate-panel benchmark

Run: `phase3-external-panel-run-v1`  
Dataset: `phase3-external-panel-v1`  
Source panel date: 2026-10-26  
Evaluation split: `external_case`

This is a separately labelled external-case rerun. It does not change the original
60-protein pilot or its untouched nine-query test split.

## Screening

- Supplied candidates: {dataset["supplied_candidate_count"]}.
- Included after frozen-source and pilot-cluster screening: {dataset["included_query_count"]}.
- Excluded: {dataset["excluded_candidate_count"]}.
- Eligible for the <=30% closest-allowed-identity subgroup:
  {dataset["low_identity_eligible_count"]}.
- Architecture labels remain provisional because positional InterProScan evidence was
  not available.

The complete decisions are in `benchmark/phase3-external-panel-v1/panel_screening.tsv`.
`NO_ANNOTATED_ACTIVE_SITE` means no UniProt `ACT_SITE` feature and does not establish
biological inactivity.

## External-case result

| Baseline | Function Recall@10 | 95% bootstrap interval |
|---|---:|---:|
| B2 sequence only | {float(b2["estimate"]):.3f} | {interval(b2)} |
| B3 structure only | {float(b3["estimate"]):.3f} | {interval(b3)} |
| B4 deterministic dual | {float(b4["estimate"]):.3f} | {interval(b4)} |

The paired B4-minus-B2 estimate is {float(comparison["estimate"]):.4f}, with a 95%
interval from {float(comparison["ci_lower"]):.4f} to
{float(comparison["ci_upper"]):.4f}. The contract conclusion is
**{comparison["conclusion"]}**. Dual retrieval therefore showed no measurable overall
benefit in this external case.

## Retrieval and cross-modal outcomes

- AlphaFold models downloaded: {retrieval["alphafold_status_counts"].get("DOWNLOADED", 0)}.
- AlphaFold models unavailable: {retrieval["alphafold_status_counts"].get("NOT_FOUND", 0)}.
- Allowed sequence hits: {retrieval["sequence_allowed_hit_count"]}.
- Allowed structure hits: {retrieval["structure_allowed_hit_count"]}.
- Excluded structure hits: {retrieval["structure_exclusion_count"]}.
- Both channels correct: {cross["counts"].get("both_correct", 0)}.
- Sequence rescues: {cross["counts"].get("sequence_rescue", 0)}.
- Structure rescues: {cross["counts"].get("structure_rescue", 0)}.
- Incorrect consensus: {cross["counts"].get("incorrect_consensus", 0)}.
- Both failed or missing: {cross["counts"].get("both_fail_or_missing", 0)}.

No structure rescue occurred. The low-identity subgroup contains only two proteins, so
it cannot support a general conclusion about remote-homology rescue.

## Interpretation limits

- Twelve supplied proteins lacked admissible Tier-A EC/GO-MF labels in frozen
  Swiss-Prot 2026_03; one additional candidate overlapped an exposed pilot cluster.
- This panel was proposed after the original benchmark was inspected, so it is an
  exploratory external case, not a new untouched confirmatory test set.
- Mapping ablations did not change B4 Function Recall@10 in this cohort.
- Supplied single/multi-domain labels remain unverified and subgroup results using them
  are exploratory only.
- Scores are retrieval-ranking features, not calibrated biological confidence.
"""
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    checksum_path = args.run / "CHECKSUMS.sha256"
    files = sorted(path for path in args.run.rglob("*") if path.is_file() and path != checksum_path)
    checksum_path.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(args.run)}\n" for path in files),
        encoding="utf-8",
    )
    print(f"finalized {args.run} with {len(files)} checksummed files")


if __name__ == "__main__":
    main()
