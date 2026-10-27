from __future__ import annotations

from typing import Any

PHASE5_DEVELOPMENT_TRANSITION_VERSION = "phase4-to-phase5-development-v1"

_REQUIRED_READINESS_CHECKS = (
    "minimum_queries",
    "complete_candidate_pool",
    "expert_annotation_provenance",
    "minimum_contradiction_labels",
    "query_candidate_coverage",
)


def assess_phase5_development_transition(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Assess engineering readiness without rewriting the scientific Phase 4 result."""
    acceptance = evaluation.get("acceptance")
    if not isinstance(acceptance, dict):
        return _assessment("HOLD_FOR_PHASE5_DEVELOPMENT", ["missing_acceptance_result"], [])

    checks = acceptance.get("checks")
    if not isinstance(checks, list):
        return _assessment("HOLD_FOR_PHASE5_DEVELOPMENT", ["missing_acceptance_checks"], [])

    by_name = {
        str(check.get("name")): check
        for check in checks
        if isinstance(check, dict) and check.get("name")
    }
    failed_readiness = [
        name
        for name in _REQUIRED_READINESS_CHECKS
        if name not in by_name or by_name[name].get("passed") is not True
    ]
    failed_scientific = sorted(
        name
        for name, check in by_name.items()
        if check.get("passed") is not True and name not in failed_readiness
    )
    status = (
        "PASS_FOR_PHASE5_DEVELOPMENT"
        if not failed_readiness
        else "HOLD_FOR_PHASE5_DEVELOPMENT"
    )
    return _assessment(status, failed_readiness, failed_scientific)


def _assessment(
    status: str,
    failed_readiness: list[str],
    failed_scientific: list[str],
) -> dict[str, Any]:
    return {
        "policy_version": PHASE5_DEVELOPMENT_TRANSITION_VERSION,
        "status": status,
        "required_readiness_checks": list(_REQUIRED_READINESS_CHECKS),
        "failed_readiness_checks": failed_readiness,
        "failed_scientific_exit_checks": failed_scientific,
        "permits": ["phase5_engineering", "phase5_prompt_and_verifier_evaluation"]
        if status == "PASS_FOR_PHASE5_DEVELOPMENT"
        else [],
        "does_not_permit": [
            "claiming_phase4_scientific_exit_passed",
            "treating_retrieved_literature_as_validated_direct_support",
            "calibrated_confidence",
            "production_or_clinical_use",
        ],
        "claim_boundary": (
            "This transition assesses whether the labelled artifacts are usable for Phase 5 "
            "development. It does not relax or replace the frozen Phase 4 scientific exit gate."
        ),
    }
