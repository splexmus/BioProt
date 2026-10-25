from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from dualrag.benchmark.dataset import parse_swissprot
from dualrag.benchmark.metrics import go_ancestors, parse_go_is_a


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build frozen Swiss-Prot GO-MF IC values.")
    parser.add_argument("--swissprot-dat", type=Path, required=True)
    parser.add_argument("--go-obo", type=Path, required=True)
    parser.add_argument("--source-release", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    parents = parse_go_is_a(args.go_obo)
    counts: Counter[str] = Counter()
    protein_count = 0
    for entry in parse_swissprot(args.swissprot_dat):
        terms = {
            label.identifier
            for label in entry.labels
            if label.namespace == "GO_MF" and label.identifier != "GO:0003674"
        }
        if not terms:
            continue
        protein_count += 1
        propagated = {ancestor for term in terms for ancestor in go_ancestors(term, parents)}
        counts.update(propagated)
    output = args.output / "go_mf_information_content.tsv"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["go_id", "protein_count", "corpus_size", "information_content"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for term, count in sorted(counts.items()):
            writer.writerow(
                {
                    "go_id": term,
                    "protein_count": count,
                    "corpus_size": protein_count,
                    "information_content": f"{-math.log(count / protein_count):.12f}",
                }
            )
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "source_release": args.source_release,
        "swissprot_sha256": sha256(args.swissprot_dat),
        "go_obo_sha256": sha256(args.go_obo),
        "protein_corpus_size": protein_count,
        "go_term_count": len(counts),
        "output_sha256": sha256(output),
    }
    (args.output / "go_ic_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
