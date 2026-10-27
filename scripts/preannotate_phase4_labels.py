from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.literature.preannotation import write_preannotation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create conservative, non-expert Phase 4 label suggestions."
    )
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review-queue", required=True, type=Path)
    args = parser.parse_args()
    summary = write_preannotation(
        queries_path=args.run / "queries/literature_queries.jsonl",
        candidates_path=args.run / "literature_candidates.jsonl",
        articles_path=args.run / "article_metadata.jsonl",
        output_path=args.output,
        review_queue_path=args.review_queue,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
