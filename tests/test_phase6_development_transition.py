from __future__ import annotations

from pathlib import Path

import yaml


def test_phase6_transition_does_not_override_scientific_failure() -> None:
    decision = yaml.safe_load(
        Path("config/phase6-development-transition-v1.yaml").read_text(encoding="utf-8")
    )

    assert decision["status"] == "PASS_FOR_NEW_VALIDATION_BUILD"
    assert decision["scientific_calibration_status"] == "FAIL_SCIENTIFIC_CALIBRATION_GATE"
    assert decision["test_access_authorized"] is False


def test_fresh_validation_v2_failure_keeps_test_locked() -> None:
    decision = yaml.safe_load(
        Path("config/phase6-fresh-validation-v2-decision.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert decision["status"] == "FAIL_SCIENTIFIC_CALIBRATION_GATE"
    assert decision["sample"]["sample_size_gate_passed"] is True
    assert decision["test_access_authorized"] is False
