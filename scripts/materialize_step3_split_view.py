from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.subset import materialize_split_view


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize selected benchmark splits without sealed test labels."
    )
    parser.add_argument("--pipeline-dataset", type=Path, required=True)
    parser.add_argument("--alignments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", action="append", required=True)
    args = parser.parse_args()
    manifest = materialize_split_view(
        pipeline_dir=args.pipeline_dataset,
        alignments_path=args.alignments,
        output_dir=args.output,
        include_splits=set(args.split),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
