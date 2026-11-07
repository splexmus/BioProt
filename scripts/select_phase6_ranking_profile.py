from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.ranking import select_development_ranking_profile


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select a development-only Phase 6 ranking profile."
    )
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = select_development_ranking_profile(
        candidates_path=args.candidates,
        predictions_path=args.predictions,
        dataset_dir=args.dataset,
        config_path=args.config,
        output_dir=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
