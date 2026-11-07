from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.calibration.sufficiency import evaluate_frozen_evidence_validation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate a frozen ranking, abstention, and calibration pipeline."
    )
    parser.add_argument("--applied", type=Path, required=True)
    parser.add_argument("--original-predictions", type=Path, required=True)
    parser.add_argument("--gold-labels", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--ranking-profile", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_frozen_evidence_validation(
        applied_dir=args.applied,
        original_predictions_path=args.original_predictions,
        gold_labels_path=args.gold_labels,
        dataset_dir=args.dataset,
        ranking_profile_path=args.ranking_profile,
        bundle_path=args.bundle,
        contract_path=args.contract,
        freeze_path=args.freeze,
        output_dir=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
