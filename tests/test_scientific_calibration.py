from __future__ import annotations

import json

import pytest

from dualrag.calibration.scientific import (
    _fit_isotonic,
    _fit_multifeature_logistic,
    _predict_isotonic,
    _predict_multifeature,
)


def _row(score: float, correct: bool) -> dict[str, object]:
    return {
        "top1_score": score,
        "top1_top2_margin": score / 2,
        "sample_weight": 1.0,
        "correct": correct,
    }


def test_isotonic_predictions_are_monotonic() -> None:
    rows = [_row(0.1, False), _row(0.2, True), _row(0.3, False), _row(0.9, True)]
    model = _fit_isotonic(rows)
    probabilities = [_predict_isotonic(model, score) for score in (0.1, 0.2, 0.3, 0.9)]
    assert probabilities == sorted(probabilities)


def test_multifeature_logistic_returns_probabilities() -> None:
    rows = [_row(index / 20, index >= 10) for index in range(1, 20)]
    model = _fit_multifeature_logistic(rows)
    probabilities = [_predict_multifeature(model, row) for row in rows]
    assert all(0.0 <= probability <= 1.0 for probability in probabilities)
    assert probabilities[-1] > probabilities[0]


def test_namespace_model_serializes_and_uses_training_scaling() -> None:
    rows = [
        dict(_row(0.6, i % 2 == 0), namespace="EC" if i % 2 == 0 else "GO_MF") for i in range(20)
    ]
    model = _fit_multifeature_logistic(rows, l2_penalty=0.1, namespace_aware=True)
    restored = json.loads(json.dumps(model))
    assert restored["l2_penalty"] == 0.1
    assert _predict_multifeature(restored, rows[0]) > _predict_multifeature(restored, rows[1])
    means = list(restored["feature_means"])
    _predict_multifeature(restored, dict(rows[0], top1_score=100))
    assert restored["feature_means"] == means


@pytest.mark.parametrize("penalty", [0, -1, float("nan"), float("inf")])
def test_logistic_rejects_invalid_penalty(penalty) -> None:
    with pytest.raises(ValueError):
        _fit_multifeature_logistic([_row(0.5, True)], l2_penalty=penalty)
