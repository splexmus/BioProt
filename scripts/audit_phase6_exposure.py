"""Inventory known exposed query identities without opening test labels."""

import argparse
from pathlib import Path

from dualrag.io import file_sha256, read_tsv, write_json, write_tsv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmarks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    sources = [
        args.benchmarks / name / "queries.tsv"
        for name in (
            "step3-merged-reviewed-v1-pipeline",
            "phase6-fresh-validation-v1-pipeline",
            "phase6-fresh-validation-v2-pipeline",
        )
    ]
    ledger = []
    for path in sources:
        for row in read_tsv(path):
            ledger.append(
                {
                    "accession": row["accession"],
                    "sequence_sha256": row["sequence_sha256"],
                    "source": str(path),
                }
            )
    assert all(r["accession"] and len(r["sequence_sha256"]) == 64 for r in ledger)
    args.output.mkdir(parents=True)
    write_tsv(args.output / "exposure_ledger.tsv", ledger, list(ledger[0]))
    write_json(
        args.output / "audit.json",
        {
            "known_unique_accessions": len({r["accession"] for r in ledger}),
            "sources": {str(p): file_sha256(p) for p in sources},
            "complete": False,
            "missing": "Third 300-protein cohort recorded in MEMORY.md; query list not located",
            "new_independent_cohort_authorized_by_audit": False,
            "test_gold_read": False,
            "baseline_coupling": "runner.py passes fusion/reranking weights to B2, B3 and B4",
            "comparator_policy": "Keep V4 B2 predictions fixed for recovery comparisons",
        },
    )


if __name__ == "__main__":
    main()
