from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.calibration.development import run_development_calibration_cv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run cluster-aware development calibration for Phase 6."
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--ranking-profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_development_calibration_cv(
        predictions_path=args.predictions,
        candidates_path=args.candidates,
        dataset_dir=args.dataset,
        ranking_profile_path=args.ranking_profile,
        output_dir=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
