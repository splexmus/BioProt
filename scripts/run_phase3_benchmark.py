from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.runner import run_phase3_benchmark
from dualrag.config import AppConfig, load_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 3 B2/B3/B4 retrieval baselines.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--swissprot-dat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--foldseek-db", type=Path)
    parser.add_argument("--foldseek-metadata", type=Path)
    parser.add_argument("--alphafold-cache", type=Path)
    parser.add_argument("--tmp-dir", type=Path)
    parser.add_argument("--mapping-projections", type=Path)
    parser.add_argument("--fusion-mappings", type=Path)
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
    parser.add_argument("--sequence-weight", type=float)
    parser.add_argument("--structure-weight", type=float)
    parser.add_argument("--agreement-weight", type=float)
    parser.add_argument("--base-score-weight", type=float)
    parser.add_argument("--quality-weight", type=float)
    parser.add_argument("--fusion-version")
    parser.add_argument("--rerank-version")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config) if args.config else None
    tmp_dir = args.tmp_dir or (config.paths.tmp_dir if config else None)
    if tmp_dir is None:
        raise ValueError("--tmp-dir is required when --config is not supplied")
    summary = run_phase3_benchmark(
        dataset_dir=args.dataset,
        swissprot_dat=args.swissprot_dat,
        output_dir=args.output,
        foldseek_db=args.foldseek_db or (config.structure.foldseek_db if config else None),
        foldseek_metadata=args.foldseek_metadata
        or (config.structure.target_metadata if config else None),
        alphafold_cache=args.alphafold_cache
        or (config.structure.alphafold_cache if config else None),
        tmp_dir=tmp_dir,
        mapping_projection_path=args.mapping_projections,
        fusion_mapping_path=args.fusion_mappings
        or (config.fusion.mapping_path if config else None),
        synonym_path=args.synonyms or (config.fusion.synonym_path if config else None),
        structure_enabled=not args.skip_structure,
        resume=args.resume,
        reuse_raw_evidence=args.reuse_raw_evidence,
        target_pool_k=args.target_pool_k,
        quality_gated_fusion=args.quality_gated_fusion
        or bool(config and config.fusion.support_aggregation_enabled),
        sequence_weight=_value(args.sequence_weight, config, "sequence_weight"),
        structure_weight=_value(args.structure_weight, config, "structure_weight"),
        agreement_weight=_value(args.agreement_weight, config, "agreement_weight"),
        base_score_weight=_value(args.base_score_weight, config, "base_score_weight"),
        quality_weight=_value(args.quality_weight, config, "quality_weight"),
        fusion_version=args.fusion_version or (config.fusion.version if config else None),
        rerank_version=args.rerank_version
        or (config.fusion.rerank_version if config else None),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


def _value(explicit: float | None, config: AppConfig | None, field: str) -> float | None:
    return explicit if explicit is not None else getattr(config.fusion, field, None)


if __name__ == "__main__":
    main()
