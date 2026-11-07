from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.sealing import seal_test_labels


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a Step 3 pipeline view without test gold and a test-label vault."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--blinded-output", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    args = parser.parse_args()
    result = seal_test_labels(
        source_dir=args.source,
        blinded_dir=args.blinded_output,
        vault_dir=args.vault,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
