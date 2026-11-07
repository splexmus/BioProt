from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.calibration.development import run_frozen_validation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate frozen Phase 6 ranking and calibration on fresh validation."
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--original-predictions", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--gold-labels", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--ranking-profile", type=Path, required=True)
    parser.add_argument("--calibrator", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_frozen_validation(
        predictions_path=args.predictions,
        original_predictions_path=args.original_predictions,
        candidates_path=args.candidates,
        gold_labels_path=args.gold_labels,
        dataset_dir=args.dataset,
        ranking_profile_path=args.ranking_profile,
        calibrator_path=args.calibrator,
        contract_path=args.contract,
        freeze_path=args.freeze,
        output_dir=args.output,
    )
    print(json.dumps(result["evaluation"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
