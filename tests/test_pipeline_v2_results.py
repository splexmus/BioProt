from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
RUN = ROOT / "benchmark" / "phase3-pipeline-v2-conservative"


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _metric(split: str, baseline: str, metric: str) -> float:
    rows = _read_tsv(RUN / f"evaluation-{split}" / "aggregate_metrics.tsv")
    return float(
        next(
            row["estimate"]
            for row in rows
            if row["baseline"] == baseline and row["metric"] == metric
        )
    )


def test_v2_profile_preserves_previously_exposed_test_result() -> None:
    summary = json.loads((RUN / "retrieval_summary.json").read_text(encoding="utf-8"))
    assert summary["fusion_profile"] == "quality-gated-v2"
    assert summary["target_pool_k"] == 10
    assert summary["raw_evidence_reused"] is True
    assert _metric("test", "B4_DUAL_DETERMINISTIC", "function_recall_at_10") == (0.7777777777777778)


def test_v2_candidates_expose_raw_and_quality_adjusted_evidence() -> None:
    with (RUN / "ablation_candidates.tsv").open(encoding="utf-8", newline="") as handle:
        fields = set(csv.DictReader(handle, delimiter="\t").fieldnames or [])
    assert {
        "sequence_max_score",
        "structure_max_score",
        "structure_reliability_score",
        "structure_gated_evidence_count",
        "structure_quality_flags",
        "sequence_best_hit_rank",
        "structure_best_hit_rank",
        "agreement_reliability_score",
    } <= fields


def test_v2_checksum_inventory_is_current() -> None:
    for line in (RUN / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", maxsplit=1)
        assert hashlib.sha256((RUN / relative).read_bytes()).hexdigest() == expected
