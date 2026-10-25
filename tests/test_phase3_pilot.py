from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parents[1]
PILOT = ROOT / "benchmark" / "phase3-pilot-v1"


def read_tsv(name: str) -> list[dict[str, str]]:
    with (PILOT / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_pilot_queries_have_admissible_primary_gold() -> None:
    queries = read_tsv("queries.tsv")
    labels = read_tsv("gold_labels.tsv")
    admissible: dict[str, set[str]] = defaultdict(set)
    for label in labels:
        if label["admissible_for_primary"] == "true":
            admissible[label["accession"]].add(label["namespace"])

    accessions = {query["accession"] for query in queries}
    assert len(queries) == len(accessions) == 60
    assert all(admissible[accession] & {"EC", "GO_MF"} for accession in accessions)
    assert all(query["source_release"] == "2026_03" for query in queries)


def test_pilot_clusters_do_not_cross_splits() -> None:
    membership = read_tsv("cluster_membership.tsv")
    cluster_splits: dict[str, set[str]] = defaultdict(set)
    for row in membership:
        cluster_splits[row["cluster_representative"]].add(row["split"])

    assert len(membership) == 60
    assert all(len(splits) == 1 for splits in cluster_splits.values())


def test_pilot_has_one_difficulty_assignment_per_query() -> None:
    queries = read_tsv("queries.tsv")
    difficulty = read_tsv("difficulty_strata.tsv")

    assert {row["accession"] for row in difficulty} == {row["accession"] for row in queries}
    assert len(difficulty) == 60


def test_pilot_summary_matches_materialized_rows() -> None:
    summary = json.loads((PILOT / "summary.json").read_text(encoding="utf-8"))

    assert summary["query_count"] == len(read_tsv("queries.tsv"))
    assert summary["prohibited_pair_count"] == len(read_tsv("prohibited_targets.tsv"))
    assert sum(summary["split_query_counts"].values()) == summary["query_count"]
    assert sum(summary["difficulty_counts"].values()) == summary["query_count"]


def test_pilot_checksum_inventory_is_current() -> None:
    expected: dict[str, str] = {}
    for line in (PILOT / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        digest, filename = line.split("  ", maxsplit=1)
        expected[filename] = digest

    assert "queries.tsv" in expected
    assert "source_manifest.json" in expected
    for filename, digest in expected.items():
        assert sha256_file(PILOT / filename) == digest
