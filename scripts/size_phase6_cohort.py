"""Estimate confidence-group count coverage from development predictions only."""

import argparse
import random
from collections import defaultdict
from pathlib import Path

from dualrag.io import file_sha256, read_tsv, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probabilities", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    grouped = defaultdict(lambda: [0, 0, 0])
    for row in read_tsv(args.probabilities):
        p = float(row["probability"])
        grouped[row["accession"]][0 if p < 0.5 else 1 if p < 0.75 else 2] += 1
    assert grouped
    vectors = [grouped[a] for a in sorted(grouped)]
    rng = random.Random(42)
    counts = []
    for _ in range(2000):
        sample = rng.choices(vectors, k=300)
        counts.append([sum(v[i] for v in sample) for i in range(3)])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        args.output,
        {
            "planned_size": 300,
            "replicates": 2000,
            "seed": 42,
            "count_minima": [20, 20, 30],
            "estimated_group_count_success_fraction": sum(
                all(n >= minimum for n, minimum in zip(c, [20, 20, 30], strict=True))
                for c in counts
            )
            / len(counts),
            "count_intervals_95": {
                label: [sorted(c[i] for c in counts)[49], sorted(c[i] for c in counts)[1949]]
                for i, label in enumerate(["LOW", "MODERATE", "HIGH"])
            },
            "input_sha256": file_sha256(args.probabilities),
            "interpretation": "Planning for group counts conditional on development-like proteins; "
            "does not estimate calibration-gate power or handle distribution shift",
            "cohort_creation_status": "WAITING_FOR_COMPLETE_EXPOSURE_LEDGER",
        },
    )


if __name__ == "__main__":
    main()
