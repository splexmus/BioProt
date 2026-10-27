from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from dualrag.io import file_sha256, write_json
from dualrag.literature.gates import assess_phase5_development_transition


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize a Phase 4 exit-benchmark manifest.")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--stage", choices=("prepared", "evaluated"), required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).parents[1]
    run = args.run.resolve()
    required = (
        run / "queries/literature_queries.jsonl",
        run / "queries/literature_query_manifest.json",
        run / "pubmed_acquisition_manifest.json",
        run / "retrieval_manifest.json",
        run / "literature_candidates.jsonl",
        run / "literature_hits.jsonl",
        run / "manual_pool_labels.tsv",
    )
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"required exit artifact is missing: {path}")
    annotation = _annotation_summary(run / "manual_pool_labels.tsv")
    evaluation_path = run / "evaluation/literature_evaluation.json"
    if args.stage == "evaluated" and not evaluation_path.is_file():
        raise FileNotFoundError(f"evaluation is missing: {evaluation_path}")
    evaluation = (
        json.loads(evaluation_path.read_text(encoding="utf-8"))
        if evaluation_path.is_file()
        else None
    )
    manifest = {
        "schema_version": 1,
        "contract_id": "phase4-literature-v1",
        "evaluation_version": "literature-pooled-evaluation-v2",
        "stage": args.stage,
        "created_at": datetime.now(UTC).isoformat(),
        "run_directory": str(run),
        "git": {
            "commit": _git(root, "rev-parse", "HEAD"),
            "status": _git(root, "status", "--short"),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pixi_lock_sha256": file_sha256(root / "pixi.lock"),
        },
        "source_inputs": {
            "phase3_dataset_manifest": file_sha256(
                root / "benchmark/phase3-pilot-v1/source_manifest.json"
            ),
            "phase3_reproducibility_manifest": file_sha256(
                root / "benchmark/phase3-pipeline-v2-conservative/reproducibility_manifest.json"
            ),
            "phase4_query_manifest": file_sha256(
                run / "queries/literature_query_manifest.json"
            ),
            "acceptance_contract": file_sha256(
                root / "config/literature-evaluation-v2.yaml"
            ),
            "phase5_development_transition_policy": file_sha256(
                root / "config/phase4-development-transition-v1.yaml"
            ),
        },
        "commands": {
            "prepare": (
                "scripts/run_phase4_exit_benchmark.sh prepare --email <redacted> "
                f"--run-name {run.name} --queries 20"
            ),
            "evaluate": (
                f"scripts/run_phase4_exit_benchmark.sh evaluate --run-name {run.name}"
            ),
        },
        "annotation": annotation,
        "evaluation": evaluation,
        "scientific_exit_status": (
            evaluation.get("status", "NOT_EVALUATED")
            if isinstance(evaluation, dict)
            else "NOT_EVALUATED"
        ),
        "phase5_development_transition": (
            assess_phase5_development_transition(evaluation)
            if isinstance(evaluation, dict)
            else None
        ),
        "artifact_checksums": {
            str(path.relative_to(run)): file_sha256(path)
            for path in sorted(run.rglob("*"))
            if path.is_file() and path.name != "phase4_exit_manifest.json"
        },
        "claim_boundary": (
            "PASS is a development-pilot literature retrieval gate, not experimental "
            "confirmation or absolute recall over all literature. A separate Phase 5 "
            "development transition never changes the scientific exit status."
        ),
    }
    write_json(run / "phase4_exit_manifest.json", manifest)
    print(f"wrote {run / 'phase4_exit_manifest.json'}")


def _annotation_summary(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    annotators = sorted({row["annotator"].strip() for row in rows if row["annotator"].strip()})
    complete = sum(
        all(
            row[field].strip()
            for field in (
                "annotator",
                "relevant",
                "citation_supported",
                "contradiction",
                "entity_correct",
                "organism_correct",
                "primary_experiment",
            )
        )
        for row in rows
    )
    return {
        "row_count": len(rows),
        "complete_row_count": complete,
        "annotators": annotators,
        "contains_codex_preannotation": "codex_preannotation" in annotators,
        "sha256": file_sha256(path),
    }


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    main()
