"""Phase 6 applicability and evidence diagnostics for ordinary analysis runs."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, read_tsv, write_json, write_tsv


def load_validation_status() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[3] / "config/phase6-validation-status.json"
    if not path.is_file():
        return {"status": "NOT_EVALUATED", "scope": "No registered validation result"}
    result = json.loads(path.read_text(encoding="utf-8"))
    result["registry_sha256"] = file_sha256(path)
    return result


def validation_explanation(validation: dict[str, Any]) -> list[str]:
    lines = [
        f"Benchmark validation gate: **{validation['status']}**",
        "",
        f"Validated scope: {validation['scope']}",
        "",
    ]
    if "brier_score" not in validation:
        return lines
    lines.extend(
        [
            f"- Brier score: **{validation['brier_score']:.4f}** (limit 0.22). "
            "Mean squared probability error; lower is better.",
            f"- Log loss: **{validation['log_loss']:.4f}** (limit 0.65). "
            "Penalizes confident incorrect predictions; lower is better.",
            f"- ECE: **{validation['expected_calibration_error']:.4f}** (limit 0.10). "
            "Average confidence-versus-accuracy gap across bins; lower is better.",
            f"- Coverage: **{validation['coverage']:.1%}** "
            f"({validation['evaluated_case_count']} evaluated namespace cases).",
            f"- HIGH group accuracy: **{validation['high_accuracy']:.1%}**; "
            f"Wilson lower bound: **{validation['high_wilson_95_lower']:.1%}**.",
            "",
            "These are cohort calibration metrics, not this query's probability and not "
            "LLM or citation accuracy. Test evaluation remains pending.",
            "",
            "The ECE confidence interval extends above 0.10; the frozen gate uses point estimates.",
            "",
            f"Evaluation SHA-256: `{validation['evaluation_sha256']}`",
            "",
        ]
    )
    return lines


def build_analysis_calibration_report(
    *, biological_dir: Path, output_dir: Path, model_path: Path | None = None
) -> dict[str, Any]:
    """Keep benchmark calibration distinct from native eggNOG/Foldseek evidence."""
    validation = load_validation_status()
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
            "matches_registered_validation": file_sha256(model_path)
            in validation.get("validated_model_sha256", []),
        }
        model["validation_status"] = (
            validation["status"] if model["matches_registered_validation"] else "NOT_REGISTERED"
        )
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
            "probability_interpretation": (
                "A calibrated value would estimate the probability that the top-ranked "
                "EC/GO-MF identifier is exactly correct under the validated pipeline. "
                "It would not establish experimental function or LLM/citation correctness."
            ),
            "calibration_applicability": "INCOMPATIBLE_FEATURE_CONTRACT"
            if model
            else "MODEL_UNAVAILABLE",
            "calibration_reason": reason,
            "model": model,
            "benchmark_validation": validation,
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
        "calibration_gate_status": validation["status"],
        "benchmark_validation": validation,
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
        *validation_explanation(validation),
        manifest["target"],
        "",
        reason,
        "",
        "Training and Brier/log-loss/ECE evaluation require a labeled cohort.",
        "",
    ]
    if model:
        lines.extend(
            [
                f"Model artifact status at export: `{model['status']}`",
                f"Subsequent benchmark validation for this model: `{model['validation_status']}`",
                f"Model SHA-256: `{model['sha256']}`",
                "",
            ]
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
                "- Explanation: a calibrated probability estimates exact correctness of a "
                "top-ranked EC/GO-MF identifier. This native analysis uses a different "
                "feature pipeline; a validated value cannot be emitted for this query.",
                "- Trained evidence-sufficiency model: not applied",
                "",
            ]
        )
    (output_dir / "calibration_report.md").write_text("\n".join(lines), encoding="utf-8")
    return manifest
