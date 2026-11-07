from __future__ import annotations

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
