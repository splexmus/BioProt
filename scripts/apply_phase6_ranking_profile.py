from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.ranking import apply_frozen_ranking_profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply a frozen Phase 6 ranking profile.")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--sequence-predictions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = apply_frozen_ranking_profile(
        candidates_path=args.candidates,
        profile_path=args.profile,
        output_dir=args.output,
        sequence_predictions_path=args.sequence_predictions,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
