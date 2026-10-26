from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.io import read_tsv, write_json, write_tsv

METRICS = (
    "function_recall_at_1",
    "function_recall_at_5",
    "function_recall_at_10",
    "precision_at_10",
    "mrr",
    "ndcg_at_10",
)
BASELINES = ("B2_SEQUENCE_ONLY", "B3_STRUCTURE_ONLY", "B4_DUAL_DETERMINISTIC")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare frozen v1 and v2 pipeline profiles.")
    parser.add_argument("--v1-development", type=Path, required=True)
    parser.add_argument("--v1-validation", type=Path, required=True)
    parser.add_argument("--v1-test", type=Path, required=True)
    parser.add_argument("--v2-run", type=Path, required=True)
    parser.add_argument("--deep-v2-run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _metric_index(path: Path) -> dict[tuple[str, str], float]:
    return {
        (row["baseline"], row["metric"]): float(row["estimate"])
        for row in read_tsv(path / "aggregate_metrics.tsv")
    }


def main() -> None:
    args = parse_args()
    profiles: dict[str, dict[str, Path]] = {
        "fixed-weight-v1": {
            "development": args.v1_development,
            "validation": args.v1_validation,
            "test": args.v1_test,
        },
        "quality-gated-v2": {
            split: args.v2_run / f"evaluation-{split}"
            for split in ("development", "validation", "test")
        },
    }
    if args.deep_v2_run is not None:
        profiles["quality-gated-v2-deep50"] = {
            split: args.deep_v2_run / f"evaluation-{split}"
            for split in ("development", "validation", "test")
        }

    indexes = {
        (profile, split): _metric_index(path)
        for profile, splits in profiles.items()
        for split, path in splits.items()
    }
    rows: list[dict[str, object]] = []
    for profile in profiles:
        for split in ("development", "validation", "test"):
            current = indexes[(profile, split)]
            reference = indexes[("fixed-weight-v1", split)]
            for baseline in BASELINES:
                for metric in METRICS:
                    estimate = current[(baseline, metric)]
                    rows.append(
                        {
                            "profile": profile,
                            "split": split,
                            "baseline": baseline,
                            "metric": metric,
                            "estimate": estimate,
                            "delta_vs_fixed_weight_v1": estimate - reference[(baseline, metric)],
                        }
                    )
    args.output.mkdir(parents=True, exist_ok=True)
    write_tsv(args.output / "profile_comparison.tsv", rows, list(rows[0]))

    dual_fr10 = {
        f"{profile}:{split}": indexes[(profile, split)][
            ("B4_DUAL_DETERMINISTIC", "function_recall_at_10")
        ]
        for profile in profiles
        for split in ("development", "validation", "test")
    }
    summary = {
        "profiles": list(profiles),
        "primary_profile": "quality-gated-v2",
        "selection_reason": (
            "Higher development FR@5/FR@10 with unchanged validation metrics and unchanged "
            "previously exposed test metrics. The 50-hit profile remains experimental."
        ),
        "dual_function_recall_at_10": dual_fr10,
        "scientific_conclusion": "NO_MEASURABLE_OVERALL_BENEFIT",
    }
    write_json(args.output / "profile_comparison.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
