from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from dualrag.benchmark.metrics import evaluate_function_predictions
from dualrag.calibration.pipeline import (
    _build_examples,
    _candidate_index,
    _evaluate,
    _fit_platt,
    _gold_sets,
    _predict,
    _principal_b4,
)
from dualrag.calibration.scientific import (
    _bootstrap_intervals,
    _fit_isotonic,
    _fit_multifeature_logistic,
    _group_wilson,
    _method_gate,
    _predict_isotonic,
    _predict_multifeature,
)
from dualrag.io import file_sha256, read_tsv, stable_hash, write_json, write_tsv


def run_development_calibration_cv(
    *,
    predictions_path: Path,
    candidates_path: Path,
    dataset_dir: Path,
    ranking_profile_path: Path,
    output_dir: Path,
    folds: int = 5,
    seed: int = 42,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite calibration run: {output_dir}")
    split_rows = read_tsv(dataset_dir / "splits.tsv")
    if {row["split"] for row in split_rows} != {"development"}:
        raise ValueError("development calibration requires a development-only dataset")
    splits = {row["accession"]: row["split"] for row in split_rows}
    clusters = {
        row["accession"]: row["cluster_representative"]
        for row in read_tsv(dataset_dir / "cluster_membership.tsv")
    }
    fold_by_accession = {
        accession: int(stable_hash(clusters[accession])[:8], 16) % folds
        for accession in splits
    }
    examples, exclusions = _build_examples(
        gold=_gold_sets(read_tsv(dataset_dir / "gold_labels.tsv")),
        splits=splits,
        difficulties={
            row["accession"]: row["difficulty_stratum"]
            for row in read_tsv(dataset_dir / "difficulty_strata.tsv")
        },
        predictions=_principal_b4(read_tsv(predictions_path)),
        candidates=_candidate_index(read_tsv(candidates_path)),
    )
    if not examples:
        raise ValueError("no development calibration examples were produced")

    methods = ("platt_logistic", "isotonic_regression", "multifeature_l2_logistic")
    predictions: dict[str, list[dict[str, Any]]] = {method: [] for method in methods}
    for fold in range(folds):
        fit = [row for row in examples if fold_by_accession[row["accession"]] != fold]
        held_out = [row for row in examples if fold_by_accession[row["accession"]] == fold]
        if not fit or not held_out:
            raise ValueError(f"empty fit or held-out partition for fold {fold}")
        for method in methods:
            model, predictor = _fit_method(method, fit)
            for row in held_out:
                predictions[method].append(
                    {
                        **row,
                        "fold": fold,
                        "method": method,
                        "probability": predictor(model, row),
                    }
                )

    raw_rows = [dict(row, probability=float(row["top1_score"])) for row in examples]
    metrics: dict[str, dict[str, Any]] = {
        "clipped_raw_ranking_score": _evaluate(raw_rows, probability_key="probability")
    }
    for method in methods:
        metrics[method] = _evaluate(predictions[method], probability_key="probability")
        metrics[method]["bootstrap_95_ci"] = _bootstrap_intervals(
            predictions[method], probability_key="probability", replicates=2000, seed=seed
        )
    complexity = {method: index for index, method in enumerate(methods)}
    selected = min(
        methods,
        key=lambda method: (
            metrics[method]["log_loss"],
            metrics[method]["brier_score"],
            metrics[method]["expected_calibration_error"],
            complexity[method],
        ),
    )
    final_model, _predictor = _fit_method(selected, examples)
    model_payload = {
        "schema_version": 1,
        "status": "DEVELOPMENT_CV_SELECTED_NOT_VALIDATED",
        "method": selected,
        "folds": folds,
        "cluster_aware": True,
        "fit_example_count": len(examples),
        "fit_protein_count": len({row["accession"] for row in examples}),
        "parameters": final_model,
        "ranking_profile_sha256": file_sha256(ranking_profile_path),
        "validation_used": False,
        "test_used": False,
    }
    output_dir.mkdir(parents=True)
    write_json(output_dir / "development_cv_metrics.json", metrics)
    write_json(output_dir / "selected_calibrator.json", model_payload)
    rows = [row for method in methods for row in predictions[method]]
    write_tsv(
        output_dir / "out_of_fold_probabilities.tsv",
        rows,
        list(rows[0]),
    )
    write_tsv(
        output_dir / "calibration_exclusions.tsv",
        exclusions,
        ["accession", "split", "namespace", "reason"],
    )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "status": model_payload["status"],
        "selected_method": selected,
        "model_parameters_hash": stable_hash(model_payload),
        "inputs": {
            "predictions": _input(predictions_path),
            "candidates": _input(candidates_path),
            "gold_labels": _input(dataset_dir / "gold_labels.tsv"),
            "clusters": _input(dataset_dir / "cluster_membership.tsv"),
            "ranking_profile": _input(ranking_profile_path),
        },
        "validation_used": False,
        "test_used": False,
    }
    write_json(output_dir / "development_calibration_manifest.json", manifest)
    return {"manifest": manifest, "metrics": metrics, "model": model_payload}


