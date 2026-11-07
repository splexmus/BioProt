from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.calibration.sufficiency import apply_evidence_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply evidence sufficiency, abstention, and calibration without gold."
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--ranking-profile", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = apply_evidence_pipeline(
        predictions_path=args.predictions,
        candidates_path=args.candidates,
        ranking_profile_path=args.ranking_profile,
        bundle_path=args.bundle,
        output_dir=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
