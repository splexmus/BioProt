from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, read_tsv, stable_hash, write_json, write_tsv

CALIBRATION_VERSION = "phase6-platt-v1"
EXAMPLE_FIELDS = [
    "accession",
    "split",
    "namespace",
    "predicted_identifier",
    "gold_identifiers",
    "correct",
    "sample_weight",
    "top1_score",
    "top1_top2_margin",
    "calibrated_probability",
    "confidence_label",
    "modalities",
    "sequence_score",
    "structure_score",
    "structure_reliability_score",
    "agreement_reliability_score",
    "modality_support",
    "hit_support",
    "evidence_quality_score",
    "sequence_evidence_count",
    "structure_evidence_count",
    "cross_modal_status",
    "difficulty_stratum",
]


def run_confidence_calibration(
    *,
    predictions_path: Path,
    candidates_path: Path,
    gold_labels_path: Path,
    splits_path: Path,
    difficulty_path: Path,
    contract_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite calibration run: {output_dir}")
    output_dir.mkdir(parents=True)
    splits = {row["accession"]: row["split"] for row in read_tsv(splits_path)}
    difficulties = {
        row["accession"]: row["difficulty_stratum"] for row in read_tsv(difficulty_path)
    }
    gold = _gold_sets(read_tsv(gold_labels_path))
    predictions = _principal_b4(read_tsv(predictions_path))
    candidates = _candidate_index(read_tsv(candidates_path))
    examples, exclusions = _build_examples(
        gold=gold,
        splits=splits,
        difficulties=difficulties,
        predictions=predictions,
        candidates=candidates,
    )
    fit = [row for row in examples if row["split"] == "development"]
    validation = [row for row in examples if row["split"] == "validation"]
    if not fit or not validation:
        raise ValueError("calibration requires nonempty development and validation examples")

    model = _fit_platt(fit)
    for row in examples:
        probability = _predict(model, float(row["top1_score"]))
        row["calibrated_probability"] = probability
        row["confidence_label"] = _confidence_label(probability)

    raw_validation = _evaluate(validation, probability_key="top1_score")
    calibrated_validation = _evaluate(validation, probability_key="calibrated_probability")
    calibrated_development = _evaluate(fit, probability_key="calibrated_probability")
    reliability_rows = _reliability_rows(validation)
    write_tsv(output_dir / "calibration_examples.tsv", examples, EXAMPLE_FIELDS)
    write_tsv(
        output_dir / "calibration_exclusions.tsv",
        exclusions,
        ["accession", "split", "namespace", "reason"],
    )
    write_tsv(
        output_dir / "reliability_bins.tsv",
        reliability_rows,
        [
            "method",
            "bin_index",
            "lower",
            "upper",
            "example_count",
            "weight",
            "mean_probability",
            "observed_accuracy",
        ],
    )
    _write_reliability_svg(output_dir / "reliability_diagram.svg", reliability_rows)
    model_payload = {
        "schema_version": 1,
        "calibration_version": CALIBRATION_VERSION,
        "status": "DEVELOPMENT_PILOT_NOT_FOR_PRODUCTION",
        "target": "top1_exact_EC_or_GO_MF_correctness",
        "fit_split": "development",
        "evaluation_split": "validation",
        "test_split_used": False,
        **model,
        "confidence_labels": {
            "LOW": "p < 0.50",
            "MODERATE": "0.50 <= p < 0.75",
            "HIGH": "p >= 0.75",
        },
    }
    write_json(output_dir / "calibration_model.json", model_payload)
    evaluation = {
        "schema_version": 1,
        "calibration_version": CALIBRATION_VERSION,
        "status": "DEVELOPMENT_PILOT_NOT_FOR_PRODUCTION",
        "development": calibrated_development,
        "validation_raw_score_baseline": raw_validation,
        "validation_calibrated": calibrated_validation,
        "limitations": [
            "Only 51 development and 15 validation query-namespace examples are available.",
            "Validation metrics are descriptive and statistically unstable.",
            "The exposed test split was not used.",
            "Probability concerns exact top-1 EC/GO-MF correctness, not experimental truth.",
        ],
    }
    write_json(output_dir / "calibration_evaluation.json", evaluation)
    inputs = {
        "predictions": _input(predictions_path),
        "candidates": _input(candidates_path),
        "gold_labels": _input(gold_labels_path),
        "splits": _input(splits_path),
        "difficulty": _input(difficulty_path),
        "contract": _input(contract_path),
    }
    manifest = {
        "schema_version": 1,
        "calibration_version": CALIBRATION_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "DEVELOPMENT_PILOT_NOT_FOR_PRODUCTION",
        "development_example_count": len(fit),
        "validation_example_count": len(validation),
        "excluded_test_example_count": sum(1 for row in exclusions if row["split"] == "test"),
        "inputs": inputs,
        "outputs": {
            path.name: file_sha256(path)
            for path in sorted(output_dir.iterdir())
            if path.is_file() and path.name != "calibration_manifest.json"
        },
        "parameters_hash": stable_hash(model_payload),
        "claim_boundary": evaluation["limitations"],
    }
    write_json(output_dir / "calibration_manifest.json", manifest)
    return {"manifest": manifest, "evaluation": evaluation, "model": model_payload}


def _gold_sets(rows: list[dict[str, str]]) -> dict[tuple[str, str], set[str]]:
    result: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        if row.get("admissible_for_primary", "").lower() != "true":
            continue
        namespace = row["namespace"]
        if namespace not in {"EC", "GO_MF"}:
            continue
        identifier = row["identifier"]
        if namespace == "EC" and not identifier.startswith("EC:"):
            identifier = f"EC:{identifier}"
        result[(row["accession"], namespace)].add(identifier)
    return result


def _principal_b4(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    result: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["baseline"] != "B4_DUAL_DETERMINISTIC" or row["ablation"] != "ALL_MAPPINGS":
            continue
        if row["namespace"] not in {"EC", "GO_MF"}:
            continue
        result[(row["query_accession"], row["namespace"])].append(row)
    for values in result.values():
        values.sort(key=lambda row: int(row["rank"]))
    return result


def _candidate_index(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        if row["baseline"] != "B4_DUAL_DETERMINISTIC" or row["ablation"] != "ALL_MAPPINGS":
            continue
        result[(_accession(row["query_id"]), row["candidate_id"])] = row
    return result


def _build_examples(
    *,
    gold: dict[tuple[str, str], set[str]],
    splits: dict[str, str],
    difficulties: dict[str, str],
    predictions: dict[tuple[str, str], list[dict[str, str]]],
    candidates: dict[tuple[str, str], dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    examples: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    eligible_keys = [
        key for key in sorted(gold) if splits.get(key[0]) in {"development", "validation"}
    ]
    per_accession = defaultdict(int)
    for accession, _namespace in eligible_keys:
        if predictions.get((accession, _namespace)):
            per_accession[accession] += 1
    for (accession, namespace), identifiers in sorted(gold.items()):
        split = splits.get(accession, "UNKNOWN")
        if split == "test":
            exclusions.append(
                {
                    "accession": accession,
                    "split": split,
                    "namespace": namespace,
                    "reason": "EXPOSED_TEST_SPLIT_PROHIBITED",
                }
            )
            continue
        if split not in {"development", "validation"}:
            exclusions.append(
                {
                    "accession": accession,
                    "split": split,
                    "namespace": namespace,
                    "reason": "UNSUPPORTED_SPLIT",
                }
            )
            continue
        ranked = predictions.get((accession, namespace), [])
        if not ranked:
            exclusions.append(
                {
                    "accession": accession,
                    "split": split,
                    "namespace": namespace,
                    "reason": "NO_TOP1_PREDICTION",
                }
            )
            continue
        top = ranked[0]
        second_score = float(ranked[1]["score"]) if len(ranked) > 1 else 0.0
        candidate = candidates.get((accession, top["identifier"]))
        if candidate is None:
            raise ValueError(f"missing candidate row for {accession} {top['identifier']}")
        examples.append(
            {
                "accession": accession,
                "split": split,
                "namespace": namespace,
                "predicted_identifier": top["identifier"],
                "gold_identifiers": ";".join(sorted(identifiers)),
                "correct": top["identifier"] in identifiers,
                "sample_weight": 1.0 / per_accession[accession],
                "top1_score": float(top["score"]),
                "top1_top2_margin": float(top["score"]) - second_score,
                "calibrated_probability": None,
                "confidence_label": None,
                "modalities": top["modalities"],
                "sequence_score": _number(candidate.get("sequence_score")),
                "structure_score": _number(candidate.get("structure_score")),
                "structure_reliability_score": _number(
                    candidate.get("structure_reliability_score")
                ),
                "agreement_reliability_score": _number(
                    candidate.get("agreement_reliability_score")
                ),
                "modality_support": _number(candidate.get("modality_support")),
                "hit_support": _number(candidate.get("hit_support")),
                "evidence_quality_score": _number(candidate.get("evidence_quality_score")),
                "sequence_evidence_count": int(candidate.get("sequence_evidence_count") or 0),
                "structure_evidence_count": int(candidate.get("structure_evidence_count") or 0),
                "cross_modal_status": candidate.get("cross_modal_status", ""),
                "difficulty_stratum": difficulties.get(accession, "UNKNOWN"),
            }
        )
    return examples, exclusions


def _fit_platt(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["top1_score"]) for row in rows]
    weights = [float(row["sample_weight"]) for row in rows]
    labels = [1.0 if row["correct"] else 0.0 for row in rows]
    total_weight = sum(weights)
    mean = sum(w * x for w, x in zip(weights, values, strict=True)) / total_weight
    variance = sum(w * (x - mean) ** 2 for w, x in zip(weights, values, strict=True)) / total_weight
    scale = math.sqrt(variance) or 1.0
    standardized = [(x - mean) / scale for x in values]
    prevalence = sum(w * y for w, y in zip(weights, labels, strict=True)) / total_weight
    intercept = math.log((prevalence + 1e-6) / (1 - prevalence + 1e-6))
    slope = 0.0
    l2 = 1.0
    iterations = 0
    for step in range(1, 101):
        iterations = step
        probabilities = [_sigmoid(intercept + slope * x) for x in standardized]
        grad_i = sum(w * (p - y) for w, p, y in zip(weights, probabilities, labels, strict=True))
        grad_s = (
            sum(
                w * (p - y) * x
                for w, p, y, x in zip(weights, probabilities, labels, standardized, strict=True)
            )
            + l2 * slope
        )
        h_ii = sum(w * p * (1 - p) for w, p in zip(weights, probabilities, strict=True)) + 1e-9
        h_is = sum(
            w * p * (1 - p) * x
            for w, p, x in zip(weights, probabilities, standardized, strict=True)
        )
        h_ss = (
            sum(
                w * p * (1 - p) * x * x
                for w, p, x in zip(weights, probabilities, standardized, strict=True)
            )
            + l2
        )
        determinant = h_ii * h_ss - h_is * h_is
        delta_i = (h_ss * grad_i - h_is * grad_s) / determinant
        delta_s = (-h_is * grad_i + h_ii * grad_s) / determinant
        intercept -= delta_i
        slope -= delta_s
        if max(abs(delta_i), abs(delta_s)) < 1e-10:
            break
    return {
        "feature": "top1_score",
        "feature_mean": mean,
        "feature_scale": scale,
        "intercept": intercept,
        "slope": slope,
        "l2_penalty": l2,
        "iterations": iterations,
        "fit_example_count": len(rows),
        "fit_protein_count": len({row["accession"] for row in rows}),
        "fit_weighted_prevalence": prevalence,
    }


def _predict(model: dict[str, Any], score: float) -> float:
    standardized = (score - model["feature_mean"]) / model["feature_scale"]
    return _sigmoid(model["intercept"] + model["slope"] * standardized)


def _evaluate(rows: list[dict[str, Any]], *, probability_key: str) -> dict[str, Any]:
    probabilities = [_clip(float(row[probability_key])) for row in rows]
    labels = [1.0 if row["correct"] else 0.0 for row in rows]
    weights = [float(row["sample_weight"]) for row in rows]
    total = sum(weights)
    brier = (
        sum(w * (p - y) ** 2 for w, p, y in zip(weights, probabilities, labels, strict=True))
        / total
    )
    log_loss = (
        -sum(
            w * (y * math.log(p) + (1 - y) * math.log(1 - p))
            for w, p, y in zip(weights, probabilities, labels, strict=True)
        )
        / total
    )
    bins = _bins(rows, probability_key)
    ece = (
        sum(
            item["weight"] * abs(item["mean_probability"] - item["observed_accuracy"])
            for item in bins
        )
        / total
    )
    by_label: dict[str, dict[str, float | int]] = {}
    for name in ("LOW", "MODERATE", "HIGH"):
        selected = [
            (row, p)
            for row, p in zip(rows, probabilities, strict=True)
            if _confidence_label(p) == name
        ]
        label_weight = sum(float(row["sample_weight"]) for row, _p in selected)
        by_label[name] = {
            "example_count": len(selected),
            "weight": label_weight,
            "mean_probability": (
                sum(float(row["sample_weight"]) * p for row, p in selected) / label_weight
                if label_weight
                else 0.0
            ),
            "observed_accuracy": (
                sum(
                    float(row["sample_weight"]) * (1.0 if row["correct"] else 0.0)
                    for row, _p in selected
                )
                / label_weight
                if label_weight
                else 0.0
            ),
        }
    return {
        "example_count": len(rows),
        "protein_count": len({row["accession"] for row in rows}),
        "weighted_accuracy": sum(w * y for w, y in zip(weights, labels, strict=True)) / total,
        "brier_score": brier,
        "log_loss": log_loss,
        "expected_calibration_error": ece,
        "accuracy_by_confidence_label": by_label,
    }


def _bins(rows: list[dict[str, Any]], probability_key: str) -> list[dict[str, Any]]:
    result = []
    for index in range(5):
        lower, upper = index / 5, (index + 1) / 5
        selected = [
            row
            for row in rows
            if lower <= _clip(float(row[probability_key])) < upper
            or (index == 4 and _clip(float(row[probability_key])) == 1)
        ]
        weight = sum(float(row["sample_weight"]) for row in selected)
        result.append(
            {
                "bin_index": index + 1,
                "lower": lower,
                "upper": upper,
                "example_count": len(selected),
                "weight": weight,
                "mean_probability": (
                    sum(
                        float(row["sample_weight"]) * _clip(float(row[probability_key]))
                        for row in selected
                    )
                    / weight
                    if weight
                    else 0.0
                ),
                "observed_accuracy": (
                    sum(
                        float(row["sample_weight"]) * (1.0 if row["correct"] else 0.0)
                        for row in selected
                    )
                    / weight
                    if weight
                    else 0.0
                ),
            }
        )
    return result


def _reliability_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"method": method, **row}
        for method, key in (
            ("raw_score", "top1_score"),
            ("platt_calibrated", "calibrated_probability"),
        )
        for row in _bins(rows, key)
    ]


def _write_reliability_svg(path: Path, rows: list[dict[str, Any]]) -> None:
    points = [row for row in rows if row["method"] == "platt_calibrated" and row["example_count"]]
    coords = " ".join(
        f"{50 + 300 * row['mean_probability']:.1f},{350 - 300 * row['observed_accuracy']:.1f}"
        for row in points
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400"
 viewBox="0 0 400 400">
<rect width="400" height="400" fill="white"/>
<line x1="50" y1="350" x2="350" y2="50" stroke="#999" stroke-dasharray="5 5"/>
<line x1="50" y1="350" x2="350" y2="350" stroke="black"/>
<line x1="50" y1="350" x2="50" y2="50" stroke="black"/>
<polyline points="{coords}" fill="none" stroke="#2563eb" stroke-width="3"/>
<text x="160" y="390" font-family="sans-serif" font-size="14">Mean predicted probability</text>
<text x="18" y="230" transform="rotate(-90 18 230)" font-family="sans-serif"
 font-size="14">Observed accuracy</text>
<text x="110" y="25" font-family="sans-serif" font-size="16">Validation reliability</text>
</svg>\n'''
    path.write_text(svg, encoding="utf-8")


def _confidence_label(probability: float) -> str:
    if probability < 0.5:
        return "LOW"
    if probability < 0.75:
        return "MODERATE"
    return "HIGH"


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _clip(value: float) -> float:
    return min(max(value, 1e-9), 1 - 1e-9)


def _number(value: str | None) -> float | None:
    return float(value) if value else None


def _accession(query_id: str) -> str:
    fields = query_id.split("|")
    return fields[1] if len(fields) >= 3 and fields[0] in {"sp", "tr"} else query_id


def _input(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": file_sha256(path)}
