from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.calibration.scientific import run_scientific_calibration


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the frozen Step 6 validation calibration gate."
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_scientific_calibration(
        predictions_path=args.predictions,
        candidates_path=args.candidates,
        gold_labels_path=args.dataset / "gold_labels.tsv",
        splits_path=args.dataset / "splits.tsv",
        difficulty_path=args.dataset / "difficulty_strata.tsv",
        contract_path=args.contract,
        freeze_path=args.freeze,
        output_dir=args.output,
    )
    print(json.dumps(result["evaluation"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
