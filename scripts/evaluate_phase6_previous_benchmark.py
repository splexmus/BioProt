from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.calibration.sufficiency import evaluate_previous_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrospectively evaluate the evidence pipeline on revealed labels."
    )
    parser.add_argument("--applied", type=Path, required=True)
    parser.add_argument("--original-predictions", type=Path, required=True)
    parser.add_argument("--gold-labels", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_previous_benchmark(
        applied_dir=args.applied,
        original_predictions_path=args.original_predictions,
        gold_labels_path=args.gold_labels,
        dataset_dir=args.dataset,
        output_dir=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