def run_frozen_validation(
    *,
    predictions_path: Path,
    original_predictions_path: Path,
    candidates_path: Path,
    gold_labels_path: Path,
    dataset_dir: Path,
    ranking_profile_path: Path,
    calibrator_path: Path,
    contract_path: Path,
    freeze_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Evaluate one frozen ranking profile and calibrator without fitting."""
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite validation run: {output_dir}")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("status") != "PREDICTIONS_AND_MODELS_FROZEN_BEFORE_GOLD_REVEAL":
        raise ValueError("validation inputs were not frozen before gold reveal")
    frozen_inputs = freeze.get("inputs", {})
    for name, path in {
        "ranked_predictions": predictions_path,
        "candidate_evidence": candidates_path,
        "ranking_profile": ranking_profile_path,
        "selected_calibrator": calibrator_path,
    }.items():
        if frozen_inputs.get(name, {}).get("sha256") != file_sha256(path):
            raise ValueError(f"{name} does not match the pre-reveal freeze")

    splits = {row["accession"]: row["split"] for row in read_tsv(dataset_dir / "splits.tsv")}
    if set(splits.values()) != {"validation"}:
        raise ValueError("fresh validation requires a validation-only dataset")
    gold_rows = read_tsv(gold_labels_path)
    gold = _gold_sets(gold_rows)
    ranked_rows = read_tsv(predictions_path)
    examples, exclusions = _build_examples(
        gold=gold,
        splits=splits,
        difficulties={
            row["accession"]: row["difficulty_stratum"]
            for row in read_tsv(dataset_dir / "difficulty_strata.tsv")
        },
        predictions=_principal_b4(ranked_rows),
        candidates=_candidate_index(read_tsv(candidates_path)),
    )
    calibrator = json.loads(calibrator_path.read_text(encoding="utf-8"))
    if calibrator.get("ranking_profile_sha256") != file_sha256(ranking_profile_path):
        raise ValueError("calibrator was not fitted for the frozen ranking profile")
    predictor = _frozen_predictor(calibrator["method"], calibrator["parameters"])
    calibrated = [dict(row, probability=predictor(row)) for row in examples]
    raw = [dict(row, probability=float(row["top1_score"])) for row in examples]
    raw_metrics = _evaluate(raw, probability_key="probability")
    calibrated_metrics = _evaluate(calibrated, probability_key="probability")
    calibrated_metrics["confidence_group_wilson"] = _group_wilson(calibrated)
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    calibrated_metrics["bootstrap_95_ci"] = _bootstrap_intervals(
        calibrated,
        probability_key="probability",
        replicates=int(
            contract["uncertainty"]["aggregate_metric_confidence_interval"]["replicates"]
        ),
        seed=int(
            contract["uncertainty"]["aggregate_metric_confidence_interval"]["random_seed"]
        ),
    )
    gate = _method_gate(calibrated_metrics, raw_metrics, contract)
    eligible = sum(1 for accession, _namespace in gold if splits.get(accession) == "validation")
    coverage = len(examples) / eligible if eligible else 0.0
    minimums = contract["minimum_evaluation_size"]["validation"]
    sample_sufficient = (
        len(examples) >= int(minimums["evaluable_query_namespace_examples"])
        and len({row["accession"] for row in examples}) >= int(minimums["unique_proteins"])
        and coverage
        >= float(contract["minimum_evaluation_size"]["candidate_prediction_coverage"])
    )
    if not sample_sufficient:
        status = contract["acceptance_policy"]["insufficient_sample_status"]
    elif gate["passes_all_checks"]:
        status = contract["acceptance_policy"]["pass_status"]
    else:
        status = contract["acceptance_policy"]["failure_status"]

    sequence_rows = [
        row
        for row in read_tsv(original_predictions_path)
        if row["baseline"] == "B2_SEQUENCE_ONLY"
    ]
    per_query, aggregate, comparison = evaluate_function_predictions(
        [*sequence_rows, *ranked_rows],
        gold_rows,
        splits,
        bootstrap_replicates=10_000,
        seed=42,
    )
    evaluation = {
        "schema_version": 1,
        "status": status,
        "method": calibrator["method"],
        "parameters_refit": False,
        "validation_example_count": len(examples),
        "validation_protein_count": len({row["accession"] for row in examples}),
        "validation_candidate_coverage": coverage,
        "sample_size_gate_passed": sample_sufficient,
        "raw_score_metrics": raw_metrics,
        "frozen_calibrator_metrics": calibrated_metrics,
        "calibration_gate": gate,
        "ranking_primary_comparison": comparison,
        "test_gold_accessed": False,
        "claim_boundary": (
            "Exact top-1 EC/GO-MF correctness on a procedurally separated "
            "validation cohort."
        ),
    }
    output_dir.mkdir(parents=True)
    write_json(output_dir / "frozen_validation_evaluation.json", evaluation)
    write_tsv(output_dir / "ranking_per_query.tsv", per_query, list(per_query[0]))
    write_tsv(output_dir / "ranking_aggregate.tsv", aggregate, list(aggregate[0]))
    write_tsv(
        output_dir / "validation_probabilities.tsv",
        calibrated,
        [*list(examples[0]), "probability"],
    )
    write_tsv(
        output_dir / "calibration_exclusions.tsv",
        exclusions,
        ["accession", "split", "namespace", "reason"],
    )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "status": status,
        "validation_gold_accessed": True,
        "test_gold_accessed": False,
        "parameters_refit": False,
        "inputs": {
            "predictions": _input(predictions_path),
            "original_predictions": _input(original_predictions_path),
            "candidates": _input(candidates_path),
            "gold_labels": _input(gold_labels_path),
            "ranking_profile": _input(ranking_profile_path),
            "selected_calibrator": _input(calibrator_path),
            "contract": _input(contract_path),
            "pre_reveal_freeze": _input(freeze_path),
        },
    }
    write_json(output_dir / "frozen_validation_manifest.json", manifest)
    return {"evaluation": evaluation, "manifest": manifest}


def _frozen_predictor(
    method: str, model: dict[str, Any]
) -> Callable[[dict[str, Any]], float]:
    if method == "platt_logistic":
        return lambda row: _predict(model, float(row["top1_score"]))
    if method == "isotonic_regression":
        return lambda row: _predict_isotonic(model, float(row["top1_score"]))
    if method == "multifeature_l2_logistic":
        return lambda row: _predict_multifeature(model, row)
    raise ValueError(f"unsupported frozen calibration method: {method}")


def _fit_method(
    method: str, rows: list[dict[str, Any]]
) -> tuple[dict[str, Any], Callable[[dict[str, Any], dict[str, Any]], float]]:
    if method == "platt_logistic":
        return _fit_platt(rows), lambda model, row: _predict(
            model, float(row["top1_score"])
        )
    if method == "isotonic_regression":
        return _fit_isotonic(rows), lambda model, row: _predict_isotonic(
            model, float(row["top1_score"])
        )
    if method == "multifeature_l2_logistic":
        return _fit_multifeature_logistic(rows), _predict_multifeature
    raise ValueError(f"unsupported calibration method: {method}")


def _input(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": file_sha256(path)}
