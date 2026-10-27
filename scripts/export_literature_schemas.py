from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.literature.schemas import (
    ArticleMetadata,
    EvidencePacket,
    LiteratureCandidate,
    LiteratureChunk,
    LiteratureHit,
    LiteratureQuery,
    SelectedHomolog,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Phase 4 Pydantic JSON schemas.")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    models = (
        SelectedHomolog,
        LiteratureQuery,
        ArticleMetadata,
        LiteratureChunk,
        LiteratureCandidate,
        LiteratureHit,
        EvidencePacket,
    )
    payload = {
        "schema_version": 1,
        "contract_id": "phase4-literature-v1",
        "models": {model.__name__: model.model_json_schema() for model in models},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
