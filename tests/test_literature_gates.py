from __future__ import annotations

from dualrag.literature.gates import assess_phase5_development_transition


def _evaluation(*, failed: set[str] | None = None) -> dict[str, object]:
    failed = failed or set()
    names = (
        "minimum_queries",
        "complete_candidate_pool",
        "expert_annotation_provenance",
        "minimum_contradiction_labels",
        "query_candidate_coverage",
        "recall_at_10",
        "entity_correctness",
    )
    return {
        "status": "FAIL" if failed else "PASS",
        "acceptance": {
            "checks": [
                {"name": name, "passed": name not in failed}
                for name in names
            ]
        },
    }


def test_failed_scientific_metrics_can_still_pass_development_transition() -> None:
    result = assess_phase5_development_transition(
        _evaluation(failed={"recall_at_10", "entity_correctness"})
    )

    assert result["status"] == "PASS_FOR_PHASE5_DEVELOPMENT"
    assert result["failed_readiness_checks"] == []
    assert result["failed_scientific_exit_checks"] == [
        "entity_correctness",
        "recall_at_10",
    ]
    assert "claiming_phase4_scientific_exit_passed" in result["does_not_permit"]


def test_failed_readiness_check_holds_phase5_development() -> None:
    result = assess_phase5_development_transition(
        _evaluation(failed={"complete_candidate_pool"})
    )

    assert result["status"] == "HOLD_FOR_PHASE5_DEVELOPMENT"
    assert result["failed_readiness_checks"] == ["complete_candidate_pool"]
    assert result["permits"] == []
