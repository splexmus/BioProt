from __future__ import annotations

from pathlib import Path

import yaml


def test_scientific_calibration_thresholds_are_complete_and_frozen() -> None:
    contract = yaml.safe_load(
        Path("config/calibration-evaluation-v2.yaml").read_text(encoding="utf-8")
    )

    assert contract["status"] == "FROZEN_BEFORE_NEW_VALIDATION_PREDICTIONS"
    assert contract["data_boundaries"]["test_split"] == (
        "one_time_frozen_model_evaluation_only"
    )
    assert "test_gold_labels" in contract["data_boundaries"]["prohibited_inputs"]
    assert contract["data_boundaries"]["validation_gold_materialized_before_threshold_freeze"]
    assert not contract["data_boundaries"]["validation_prediction_results_available_at_freeze"]
    minimum = contract["minimum_evaluation_size"]
    assert minimum["validation"]["evaluable_query_namespace_examples"] >= 100
    assert minimum["test"]["evaluable_query_namespace_examples"] >= 100
    assert minimum["candidate_prediction_coverage"] >= 0.80

    policy = contract["acceptance_policy"]
    metrics = policy["overall_metrics"]
    assert metrics["brier_score"] == {
        "maximum": 0.22,
        "minimum_improvement_over_raw": 0.02,
    }
    assert metrics["log_loss"]["maximum"] == 0.65
    assert metrics["expected_calibration_error"]["maximum"] == 0.10
    assert all(
        metric["minimum_improvement_over_raw"] > 0 for metric in metrics.values()
    )
    groups = policy["confidence_groups"]
    assert groups["monotonic_order"] == ["LOW", "MODERATE", "HIGH"]
    assert groups["minimum_examples"]["HIGH"] >= 30
    assert groups["high_confidence"]["minimum_point_accuracy"] >= 0.85
    assert groups["high_confidence"]["minimum_wilson_95_lower_bound"] >= 0.70

    provenance = contract["provenance"]
    assert provenance["universal_standard_claimed"] is False
    assert "new_validation_prediction_results" in provenance["not_informed_by"]
    assert "sealed_test_gold_evaluation" in provenance["not_informed_by"]

