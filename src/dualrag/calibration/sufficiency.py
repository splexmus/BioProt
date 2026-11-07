from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from dualrag.benchmark.metrics import evaluate_function_predictions
from dualrag.calibration.development import _fit_method, _frozen_predictor
from dualrag.calibration.pipeline import (
    _build_examples,
    _candidate_index,
    _confidence_label,
    _evaluate,
    _gold_sets,
    _prediction_feature_rows,
    _principal_b4,
)
from dualrag.calibration.scientific import (
    _bootstrap_intervals,
    _fit_multifeature_logistic,
    _group_wilson,
    _method_gate,
    _predict_multifeature,
)
from dualrag.io import file_sha256, read_tsv, stable_hash, write_json, write_tsv


def select_development_evidence_pipeline(
    *,
    predictions_path: Path,
    candidates_path: Path,
    dataset_dir: Path,
    ranking_profile_path: Path,
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite evidence pipeline: {output_dir}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    split_rows = read_tsv(dataset_dir / "splits.tsv")
    if {row["split"] for row in split_rows} != {"development"}:
        raise ValueError("evidence sufficiency selection requires development-only data")
    splits = {row["accession"]: row["split"] for row in split_rows}
    clusters = {
        row["accession"]: row["cluster_representative"]
        for row in read_tsv(dataset_dir / "cluster_membership.tsv")
    }
    folds = int(config["folds"])
    fold_by_accession = {
        accession: int(stable_hash(clusters[accession])[:8], 16) % folds
        for accession in splits
    }
    gold = _gold_sets(read_tsv(dataset_dir / "gold_labels.tsv"))
    examples, exclusions = _build_examples(
        gold=gold,
        splits=splits,
        difficulties={
            row["accession"]: row["difficulty_stratum"]
            for row in read_tsv(dataset_dir / "difficulty_strata.tsv")
        },
        predictions=_principal_b4(read_tsv(predictions_path)),
        candidates=_candidate_index(read_tsv(candidates_path)),
    )
    eligible_by_namespace = Counter(namespace for _accession, namespace in gold)
    oof: list[dict[str, Any]] = []
    for fold in range(folds):
        fit = [row for row in examples if fold_by_accession[row["accession"]] != fold]
        held = [row for row in examples if fold_by_accession[row["accession"]] == fold]
        model = _fit_multifeature_logistic(fit)
        oof.extend(
            dict(
                row,
                fold=fold,
                sufficiency_probability=_predict_multifeature(model, row),
            )
            for row in held
        )
    threshold_metrics = _select_threshold(
        oof,
        eligible_count=len(gold),
        eligible_by_namespace=eligible_by_namespace,
        minimum_coverage=float(config["minimum_candidate_coverage"]),
        minimum_namespace_coverage=float(config["minimum_namespace_coverage"]),
        minimum_proteins=int(config["minimum_accepted_proteins"]),
    )
    threshold = float(threshold_metrics["threshold"])
    accepted_oof = [
        row for row in oof if float(row["sufficiency_probability"]) >= threshold
    ]
    methods = tuple(config["calibration_methods"])
    calibration_predictions: dict[str, list[dict[str, Any]]] = {
        method: [] for method in methods
    }
    for fold in range(folds):
        fit = [row for row in accepted_oof if row["fold"] != fold]
        held = [row for row in accepted_oof if row["fold"] == fold]
        if not held:
            continue
        for method in methods:
            model, predictor = _fit_method(method, fit)
            calibration_predictions[method].extend(
                dict(row, probability=predictor(model, row)) for row in held
            )
    calibration_metrics = {
        method: _evaluate(rows, probability_key="probability")
        for method, rows in calibration_predictions.items()
    }
    complexity = {method: index for index, method in enumerate(methods)}
    selected_method = min(
        methods,
        key=lambda method: (
            calibration_metrics[method]["log_loss"],
            calibration_metrics[method]["brier_score"],
            calibration_metrics[method]["expected_calibration_error"],
            complexity[method],
        ),
    )
    sufficiency_model = _fit_multifeature_logistic(examples)
    final_accepted = [
        row
        for row in examples
        if _predict_multifeature(sufficiency_model, row) >= threshold
    ]
    calibration_model, _predictor = _fit_method(selected_method, final_accepted)
    bundle = {
        "schema_version": 1,
        "status": "DEVELOPMENT_SELECTED_NOT_VALIDATED",
        "pipeline_order": [
            "ranking",
            "evidence_sufficiency",
            "top1_or_abstain",
            "probability_calibration",
        ],
        "ranking_profile_sha256": file_sha256(ranking_profile_path),
        "sufficiency": {
            "method": "multifeature_l2_logistic",
            "minimum_probability": threshold,
            "parameters": sufficiency_model,
            "development_oof": threshold_metrics,
        },
        "calibration": {
            "method": selected_method,
            "parameters": calibration_model,
            "fit_example_count": len(final_accepted),
            "oof_metrics": calibration_metrics[selected_method],
        },
        "validation_used": False,
        "test_used": False,
    }
    output_dir.mkdir(parents=True)
    write_json(output_dir / "selected_evidence_pipeline.json", bundle)
    write_json(
        output_dir / "development_metrics.json",
        {
            "threshold_search": threshold_metrics,
            "calibration_methods": calibration_metrics,
            "selected_calibration_method": selected_method,
        },
    )
    write_tsv(output_dir / "out_of_fold_decisions.tsv", oof, list(oof[0]))
    write_tsv(
        output_dir / "calibration_exclusions.tsv",
        exclusions,
        ["accession", "split", "namespace", "reason"],
    )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "status": bundle["status"],
        "inputs": {
            "predictions": _input(predictions_path),
            "candidates": _input(candidates_path),
            "gold_labels": _input(dataset_dir / "gold_labels.tsv"),
            "clusters": _input(dataset_dir / "cluster_membership.tsv"),
            "ranking_profile": _input(ranking_profile_path),
            "config": _input(config_path),
        },
        "bundle_sha256": file_sha256(output_dir / "selected_evidence_pipeline.json"),
        "validation_used": False,
        "test_used": False,
    }
    write_json(output_dir / "development_manifest.json", manifest)
    return {"bundle": bundle, "metrics": threshold_metrics, "manifest": manifest}


