from __future__ import annotations

import itertools
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from dualrag.benchmark.metrics import evaluate_function_predictions
from dualrag.io import file_sha256, read_tsv, stable_hash, write_json, write_tsv


def select_development_ranking_profile(
    *,
    candidates_path: Path,
    predictions_path: Path,
    dataset_dir: Path,
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite ranking run: {output_dir}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    queries = read_tsv(dataset_dir / "queries.tsv")
    accessions = [row["accession"] for row in queries]
    gold = read_tsv(dataset_dir / "gold_labels.tsv")
    clusters = {
        row["accession"]: row["cluster_representative"]
        for row in read_tsv(dataset_dir / "cluster_membership.tsv")
    }
    folds = {
        accession: int(stable_hash(clusters[accession])[:8], 16) % int(config["folds"])
        for accession in accessions
    }
    sequence_predictions = [
        row
        for row in read_tsv(predictions_path)
        if row["baseline"] == "B2_SEQUENCE_ONLY"
    ]
    sequence_top1 = _sequence_top1(sequence_predictions)
    candidates = [
        row
        for row in read_tsv(candidates_path)
        if row["baseline"] == "B4_DUAL_DETERMINISTIC"
        and row["ablation"] == "ALL_MAPPINGS"
        and row["informative"].casefold() == "true"
        and row["candidate_kind"] in {"EC", "GO"}
        and _accession(row["query_id"]) in folds
    ]
    profiles = _profiles(config["grid"])
    for profile in profiles:
        profile["sequence_top1_anchor"] = bool(
            config.get("sequence_top1_anchor", False)
        )
    results: list[dict[str, Any]] = []
    profile_predictions: dict[str, list[dict[str, object]]] = {}
    for profile in profiles:
        name = _profile_name(profile)
        dual_predictions = _rank(candidates, profile, sequence_top1)
        profile_predictions[name] = dual_predictions
        per_query, aggregate, _comparison = evaluate_function_predictions(
            [*sequence_predictions, *dual_predictions],
            gold,
            accessions,
            bootstrap_replicates=0,
            seed=int(config["seed"]),
        )
        metrics = _metric_index(aggregate)
        row: dict[str, Any] = {"profile": name, **profile}
        for baseline in ("B2_SEQUENCE_ONLY", "B4_DUAL_DETERMINISTIC"):
            for metric in (
                "function_recall_at_1",
                "function_recall_at_10",
                "precision_at_10",
                "mrr",
            ):
                row[f"{baseline}_{metric}"] = metrics[(baseline, metric)]
        row["recall_at_10_gain"] = (
            row["B4_DUAL_DETERMINISTIC_function_recall_at_10"]
            - row["B2_SEQUENCE_ONLY_function_recall_at_10"]
        )
        row["recall_at_1_loss"] = (
            row["B2_SEQUENCE_ONLY_function_recall_at_1"]
            - row["B4_DUAL_DETERMINISTIC_function_recall_at_1"]
        )
        row["mrr_loss"] = row["B2_SEQUENCE_ONLY_mrr"] - row["B4_DUAL_DETERMINISTIC_mrr"]
        row["passes_constraints"] = _passes(row, config["constraints"])
        row["fold_recall_at_10"] = json.dumps(
            [
                mean(
                    float(item["function_recall_at_10"])
                    for item in per_query
                    if item["baseline"] == "B4_DUAL_DETERMINISTIC"
                    and folds[str(item["query_accession"])] == fold
                )
                for fold in range(int(config["folds"]))
            ]
        )
        results.append(row)

    eligible = [row for row in results if row["passes_constraints"]]
    if not eligible:
        raise RuntimeError("no ranking profile passed the development constraints")
    selected = max(
        eligible,
        key=lambda row: (
            row["B4_DUAL_DETERMINISTIC_precision_at_10"],
            row["B4_DUAL_DETERMINISTIC_function_recall_at_10"],
            row["B4_DUAL_DETERMINISTIC_mrr"],
            row["max_structure_only_per_namespace"],
            -sum(
                float(row[key])
                for key in (
                    "consensus_bonus",
                    "direct_structure_bonus",
                    "structure_only_penalty",
                    "domain_projection_penalty",
                )
            ),
        ),
    )
    output_dir.mkdir(parents=True)
    selected_predictions = profile_predictions[str(selected["profile"])]
    prediction_fields = list(selected_predictions[0])
    write_tsv(output_dir / "selected_predictions.tsv", selected_predictions, prediction_fields)
    write_tsv(output_dir / "profile_search.tsv", results, list(results[0]))
    selected_profile = {
        "schema_version": 1,
        "profile_family": config["profile_family"],
        "status": "DEVELOPMENT_SELECTED_NOT_VALIDATED",
        "selected_at": datetime.now(UTC).isoformat(),
        "parameters": {
            **{key: selected[key] for key in _PROFILE_FIELDS},
            "sequence_top1_anchor": selected["sequence_top1_anchor"],
        },
        "development_metrics": {
            key: value
            for key, value in selected.items()
            if key.startswith("B2_")
            or key.startswith("B4_")
            or key.endswith("_gain")
            or key.endswith("_loss")
        },
        "fold_recall_at_10": json.loads(str(selected["fold_recall_at_10"])),
        "inputs": {
            "candidates": _input(candidates_path),
            "predictions": _input(predictions_path),
            "gold_labels": _input(dataset_dir / "gold_labels.tsv"),
            "cluster_membership": _input(dataset_dir / "cluster_membership.tsv"),
            "search_config": _input(config_path),
        },
        "validation_used": False,
        "test_used": False,
    }
    selected_profile["parameters_hash"] = stable_hash(selected_profile["parameters"])
    write_json(output_dir / "selected_profile.json", selected_profile)
    return selected_profile


def apply_frozen_ranking_profile(
    *,
    candidates_path: Path,
    profile_path: Path,
    output_dir: Path,
    sequence_predictions_path: Path | None = None,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite ranked predictions: {output_dir}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    parameters = profile["parameters"]
    candidates = [
        row
        for row in read_tsv(candidates_path)
        if row["baseline"] == "B4_DUAL_DETERMINISTIC"
        and row["ablation"] == "ALL_MAPPINGS"
        and row["informative"].casefold() == "true"
        and row["candidate_kind"] in {"EC", "GO"}
    ]
    sequence_top1: dict[tuple[str, str], str] = {}
    if parameters.get("sequence_top1_anchor"):
        if sequence_predictions_path is None:
            raise ValueError("sequence-anchored ranking requires sequence predictions")
        sequence_top1 = _sequence_top1(read_tsv(sequence_predictions_path))
    predictions = _rank(candidates, parameters, sequence_top1)
    output_dir.mkdir(parents=True)
    write_tsv(output_dir / "predictions.tsv", predictions, list(predictions[0]))
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "FROZEN_PROFILE_APPLIED_WITHOUT_GOLD",
        "prediction_count": len(predictions),
        "query_count": len({row["query_accession"] for row in predictions}),
        "profile": _input(profile_path),
        "candidates": _input(candidates_path),
        "sequence_predictions": (
            _input(sequence_predictions_path) if sequence_predictions_path else None
        ),
        "parameters_hash": stable_hash(parameters),
        "gold_labels_used": False,
    }
    write_json(output_dir / "ranking_application_manifest.json", manifest)
    return manifest


_PROFILE_FIELDS = (
    "consensus_bonus",
    "direct_structure_bonus",
    "structure_only_penalty",
    "domain_projection_penalty",
    "max_structure_only_per_namespace",
)


def _profiles(grid: dict[str, list[float]]) -> list[dict[str, float]]:
    return [
        dict(zip(_PROFILE_FIELDS, values, strict=True))
        for values in itertools.product(*(grid[field] for field in _PROFILE_FIELDS))
    ]


def _profile_name(profile: dict[str, float]) -> str:
    return stable_hash(profile)[:12]


def _rank(
    candidates: list[dict[str, str]],
    profile: dict[str, Any],
    sequence_top1: dict[tuple[str, str], str] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[tuple[float, dict[str, str]]]] = defaultdict(list)
    for row in candidates:
        namespace = "EC" if row["candidate_kind"] == "EC" else "GO_MF"
        score = float(row["rerank_score"])
        modalities = set(row["modalities"].split(";"))
        provenance = row["mapping_provenance"]
        if modalities == {"sequence", "structure"}:
            score += profile["consensus_bonus"]
        if "structure" in modalities and "DIRECT_STRUCTURE_TARGET" in provenance:
            score += profile["direct_structure_bonus"]
        if modalities == {"structure"}:
            score -= profile["structure_only_penalty"]
        if "DOMAIN_PROJECTION:INTERPRO2GO" in provenance:
            score -= profile["domain_projection_penalty"]
        grouped[(_accession(row["query_id"]), namespace)].append((score, row))
    predictions: list[dict[str, object]] = []
    for (accession, namespace), values in sorted(grouped.items()):
        ordered = sorted(
            values,
            key=lambda item: (-item[0], -float(item[1]["rerank_score"]), item[1]["candidate_id"]),
        )
        retained: list[tuple[float, dict[str, str]]] = []
        structure_only_count = 0
        for item in ordered:
            modalities = set(item[1]["modalities"].split(";"))
            if modalities == {"structure"}:
                if structure_only_count >= int(
                    profile["max_structure_only_per_namespace"]
                ):
                    continue
                structure_only_count += 1
            retained.append(item)
            if len(retained) == 10:
                break
        anchor = (sequence_top1 or {}).get((accession, namespace))
        if profile.get("sequence_top1_anchor") and anchor:
            anchored = next(
                (item for item in ordered if item[1]["candidate_id"] == anchor), None
            )
            if anchored is not None:
                retained = [
                    anchored,
                    *(item for item in retained if item[1]["candidate_id"] != anchor),
                ][:10]
        for rank, (score, row) in enumerate(retained, start=1):
            predictions.append(
                {
                    "baseline": "B4_DUAL_DETERMINISTIC",
                    "ablation": "ALL_MAPPINGS",
                    "query_accession": accession,
                    "namespace": namespace,
                    "identifier": row["candidate_id"],
                    "rank": rank,
                    "score": round(score, 6),
                    "modalities": row["modalities"],
                    "source_ids": ";".join(
                        value
                        for value in (row["sequence_source_ids"], row["structure_source_ids"])
                        if value
                    ),
                    "mapping_provenance": row["mapping_provenance"],
                }
            )
    return predictions


def _sequence_top1(rows: list[dict[str, str]]) -> dict[tuple[str, str], str]:
    return {
        (row["query_accession"], row["namespace"]): row["identifier"]
        for row in rows
        if row["baseline"] == "B2_SEQUENCE_ONLY"
        and row["namespace"] in {"EC", "GO_MF"}
        and int(row["rank"]) == 1
    }


def _metric_index(rows: list[dict[str, object]]) -> dict[tuple[str, str], float]:
    return {
        (str(row["baseline"]), str(row["metric"])): float(row["estimate"])
        for row in rows
    }


def _passes(row: dict[str, Any], constraints: dict[str, float]) -> bool:
    return (
        row["recall_at_10_gain"] >= constraints["minimum_recall_at_10_gain_over_sequence"]
        and row["recall_at_1_loss"] <= constraints["maximum_recall_at_1_loss_vs_sequence"]
        and row["mrr_loss"] <= constraints["maximum_mrr_loss_vs_sequence"]
    )


def _accession(query_id: str) -> str:
    fields = query_id.split("|")
    return fields[1] if len(fields) >= 3 else query_id


def _input(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": file_sha256(path)}
