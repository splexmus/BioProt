from __future__ import annotations

import json
from pathlib import Path

import pytest

from dualrag.calibration.analysis import load_validation_status, validation_explanation
from dualrag.io import file_sha256


def test_registered_calibration_has_values_and_explicit_scope():
    status = load_validation_status()
    assert status["status"] == "PASS_SCIENTIFIC_CALIBRATION_GATE"
    assert status["native_analysis_applicable"] is False
    assert status["brier_score"] == pytest.approx(0.19443108358500333)
    assert status["coverage"] == pytest.approx(370 / 404)
    assert "not this query's probability" in "\n".join(validation_explanation(status))


def test_registered_calibration_matches_original_evaluation_when_available():
    status = load_validation_status()
    root = Path(__file__).parents[1]
    path = root / status["evaluation_path"]
    if not path.is_file():
        pytest.skip("original scientific evaluation is stored outside Git")
    assert file_sha256(path) == status["evaluation_sha256"]
    evaluation = json.loads(path.read_text())
    assert status["status"] == evaluation["status"]
    for key in ("brier_score", "log_loss", "expected_calibration_error"):
        assert status[key] == evaluation["frozen_calibrator_metrics"][key]
