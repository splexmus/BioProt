from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.rag.pipeline import augment_generation_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Add reproducibility provenance to Phase 5.")
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    manifest = augment_generation_manifest(args.run)
    print(
        json.dumps(
            {
                "run": str(args.run),
                "report_count": manifest["report_count"],
                "artifact_count": len(manifest["artifact_checksums"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
