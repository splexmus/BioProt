from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from dualrag import __version__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize a quality-gated-v2 rescore.")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--mappings", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_output(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    return (result.stdout or result.stderr).strip()


def main() -> None:
    args = parse_args()
    root = Path(__file__).parents[1]
    raw_names = (
        "sequence_evidence.tsv",
        "structure_evidence.tsv",
        "alphafold_acquisition.tsv",
        "structure_exclusions.tsv",
    )
    raw_inputs = {}
    for name in raw_names:
        source = args.source_run / "raw" / name
        current = args.run / "raw" / name
        source_digest = sha256(source)
        current_digest = sha256(current)
        if source_digest != current_digest:
            raise ValueError(f"raw evidence differs from source run: {name}")
        raw_inputs[name] = source_digest

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "profile": "quality-gated-v2",
        "target_pool_k": 10,
        "source_run": str(args.source_run),
        "dataset": str(args.dataset),
        "raw_evidence_reused": True,
        "raw_input_sha256": raw_inputs,
        "configuration": {
            "sequence_weight": 0.50,
            "structure_weight": 0.30,
            "agreement_weight": 0.20,
            "support_bonus_max": 0.15,
            "support_saturation": 3,
            "direct_hit_k": 10,
            "deep_support_min": 3,
            "deep_candidate_score_multiplier": 0.50,
            "structure_min_query_coverage": 0.50,
            "structure_min_target_coverage": 0.50,
            "structure_min_tm_score": 0.50,
            "structure_quality_floor": 0.20,
        },
        "inputs": {
            "dataset_manifest_sha256": sha256(args.dataset / "source_manifest.json"),
            "mapping_manifest_sha256": sha256(args.mappings / "manifest.json"),
            "go_ic_manifest_sha256": sha256(args.mappings / "go_ic_manifest.json"),
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "dualrag": __version__,
            "pixi_lock_sha256": sha256(root / "pixi.lock"),
        },
        "git": {
            "commit": command_output(["git", "rev-parse", "HEAD"]),
            "status": command_output(["git", "status", "--short"]),
        },
        "claim_scope": (
            "Development/validation-selected ranking profile regression-checked on the "
            "already exposed nine-query v1 test split. It is not fresh confirmation or a "
            "powered biological benchmark."
        ),
        "scientific_conclusion": "NO_MEASURABLE_OVERALL_BENEFIT",
    }
    manifest_path = args.run / "reproducibility_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    checksum_path = args.run / "CHECKSUMS.sha256"
    files = sorted(path for path in args.run.rglob("*") if path.is_file() and path != checksum_path)
    checksum_path.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(args.run)}\n" for path in files),
        encoding="utf-8",
    )
    print(f"wrote {manifest_path} and {checksum_path} ({len(files)} files)")


if __name__ == "__main__":
    main()
