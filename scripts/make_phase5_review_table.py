from __future__ import annotations

import argparse
from pathlib import Path

from dualrag.rag.review import build_review_table


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Phase 5 human report-review table.")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_review_table(run_dir=args.run, output_path=args.output)
    print(f"created {manifest['report_count']}-report review table -> {args.output}")


if __name__ == "__main__":
    main()
