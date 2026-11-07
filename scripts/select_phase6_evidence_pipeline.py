from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.calibration.sufficiency import select_development_evidence_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select development-only evidence sufficiency and calibration."
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--ranking-profile", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = select_development_evidence_pipeline(
        predictions_path=args.predictions,
        candidates_path=args.candidates,
        dataset_dir=args.dataset,
        ranking_profile_path=args.ranking_profile,
        config_path=args.config,
        output_dir=args.output,
    )
    print(json.dumps(result["bundle"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