def apply_evidence_pipeline(
    *,
    predictions_path: Path,
    candidates_path: Path,
    ranking_profile_path: Path,
    bundle_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite evidence application: {output_dir}")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if bundle["ranking_profile_sha256"] != file_sha256(ranking_profile_path):
        raise ValueError("evidence pipeline was not fitted for this ranking profile")
    ranked_rows = read_tsv(predictions_path)
    ranked = _principal_b4(ranked_rows)
    features = _prediction_feature_rows(
        predictions=ranked,
        candidates=_candidate_index(read_tsv(candidates_path)),
    )
    sufficiency = bundle["sufficiency"]
    calibrator = bundle["calibration"]
    calibrate = _frozen_predictor(calibrator["method"], calibrator["parameters"])
    accepted_keys: set[tuple[str, str]] = set()
    decisions: list[dict[str, Any]] = []
    for key, row in sorted(features.items()):
        probability = _predict_multifeature(sufficiency["parameters"], row)
        accepted = probability >= float(sufficiency["minimum_probability"])
        if accepted:
            accepted_keys.add(key)
        calibrated = calibrate(row) if accepted else None
        decisions.append(
            {
                **row,
                "sufficiency_probability": probability,
                "accepted": accepted,
                "abstention_reason": (
                    "" if accepted else "BELOW_DEVELOPMENT_SUFFICIENCY_THRESHOLD"
                ),
                "calibrated_probability": calibrated,
                "confidence_label": _confidence_label(calibrated) if accepted else "ABSTAIN",
            }
        )
    accepted_predictions = [
        row
        for row in ranked_rows
        if (row["query_accession"], row["namespace"]) in accepted_keys
    ]
    output_dir.mkdir(parents=True)
    write_tsv(output_dir / "predictions.tsv", accepted_predictions, list(ranked_rows[0]))
    write_tsv(output_dir / "evidence_decisions.tsv", decisions, list(decisions[0]))
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "DEVELOPMENT_PIPELINE_APPLIED_WITHOUT_GOLD",
        "decision_count": len(decisions),
        "accepted_count": len(accepted_keys),
        "abstained_count": len(decisions) - len(accepted_keys),
        "inputs": {
            "predictions": _input(predictions_path),
            "candidates": _input(candidates_path),
            "ranking_profile": _input(ranking_profile_path),
            "evidence_pipeline": _input(bundle_path),
        },
        "gold_labels_used": False,
    }
    write_json(output_dir / "application_manifest.json", manifest)
    return manifest


