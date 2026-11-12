from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.fresh_validation import build_fresh_validation_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a fresh Phase 6 validation cohort.")
    parser.add_argument("--swissprot-dat", type=Path, required=True)
    parser.add_argument("--swissprot-fasta", type=Path, required=True)
    parser.add_argument("--exclude-dataset", type=Path, action="append", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-release", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--dataset-id", default="phase6-fresh-validation-v1")
    parser.add_argument("--size", type=int, default=150)
    parser.add_argument("--pool-size", type=int, default=600)
    parser.add_argument("--exclude-exposed-queries", action="store_true")
    args = parser.parse_args()
    manifest = build_fresh_validation_dataset(
        swissprot_dat=args.swissprot_dat,
        swissprot_fasta=args.swissprot_fasta,
        exclude_datasets=args.exclude_dataset,
        contract_path=args.contract,
        output_dir=args.output,
        source_release=args.source_release,
        source_sha256=args.source_sha256,
        dataset_id=args.dataset_id,
        size=args.size,
        pool_size=args.pool_size,
        exclude_exposed_queries=args.exclude_exposed_queries,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
