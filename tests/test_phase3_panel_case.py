from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
DATASET = ROOT / "benchmark" / "phase3-external-panel-v1"
RUN = ROOT / "benchmark" / "phase3-external-panel-run-v1"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_panel_screening_preserves_every_supplied_decision() -> None:
    screening = _rows(DATASET / "panel_screening.tsv")
    included = [row for row in screening if row["screening_status"] == "INCLUDED_EXTERNAL_CASE"]
    excluded = [row for row in screening if row["screening_status"] == "EXCLUDED"]

    assert len(screening) == 60
    assert len(included) == 47
    assert len(excluded) == 13
    assert sum("NO_TIER_A_EC_OR_GO_MF" in row["exclusion_reasons"] for row in excluded) == 12
    assert (
        next(row for row in excluded if row["accession"] == "F9VMT6")["exclusion_reasons"]
        == "PILOT_CLUSTER_OVERLAP"
    )
    assert {row["accession"] for row in included if row["low_identity_eligible"] == "true"} == {
        "P25583",
        "P28321",
    }


def test_panel_case_is_separate_from_frozen_pilot_splits() -> None:
    splits = _rows(DATASET / "splits.tsv")
    pilot_accessions = {
        row["accession"] for row in _rows(ROOT / "benchmark" / "phase3-pilot-v1" / "queries.tsv")
    }

    assert len(splits) == 47
    assert {row["split"] for row in splits} == {"external_case"}
    assert not ({row["accession"] for row in splits} & pilot_accessions)


def test_panel_run_contains_real_structure_outcomes_and_external_case_claim() -> None:
    retrieval = json.loads((RUN / "retrieval_summary.json").read_text(encoding="utf-8"))
    comparison = json.loads(
        (RUN / "evaluation" / "primary_comparison.json").read_text(encoding="utf-8")
    )

    assert retrieval["alphafold_status_counts"] == {"DOWNLOADED": 43, "NOT_FOUND": 4}
    assert retrieval["structure_allowed_hit_count"] == 412
    assert comparison["paired_query_count"] == 47
    assert comparison["conclusion"] == "NO_MEASURABLE_OVERALL_BENEFIT"
    assert comparison["ci_lower"] <= 0 <= comparison["ci_upper"]


def test_panel_dataset_and_run_checksum_inventories_are_current() -> None:
    for base in (DATASET, RUN):
        for line in (base / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
            expected, relative = line.split("  ", maxsplit=1)
            observed = hashlib.sha256((base / relative).read_bytes()).hexdigest()
            assert observed == expected
