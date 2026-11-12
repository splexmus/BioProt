"""Freeze and evaluate the saved recovery calibrator on a new sealed cohort."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from dualrag.benchmark.fresh_validation import freeze_fresh_validation_inputs
from dualrag.calibration.development import run_frozen_validation
from dualrag.calibration.pipeline import (
    _candidate_index,
    _prediction_feature_rows,
    _principal_b4,
)
from dualrag.calibration.scientific import _predict_multifeature
from dualrag.io import file_sha256, read_tsv, write_json, write_tsv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "run", "model", "ranking-profile", "gold-labels", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    model = json.loads(args.model.read_text())
    if model.get("method") != "logistic:0.01:1":
        raise ValueError("expected the preselected recovery calibrator")
    if file_sha256(args.model) != (
        "d3da7ad725816fa0c4a61ae5a66b7f275aec4e522d096a9bf2da311cd11c2ff9"
    ):
        raise ValueError("saved recovery model changed")
    baseline = json.loads(args.ranking_profile.read_text())
    actual = json.loads((args.run / "retrieval_summary.json").read_text())
    for key in (
        "fusion_weights",
        "fusion_mapping",
        "mapping_projection",
        "target_pool_k",
        "synonyms",
        "fusion_profile",
        "rerank_version",
        "fusion_version",
    ):
        if actual[key] != baseline[key]:
            raise ValueError(f"validation ranking contract differs for {key}")
    args.output.mkdir(parents=True)
    exported = dict(
        model,
        method="multifeature_l2_logistic",
        candidate_name=model["method"],
        source_model_sha256=file_sha256(args.model),
        ranking_profile_sha256=file_sha256(args.ranking_profile),
    )
    calibrator = args.output / "frozen_calibrator.json"
    write_json(calibrator, exported)
    features = _prediction_feature_rows(
        predictions=_principal_b4(read_tsv(args.run / "predictions.tsv")),
        candidates=_candidate_index(read_tsv(args.run / "ablation_candidates.tsv")),
    )
    probability_rows = [
        {
            "accession": accession,
            "namespace": namespace,
            "probability": _predict_multifeature(model["parameters"], row),
        }
        for (accession, namespace), row in sorted(features.items())
    ]
    values = [row["probability"] for row in probability_rows]
    if not values or not all(math.isfinite(p) and 0 <= p <= 1 for p in values):
        raise ValueError("invalid probabilities before gold reveal")
    if len(set(values)) < 2:
        raise ValueError("constant probabilities before gold reveal")
    probability_path = args.output / "pre_reveal_probabilities.tsv"
    write_tsv(probability_path, probability_rows, ["accession", "namespace", "probability"])
    freeze = args.output / "pre_reveal_freeze.json"
    contract = Path("config/calibration-evaluation-v2.yaml")
    freeze_fresh_validation_inputs(
        inputs={
            "ranked_predictions": args.run / "predictions.tsv",
            "candidate_evidence": args.run / "ablation_candidates.tsv",
            "ranking_profile": args.ranking_profile,
            "selected_calibrator": calibrator,
            "original_recovery_model": args.model,
            "contract": contract,
            "pipeline_queries": args.dataset / "queries.tsv",
            "probabilities": probability_path,
        },
        code_roots=[Path("src"), Path("scripts")],
        output_path=freeze,
    )
    result = run_frozen_validation(
        predictions_path=args.run / "predictions.tsv",
        original_predictions_path=args.run / "predictions.tsv",
        candidates_path=args.run / "ablation_candidates.tsv",
        gold_labels_path=args.gold_labels,
        dataset_dir=args.dataset,
        ranking_profile_path=args.ranking_profile,
        calibrator_path=calibrator,
        contract_path=contract,
        freeze_path=freeze,
        output_dir=args.output / "evaluation",
    )
    print(json.dumps(result["evaluation"], indent=2))


if __name__ == "__main__":
    main()
