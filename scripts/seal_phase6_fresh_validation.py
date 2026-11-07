from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.fresh_validation import seal_fresh_validation_labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Seal fresh Phase 6 validation labels.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--pipeline", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    args = parser.parse_args()
    manifest = seal_fresh_validation_labels(
        source_dir=args.source,
        pipeline_dir=args.pipeline,
        vault_dir=args.vault,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
