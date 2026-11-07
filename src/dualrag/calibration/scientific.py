from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from dualrag.calibration.pipeline import (
    _build_examples,
    _candidate_index,
    _confidence_label,
    _evaluate,
    _fit_platt,
    _gold_sets,
    _predict,
    _principal_b4,
)
from dualrag.io import file_sha256, read_tsv, stable_hash, write_json, write_tsv

FEATURES = (
    "top1_score",
    "top1_top2_margin",
    "sequence_score",
    "structure_score",
    "sequence_max_score",
    "structure_max_score",
    "sequence_best_hit_rank",
    "structure_best_hit_rank",
    "structure_reliability_score",
    "agreement_reliability_score",
    "modality_support",
    "hit_support",
    "evidence_quality_score",
    "sequence_evidence_count",
    "structure_evidence_count",
    "direct_structure_support",
    "domain_projection_support",
    "consensus_support",
    "structure_only_support",
)


def run_scientific_calibration(
    *,
    predictions_path: Path,
    candidates_path: Path,
    gold_labels_path: Path,
    splits_path: Path,
    difficulty_path: Path,
    contract_path: Path,
    freeze_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Compare frozen calibration methods using development and validation only."""
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite calibration run: {output_dir}")
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    splits = {row["accession"]: row["split"] for row in read_tsv(splits_path)}
    if "test" in {row.get("split") for row in read_tsv(gold_labels_path)}:
        raise ValueError("scientific calibration input must not contain test gold labels")
    gold = _gold_sets(read_tsv(gold_labels_path))
    examples, exclusions = _build_examples(
        gold=gold,
        splits=splits,
        difficulties={
            row["accession"]: row["difficulty_stratum"]
            for row in read_tsv(difficulty_path)
        },
        predictions=_principal_b4(read_tsv(predictions_path)),
        candidates=_candidate_index(read_tsv(candidates_path)),
    )
    development = [row for row in examples if row["split"] == "development"]
    validation = [row for row in examples if row["split"] == "validation"]
    if not development or not validation:
        raise ValueError("nonempty development and validation examples are required")

    platt = _fit_platt(development)
    isotonic = _fit_isotonic(development)
    multifeature = _fit_multifeature_logistic(development)
    predictors: dict[str, Callable[[dict[str, Any]], float]] = {
        "clipped_raw_ranking_score": lambda row: min(max(float(row["top1_score"]), 0.0), 1.0),
        "platt_logistic": lambda row: _predict(platt, float(row["top1_score"])),
        "isotonic_regression": lambda row: _predict_isotonic(
            isotonic, float(row["top1_score"])
        ),
        "multifeature_l2_logistic": lambda row: _predict_multifeature(multifeature, row),
    }
    method_metrics: dict[str, dict[str, Any]] = {}
    probability_rows: list[dict[str, Any]] = []
    for method, predictor in predictors.items():
        evaluated = [dict(row, probability=predictor(row)) for row in validation]
        method_metrics[method] = _evaluate(evaluated, probability_key="probability")
        method_metrics[method]["confidence_group_wilson"] = _group_wilson(evaluated)
        method_metrics[method]["bootstrap_95_ci"] = _bootstrap_intervals(
            evaluated,
            probability_key="probability",
            replicates=int(contract["uncertainty"]["aggregate_metric_confidence_interval"]["replicates"]),
            seed=int(contract["uncertainty"]["aggregate_metric_confidence_interval"]["random_seed"]),
        )
        for row in evaluated:
            probability_rows.append(
                {
                    "accession": row["accession"],
                    "split": row["split"],
                    "namespace": row["namespace"],
                    "method": method,
                    "probability": row["probability"],
                    "confidence_label": _confidence_label(row["probability"]),
                    "correct": row["correct"],
                    "sample_weight": row["sample_weight"],
                }
            )

    eligible_validation = sum(
        1 for accession, _namespace in gold if splits.get(accession) == "validation"
    )
    coverage = len(validation) / eligible_validation if eligible_validation else 0.0
    gates = {
        method: _method_gate(
            method_metrics[method], method_metrics["clipped_raw_ranking_score"], contract
        )
        for method in ("platt_logistic", "isotonic_regression", "multifeature_l2_logistic")
    }
    minimums = contract["minimum_evaluation_size"]["validation"]
    sample_sufficient = (
        len(validation) >= int(minimums["evaluable_query_namespace_examples"])
        and len({row["accession"] for row in validation}) >= int(minimums["unique_proteins"])
        and coverage >= float(contract["minimum_evaluation_size"]["candidate_prediction_coverage"])
    )
    passing = [method for method, result in gates.items() if result["passes_all_checks"]]
    if not sample_sufficient:
        status = contract["acceptance_policy"]["insufficient_sample_status"]
        selected = None
    elif not passing:
        status = contract["acceptance_policy"]["failure_status"]
        selected = None
    else:
        selected = min(
            passing,
            key=lambda method: (
                method_metrics[method]["log_loss"],
                method_metrics[method]["brier_score"],
                method_metrics[method]["expected_calibration_error"],
                contract["model_selection"]["complexity_order"].index(method),
            ),
        )
        status = contract["acceptance_policy"]["pass_status"]

    model_payload = {
        "schema_version": 1,
        "status": status,
        "selected_method": selected,
        "test_split_used": False,
        "models": {
            "platt_logistic": platt,
            "isotonic_regression": isotonic,
            "multifeature_l2_logistic": multifeature,
        },
    }
    evaluation = {
        "schema_version": 1,
        "evaluation_version": contract["evaluation_version"],
        "status": status,
        "selected_method": selected,
        "development_example_count": len(development),
        "development_protein_count": len({row["accession"] for row in development}),
        "validation_example_count": len(validation),
        "validation_protein_count": len({row["accession"] for row in validation}),
        "validation_candidate_coverage": coverage,
        "sample_size_gate_passed": sample_sufficient,
        "method_metrics": method_metrics,
        "method_gates": gates,
        "test_split_used": False,
        "claim_boundary": "Calibration estimates exact top-1 identifier correctness only.",
    }
    output_dir.mkdir(parents=True)
    write_json(output_dir / "scientific_calibration_evaluation.json", evaluation)
    write_json(output_dir / "scientific_calibration_model.json", model_payload)
    write_tsv(
        output_dir / "validation_probabilities.tsv",
        probability_rows,
        [
            "accession",
            "split",
            "namespace",
            "method",
            "probability",
            "confidence_label",
            "correct",
            "sample_weight",
        ],
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
        "test_split_used": False,
        "inputs": {
            "predictions": _input(predictions_path),
            "candidates": _input(candidates_path),
            "gold_labels": _input(gold_labels_path),
            "splits": _input(splits_path),
            "difficulty": _input(difficulty_path),
            "contract": _input(contract_path),
            "contract_freeze": _input(freeze_path),
        },
        "model_sha256": file_sha256(output_dir / "scientific_calibration_model.json"),
        "model_parameters_hash": stable_hash(model_payload),
        "test_gold_accessed": False,
    }
    write_json(output_dir / "scientific_calibration_manifest.json", manifest)
    return {"evaluation": evaluation, "manifest": manifest, "model": model_payload}


def _fit_isotonic(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: float(row["top1_score"]))
    blocks: list[dict[str, float]] = []
    for row in ordered:
        weight = float(row["sample_weight"])
        blocks.append(
            {
                "lower": float(row["top1_score"]),
                "upper": float(row["top1_score"]),
                "weight": weight,
                "positive_weight": weight * (1.0 if row["correct"] else 0.0),
            }
        )
        while len(blocks) >= 2 and _block_mean(blocks[-2]) > _block_mean(blocks[-1]):
            right = blocks.pop()
            left = blocks.pop()
            blocks.append(
                {
                    "lower": left["lower"],
                    "upper": right["upper"],
                    "weight": left["weight"] + right["weight"],
                    "positive_weight": left["positive_weight"] + right["positive_weight"],
                }
            )
    return {
        "feature": "top1_score",
        "blocks": [
            {**block, "probability": _block_mean(block)} for block in blocks
        ],
        "fit_example_count": len(rows),
    }


def _block_mean(block: dict[str, float]) -> float:
    return block["positive_weight"] / block["weight"]


def _predict_isotonic(model: dict[str, Any], score: float) -> float:
    blocks = model["blocks"]
    for block in blocks:
        if score <= block["upper"]:
            return float(block["probability"])
    return float(blocks[-1]["probability"])


def _fit_multifeature_logistic(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matrix = np.asarray([[_feature_value(row, name) for name in FEATURES] for row in rows])
    weights = np.asarray([float(row["sample_weight"]) for row in rows])
    labels = np.asarray([1.0 if row["correct"] else 0.0 for row in rows])
    means = np.average(matrix, axis=0, weights=weights)
    variances = np.average((matrix - means) ** 2, axis=0, weights=weights)
    scales = np.sqrt(variances)
    scales[scales == 0] = 1.0
    standardized = (matrix - means) / scales
    coefficients = np.zeros(len(FEATURES))
    prevalence = float(np.average(labels, weights=weights))
    intercept = math.log((prevalence + 1e-6) / (1 - prevalence + 1e-6))
    l2, learning_rate = 1.0, 0.05
    iteration = 0
    for _iteration in range(1, 2001):
        iteration = _iteration
        logits = np.clip(intercept + standardized @ coefficients, -40, 40)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        residual = (probabilities - labels) * weights
        grad_intercept = float(residual.sum() / weights.sum())
        grad_coefficients = standardized.T @ residual / weights.sum() + l2 * coefficients
        intercept -= learning_rate * grad_intercept
        coefficients -= learning_rate * grad_coefficients
        if max(abs(grad_intercept), float(np.max(np.abs(grad_coefficients)))) < 1e-8:
            break
    return {
        "features": list(FEATURES),
        "feature_means": means.tolist(),
        "feature_scales": scales.tolist(),
        "intercept": intercept,
        "coefficients": coefficients.tolist(),
        "l2_penalty": l2,
        "iterations": iteration,
        "fit_example_count": len(rows),
    }


def _predict_multifeature(model: dict[str, Any], row: dict[str, Any]) -> float:
    values = np.asarray([_feature_value(row, name) for name in model["features"]])
    standardized = (values - np.asarray(model["feature_means"])) / np.asarray(
        model["feature_scales"]
    )
    value = float(model["intercept"] + standardized @ np.asarray(model["coefficients"]))
    return 1.0 / (1.0 + math.exp(-max(min(value, 40), -40)))


def _feature_value(row: dict[str, Any], name: str) -> float:
    value = row.get(name)
    return float(value) if value not in (None, "") else 0.0


def _method_gate(
    metrics: dict[str, Any], raw: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    thresholds = contract["acceptance_policy"]["overall_metrics"]
    for metric, threshold in thresholds.items():
        checks[f"{metric}_maximum"] = metrics[metric] <= float(threshold["maximum"])
        checks[f"{metric}_improvement"] = (
            raw[metric] - metrics[metric]
            >= float(threshold["minimum_improvement_over_raw"])
        )
    groups = metrics["accuracy_by_confidence_label"]
    group_contract = contract["acceptance_policy"]["confidence_groups"]
    for label, minimum in group_contract["minimum_examples"].items():
        checks[f"{label.lower()}_minimum_examples"] = groups[label]["example_count"] >= int(minimum)
    checks["monotonic_accuracy"] = (
        groups["LOW"]["observed_accuracy"]
        <= groups["MODERATE"]["observed_accuracy"]
        <= groups["HIGH"]["observed_accuracy"]
    )
    high = groups["HIGH"]
    lower = float(metrics["confidence_group_wilson"]["HIGH"]["lower_95"])
    checks["high_point_accuracy"] = high["observed_accuracy"] >= float(
        group_contract["high_confidence"]["minimum_point_accuracy"]
    )
    checks["high_wilson_lower"] = lower >= float(
        group_contract["high_confidence"]["minimum_wilson_95_lower_bound"]
    )
    return {
        "passes_all_checks": all(checks.values()),
        "checks": checks,
        "high_wilson_95_lower": lower,
    }


def _wilson_lower(successes: float, count: int, z: float = 1.959963984540054) -> float:
    if count == 0:
        return 0.0
    proportion = successes / count
    denominator = 1 + z * z / count
    centre = proportion + z * z / (2 * count)
    margin = z * math.sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count))
    return (centre - margin) / denominator


def _group_wilson(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for label in ("LOW", "MODERATE", "HIGH"):
        selected = [
            row for row in rows if _confidence_label(float(row["probability"])) == label
        ]
        successes = sum(1 for row in selected if row["correct"])
        result[label] = {
            "example_count": len(selected),
            "success_count": successes,
            "lower_95": _wilson_lower(successes, len(selected)),
        }
    return result


def _bootstrap_intervals(
    rows: list[dict[str, Any]], *, probability_key: str, replicates: int, seed: int
) -> dict[str, list[float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["accession"]].append(row)
    accessions = sorted(grouped)
    rng = random.Random(seed)
    values: dict[str, list[float]] = defaultdict(list)
    for _ in range(replicates):
        sampled = [rng.choice(accessions) for _item in accessions]
        bootstrap = [
            dict(row, accession=f"{index}:{accession}")
            for index, accession in enumerate(sampled)
            for row in grouped[accession]
        ]
        metrics = _evaluate(bootstrap, probability_key=probability_key)
        for metric in ("brier_score", "log_loss", "expected_calibration_error"):
            values[metric].append(float(metrics[metric]))
    return {
        metric: [float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))]
        for metric, samples in values.items()
    }


def _input(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": file_sha256(path)}
