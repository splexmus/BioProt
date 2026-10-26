from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.runner import run_phase3_benchmark


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 3 B2/B3/B4 retrieval baselines.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--swissprot-dat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--foldseek-db", type=Path)
    parser.add_argument("--foldseek-metadata", type=Path)
    parser.add_argument("--alphafold-cache", type=Path)
    parser.add_argument("--tmp-dir", type=Path, required=True)
    parser.add_argument("--mapping-projections", type=Path)
    parser.add_argument("--synonyms", type=Path)
    parser.add_argument("--skip-structure", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--reuse-raw-evidence",
        action="store_true",
        help="Rescore preserved raw TSV evidence without rerunning retrieval or external APIs.",
    )
    parser.add_argument(
        "--target-pool-k",
        type=int,
        default=10,
        help="Allowed target hits retained per modality before function aggregation.",
    )
    parser.add_argument(
        "--quality-gated-fusion",
        action="store_true",
        help="Use quality-gated-v2 scoring and biological-source support aggregation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_phase3_benchmark(
        dataset_dir=args.dataset,
        swissprot_dat=args.swissprot_dat,
        output_dir=args.output,
        foldseek_db=args.foldseek_db,
        foldseek_metadata=args.foldseek_metadata,
        alphafold_cache=args.alphafold_cache,
        tmp_dir=args.tmp_dir,
        mapping_projection_path=args.mapping_projections,
        synonym_path=args.synonyms,
        structure_enabled=not args.skip_structure,
        resume=args.resume,
        reuse_raw_evidence=args.reuse_raw_evidence,
        target_pool_k=args.target_pool_k,
        quality_gated_fusion=args.quality_gated_fusion,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
