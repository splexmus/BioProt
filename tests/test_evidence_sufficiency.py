from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from dualrag.calibration.sufficiency import (
    _select_threshold,
    evaluate_frozen_evidence_validation,
)


def test_select_threshold_maximizes_accuracy_with_coverage_floor() -> None:
    rows = [
        {
            "accession": f"P{index}",
            "namespace": "EC" if index % 2 else "GO_MF",
            "sufficiency_probability": index / 10,
            "sample_weight": 1.0,
            "correct": index >= 3,
        }
        for index in range(1, 11)
    ]

    selected = _select_threshold(
        rows,
        eligible_count=10,
        eligible_by_namespace=Counter({"EC": 5, "GO_MF": 5}),
        minimum_coverage=0.8,
        minimum_namespace_coverage=0.8,
        minimum_proteins=8,
    )

    assert selected["accepted_count"] == 8
    assert selected["threshold"] == 0.3


def test_frozen_evaluator_rejects_unfrozen_inputs_before_gold_access(
    tmp_path: Path,
) -> None:
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"status": "NOT_FROZEN"}), encoding="utf-8")

    with pytest.raises(ValueError, match="not frozen"):
        evaluate_frozen_evidence_validation(
            applied_dir=tmp_path / "missing-applied",
            original_predictions_path=tmp_path / "missing-predictions.tsv",
            gold_labels_path=tmp_path / "must-not-be-read.tsv",
            dataset_dir=tmp_path / "missing-dataset",
            ranking_profile_path=tmp_path / "missing-ranking.json",
            bundle_path=tmp_path / "missing-bundle.json",
            contract_path=tmp_path / "missing-contract.yaml",
            freeze_path=freeze,
            output_dir=tmp_path / "output",
        )
