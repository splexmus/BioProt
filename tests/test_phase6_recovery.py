from __future__ import annotations

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "phase6_recovery", Path(__file__).parents[1] / "scripts/run_phase6_recovery.py"
)
assert SPEC and SPEC.loader
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)


def test_fold_map_keeps_clusters_together_and_is_deterministic():
    clusters = {"a": "same", "b": "same", "c": "c", "d": "d", "e": "e"}
    result = recovery.fold_map(clusters, clusters, 3, 42)
    assert result["a"] == result["b"]
    assert result == recovery.fold_map(reversed(list(clusters)), clusters, 3, 42)
    assert set(result.values()) == {0, 1, 2}


def test_cross_validation_fits_only_training_rows(monkeypatch):
    rows = [{"accession": str(i), "correct": i % 2 == 0} for i in range(6)]
    folds = {str(i): i % 3 for i in range(6)}

    def fit(_name, training):
        accessions = {r["accession"] for r in training}

        def predict(_model, row):
            assert row["accession"] not in accessions
            return 0.5

        return {}, predict

    monkeypatch.setattr(recovery, "fit", fit)
    output = recovery.cross_validate("dummy", rows, folds)
    assert len(output) == len(rows)
    assert {r["accession"] for r in output} == set(folds)
