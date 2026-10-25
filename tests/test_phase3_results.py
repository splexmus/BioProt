from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
RUN = ROOT / "benchmark" / "phase3-run-v1"


def test_phase3_primary_claim_uses_untouched_test_split() -> None:
    comparison = json.loads(
        (RUN / "evaluation" / "primary_comparison.json").read_text(encoding="utf-8")
    )

    assert comparison["paired_query_count"] == 9
    assert comparison["bootstrap_replicates"] == 10_000
    assert comparison["conclusion"] == "NO_MEASURABLE_OVERALL_BENEFIT"
    assert comparison["ci_lower"] <= 0 <= comparison["ci_upper"]


def test_phase3_contains_all_baselines_and_ablations() -> None:
    with (RUN / "evaluation" / "mapping_ablation_metrics.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    assert {row["baseline"] for row in rows} == {
        "B2_SEQUENCE_ONLY",
        "B3_STRUCTURE_ONLY",
        "B4_DUAL_DETERMINISTIC",
    }
    assert {row["ablation"] for row in rows} == {
        "NO_MAPPING",
        "INTERPRO2GO",
        "GO_EC_MAPPING",
        "CURATED_GO_SYNONYMS",
        "ALL_MAPPINGS",
    }


def test_phase3_checksum_inventory_is_current() -> None:
    for line in (RUN / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", maxsplit=1)
        digest = hashlib.sha256((RUN / relative).read_bytes()).hexdigest()
        assert digest == expected
