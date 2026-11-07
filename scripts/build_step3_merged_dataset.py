from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.step3 import build_step3_merged_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the merged Step 3 benchmark dataset.")
    parser.add_argument("--nomination", type=Path, action="append", required=True)
    parser.add_argument("--swissprot-dat", type=Path, required=True)
    parser.add_argument("--swissprot-fasta", type=Path, required=True)
    parser.add_argument("--pilot-queries", type=Path, required=True)
    parser.add_argument("--external-panel", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=Path("config/benchmark-contract-v1.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-id", default="step3-merged-reviewed-v1")
    parser.add_argument("--source-release", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--mmseqs", default="mmseqs")
    args = parser.parse_args()
    result = build_step3_merged_dataset(
        nomination_paths=args.nomination,
        swissprot_dat=args.swissprot_dat,
        swissprot_fasta=args.swissprot_fasta,
        pilot_queries=args.pilot_queries,
        external_panel=args.external_panel,
        contract_path=args.contract,
        output_dir=args.output,
        dataset_id=args.dataset_id,
        source_release=args.source_release,
        source_sha256=args.source_sha256,
        mmseqs_executable=args.mmseqs,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