def evaluate_previous_benchmark(
    *,
    applied_dir: Path,
    original_predictions_path: Path,
    gold_labels_path: Path,
    dataset_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    return _evaluate_applied(
        applied_dir=applied_dir,
        original_predictions_path=original_predictions_path,
        gold_labels_path=gold_labels_path,
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        contract=None,
    )


def evaluate_frozen_evidence_validation(
    *,
    applied_dir: Path,
    original_predictions_path: Path,
    gold_labels_path: Path,
    dataset_dir: Path,
    ranking_profile_path: Path,
    bundle_path: Path,
    contract_path: Path,
    freeze_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("status") != "PREDICTIONS_AND_MODELS_FROZEN_BEFORE_GOLD_REVEAL":
        raise ValueError("validation predictions were not frozen before gold reveal")
    for name, path in {
        "accepted_predictions": applied_dir / "predictions.tsv",
        "evidence_decisions": applied_dir / "evidence_decisions.tsv",
        "ranking_profile": ranking_profile_path,
        "selected_evidence_pipeline": bundle_path,
        "calibration_contract": contract_path,
    }.items():
        if freeze.get("inputs", {}).get(name, {}).get("sha256") != file_sha256(path):
            raise ValueError(f"{name} does not match the pre-reveal freeze")
    return _evaluate_applied(
        applied_dir=applied_dir,
        original_predictions_path=original_predictions_path,
        gold_labels_path=gold_labels_path,
        dataset_dir=dataset_dir,
        output_dir=output_dir,
        contract=yaml.safe_load(contract_path.read_text(encoding="utf-8")),
    )


def _evaluate_applied(
    *,
    applied_dir: Path,
    original_predictions_path: Path,
    gold_labels_path: Path,
    dataset_dir: Path,
    output_dir: Path,
    contract: dict[str, Any] | None,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite evaluation: {output_dir}")
    gold_rows = read_tsv(gold_labels_path)
    gold = _gold_sets(gold_rows)
    splits = {row["accession"]: row["split"] for row in read_tsv(dataset_dir / "splits.tsv")}
    accessions = sorted(splits)
    dual = read_tsv(applied_dir / "predictions.tsv")
    sequence = [
        row
        for row in read_tsv(original_predictions_path)
        if row["baseline"] == "B2_SEQUENCE_ONLY"
    ]
    per_query, aggregate, comparison = evaluate_function_predictions(
        [*sequence, *dual], gold_rows, accessions, bootstrap_replicates=10_000, seed=42
    )
    decisions = read_tsv(applied_dir / "evidence_decisions.tsv")
    accepted: list[dict[str, Any]] = []
    abstained_correct = 0
    accepted_per_accession = Counter(
        row["accession"] for row in decisions if row["accepted"] == "true"
    )
    for row in decisions:
        key = (row["accession"], row["namespace"])
        if key not in gold:
            continue
        truth = gold[key]
        correct = row["predicted_identifier"] in truth
        if row["accepted"] != "true":
            abstained_correct += int(correct)
            continue
        accepted.append(
            {
                **row,
                "correct": correct,
                "sample_weight": 1.0 / accepted_per_accession[row["accession"]],
                "probability": float(row["calibrated_probability"]),
            }
        )
    calibration = _evaluate(accepted, probability_key="probability")
    calibration["confidence_group_wilson"] = _group_wilson(accepted)
    calibration["bootstrap_95_ci"] = _bootstrap_intervals(
        accepted, probability_key="probability", replicates=2000, seed=42
    )
    raw = [dict(row, raw_probability=float(row["top1_score"])) for row in accepted]
    raw_metrics = _evaluate(raw, probability_key="raw_probability")
    eligible = len(gold)
    abstained_count = eligible - len(accepted)
    coverage = len(accepted) / eligible if eligible else 0.0
    gate = _method_gate(calibration, raw_metrics, contract) if contract else None
    sample_sufficient = None
    if contract:
        minimums = contract["minimum_evaluation_size"]["validation"]
        sample_sufficient = (
            len(accepted) >= int(minimums["evaluable_query_namespace_examples"])
            and len({row["accession"] for row in accepted})
            >= int(minimums["unique_proteins"])
            and coverage
            >= float(contract["minimum_evaluation_size"]["candidate_prediction_coverage"])
        )
        if not sample_sufficient:
            status = contract["acceptance_policy"]["insufficient_sample_status"]
        elif gate and gate["passes_all_checks"]:
            status = contract["acceptance_policy"]["pass_status"]
        else:
            status = contract["acceptance_policy"]["failure_status"]
    else:
        status = "EXPLORATORY_PREVIOUS_BENCHMARK_REUSE"
    summary = {
        "schema_version": 1,
        "status": status,
        "confirmatory": contract is not None,
        "ranking_primary_comparison": comparison,
        "eligible_query_namespace_count": eligible,
        "accepted_count": len(accepted),
        "abstained_count": abstained_count,
        "accepted_coverage": coverage,
        "accepted_accuracy": calibration["weighted_accuracy"],
        "abstained_would_be_correct_rate": (
            abstained_correct / abstained_count if abstained_count else 0.0
        ),
        "calibration": calibration,
        "raw_score_metrics": raw_metrics,
        "calibration_gate": gate,
        "sample_size_gate_passed": sample_sufficient,
        "test_gold_accessed": False,
        "claim_boundary": (
            "Frozen prospective evaluation on a procedurally separated cohort."
            if contract
            else "Retrospective evaluation on previously revealed validation labels; "
            "not evidence for a new scientific pass."
        ),
    }
    output_dir.mkdir(parents=True)
    write_json(
        output_dir / ("frozen_validation_summary.json" if contract else "exploratory_summary.json"),
        summary,
    )
    write_tsv(output_dir / "ranking_per_query.tsv", per_query, list(per_query[0]))
    write_tsv(output_dir / "ranking_aggregate.tsv", aggregate, list(aggregate[0]))
    write_tsv(output_dir / "accepted_calibration.tsv", accepted, list(accepted[0]))
    return summary


def _select_threshold(
    rows: list[dict[str, Any]],
    *,
    eligible_count: int,
    eligible_by_namespace: Counter[str],
    minimum_coverage: float,
    minimum_namespace_coverage: float,
    minimum_proteins: int,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    thresholds = {0.0, *(float(row["sufficiency_probability"]) for row in rows)}
    for threshold in sorted(thresholds):
        accepted = [
            row for row in rows if float(row["sufficiency_probability"]) >= threshold
        ]
        namespace_counts = Counter(row["namespace"] for row in accepted)
        coverage = len(accepted) / eligible_count
        namespace_coverage = {
            namespace: namespace_counts[namespace] / count
            for namespace, count in eligible_by_namespace.items()
        }
        protein_count = len({row["accession"] for row in accepted})
        weight = sum(float(row["sample_weight"]) for row in accepted)
        accuracy = (
            sum(
                float(row["sample_weight"]) * (1.0 if row["correct"] else 0.0)
                for row in accepted
            )
            / weight
        )
        if (
            coverage >= minimum_coverage
            and min(namespace_coverage.values()) >= minimum_namespace_coverage
            and protein_count >= minimum_proteins
        ):
            candidates.append(
                {
                    "threshold": threshold,
                    "accepted_count": len(accepted),
                    "accepted_protein_count": protein_count,
                    "coverage": coverage,
                    "namespace_coverage": namespace_coverage,
                    "weighted_accuracy": accuracy,
                }
            )
    if not candidates:
        raise RuntimeError("no evidence sufficiency threshold satisfies coverage constraints")
    return max(
        candidates,
        key=lambda row: (row["weighted_accuracy"], row["threshold"], row["coverage"]),
    )


def _input(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": file_sha256(path)}
