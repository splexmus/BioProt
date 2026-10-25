from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.dataset import build_benchmark_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Phase 3.2-3.4 benchmark pilot.")
    parser.add_argument("--swissprot-dat", type=Path, required=True)
    parser.add_argument("--swissprot-fasta", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=Path("config/benchmark-contract-v1.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-id", default="phase3-pilot-v1")
    parser.add_argument("--source-release", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--size", type=int, default=60)
    parser.add_argument("--mmseqs", default="mmseqs")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_benchmark_dataset(
        swissprot_dat=args.swissprot_dat,
        swissprot_fasta=args.swissprot_fasta,
        contract_path=args.contract,
        output_dir=args.output,
        dataset_id=args.dataset_id,
        source_release=args.source_release,
        source_sha256=args.source_sha256,
        size=args.size,
        mmseqs_executable=args.mmseqs,
        resume=args.resume,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
