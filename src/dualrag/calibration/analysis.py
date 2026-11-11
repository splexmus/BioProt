"""Phase 6 applicability and evidence diagnostics for ordinary analysis runs."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, read_tsv, write_json, write_tsv


def build_analysis_calibration_report(
    *, biological_dir: Path, output_dir: Path, model_path: Path | None = None
) -> dict[str, Any]:
    """Keep benchmark calibration distinct from native eggNOG/Foldseek evidence."""
    model = None
    if model_path is not None:
        payload = json.loads(model_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("status"), str):
            raise ValueError("calibration model must be an object with a status")
        model = {
            "path": str(model_path.resolve()),
            "sha256": file_sha256(model_path),
            "status": payload["status"],
            "method": payload.get("method") or payload.get("selected_method"),
        }
    output_dir.mkdir(parents=True)
    candidates = read_tsv(biological_dir / "function_candidates.tsv")
    summaries = read_tsv(biological_dir / "fusion_summary.tsv")
    assessments = []
    ranked_rows = []
    reason = (
        "The supplied cohort calibrator uses benchmark retrieval/ranking features. "
        "Native analyze candidates have a different retrieval and annotation contract; "
        "GO terms are not all guaranteed GO Molecular Function. No probability is transferable."
        if model
        else "No compatible scientifically validated analysis calibrator was supplied."
    )
    for summary in summaries:
        query = summary["query_id"]
        rows = sorted(
            [r for r in candidates if r["query_id"] == query],
            key=lambda r: (int(r["rank"]), r["candidate_id"]),
        )
        informative = [r for r in rows if r["informative"].lower() == "true"]
        top = informative[0] if informative else None
        assessment = {
            "query_id": query,
            "cross_modal_status": summary["cross_modal_status"],
            "decision": "REVIEW_REQUIRED" if top else "ABSTAIN",
            "decision_reason": "Informative candidates need expert review"
            if top
            else "No informative function candidate",
            "top_candidate_id": top["candidate_id"] if top else None,
            "confidence_status": "NOT_CALIBRATED",
            "calibrated_probability": None,
            "calibration_applicability": "INCOMPATIBLE_FEATURE_CONTRACT"
            if model
            else "MODEL_UNAVAILABLE",
            "calibration_reason": reason,
            "model": model,
            "trained_sufficiency_status": "NOT_APPLIED_INCOMPATIBLE_FEATURE_CONTRACT",
            "candidate_count": len(rows),
            "informative_candidate_count": len(informative),
        }
        assessments.append(assessment)
        for row in rows:
            score = float(row["rerank_score"])
            if not math.isfinite(score):
                raise ValueError("candidate ranking score must be finite")
            ranked_rows.append(
                {
                    "query_id": query,
                    "rank": row["rank"],
                    "candidate_id": row["candidate_id"],
                    "namespace": row["candidate_kind"],
                    "ranking_score": score,
                    "modalities": row["modalities"],
                    "informative": row["informative"],
                    "sequence_score": row["sequence_score"],
                    "structure_score": row["structure_score"],
                    "calibrated_probability": None,
                }
            )
    manifest = {
        "schema_version": 1,
        "stage": "PHASE6_ANALYSIS_APPLICABILITY",
        "confidence_status": "NOT_CALIBRATED",
        "calibration_gate_status": "FAIL_SCIENTIFIC_CALIBRATION_GATE",
        "model": model,
        "queries": assessments,
        "target": "Exact top-1 EC/GO-MF correctness; not LLM or literature truth",
        "gold_labels_used": False,
        "model_fitted": False,
        "inputs": {
            name: file_sha256(biological_dir / name)
            for name in ("function_candidates.tsv", "fusion_summary.tsv", "run_metadata.json")
        },
    }
    write_json(output_dir / "calibration_report.json", manifest)
    write_tsv(
        output_dir / "candidate_assessments.tsv",
        ranked_rows,
        [
            "query_id",
            "rank",
            "candidate_id",
            "namespace",
            "ranking_score",
            "modalities",
            "informative",
            "sequence_score",
            "structure_score",
            "calibrated_probability",
        ],
    )
    lines = [
        "# Phase 6 analysis report",
        "",
        "Confidence: **NOT_CALIBRATED**",
        "",
        manifest["target"],
        "",
        reason,
        "",
        "Training and Brier/log-loss/ECE evaluation require a labeled cohort.",
        "",
    ]
    if model:
        lines.extend(
            [f"Model status: `{model['status']}`", f"Model SHA-256: `{model['sha256']}`", ""]
        )
    for assessment in assessments:
        lines.extend(
            [
                f"## {assessment['query_id']}",
                "",
                f"- Decision: `{assessment['decision']}`",
                f"- Top informative candidate: `{assessment['top_candidate_id']}`",
                f"- Cross-modal state: `{assessment['cross_modal_status']}`",
                f"- Applicability: `{assessment['calibration_applicability']}`",
                "- Calibrated probability: unavailable",
                "- Trained evidence-sufficiency model: not applied",
                "",
            ]
        )
    (output_dir / "calibration_report.md").write_text("\n".join(lines), encoding="utf-8")
    return manifest
