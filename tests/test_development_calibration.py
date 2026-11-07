from __future__ import annotations

import pytest

from dualrag.calibration.development import _fit_method, _frozen_predictor


def test_development_calibration_methods_return_probabilities() -> None:
    rows = [
        {
            "accession": f"P{index}",
            "top1_score": index / 20,
            "top1_top2_margin": index / 40,
            "sample_weight": 1.0,
            "correct": index >= 10,
        }
        for index in range(1, 20)
    ]
    for method in ("platt_logistic", "isotonic_regression", "multifeature_l2_logistic"):
        model, predictor = _fit_method(method, rows)
        probabilities = [predictor(model, row) for row in rows]
        assert all(0.0 <= probability <= 1.0 for probability in probabilities)


def test_frozen_predictor_rejects_unknown_method() -> None:
    with pytest.raises(ValueError, match="unsupported frozen calibration method"):
        _frozen_predictor("new_method", {})
