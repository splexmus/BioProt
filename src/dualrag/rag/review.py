from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from dualrag.io import file_sha256, write_json
from dualrag.literature.io import read_jsonl
from dualrag.rag.schemas import GenerationContext, GroundedProteinReport, ReportVerification

REVIEW_SCHEMA_VERSION = "phase5-human-review-v1"
FIELDS = [
    "reviewer",
    "review_date",
    "query_id",
    "report_title",
    "report_path",
    "report_sha256",
    "proposed_function",
    "cross_modal_status",
    "automated_verification",
    "verification_findings",
    "sequence_record_count",
    "structure_record_count",
    "literature_record_count",
    "sequence_claim_count",
    "structure_claim_count",
    "literature_claim_count",
    "function_assessment",
    "sequence_section_review",
    "structure_section_review",
    "cross_modal_handling",
    "literature_grounding",
    "citation_grounding",
    "unsupported_claims",
    "report_usefulness",
    "overall_decision",
    "notes",
]


def build_review_table(*, run_dir: Path, output_path: Path) -> dict[str, object]:
    run_dir = run_dir.resolve()
    output_path = output_path.resolve()
    manifest_path = output_path.with_suffix(".manifest.json")
    if output_path.exists() or manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite review artifact: {output_path}")
    reports_path = run_dir / "generated_reports.jsonl"
    verifications_path = run_dir / "report_verifications.jsonl"
    generation_manifest_path = run_dir / "generation_manifest.json"
    reports = read_jsonl(reports_path, GroundedProteinReport)
    verifications = {
        value.query_id: value for value in read_jsonl(verifications_path, ReportVerification)
    }
    rows: list[dict[str, object]] = []
    for report in sorted(reports, key=lambda value: value.query_id):
        context_path = run_dir / "contexts" / f"{report.query_id}.json"
        report_path = run_dir / "reports" / f"{report.query_id}.md"
        context = GenerationContext.model_validate_json(context_path.read_text(encoding="utf-8"))
        verification = verifications[report.query_id]
        rows.append(
            {
                "reviewer": "",
                "review_date": "",
                "query_id": report.query_id,
                "report_title": report.title,
                "report_path": str(report_path),
                "report_sha256": file_sha256(report_path),
                "proposed_function": report.proposed_function,
                "cross_modal_status": context.cross_modal_status,
                "automated_verification": str(verification.status),
                "verification_findings": ";".join(f.code for f in verification.findings),
                "sequence_record_count": _evidence_count(context, "SEQUENCE_RETRIEVAL_HIT"),
                "structure_record_count": _evidence_count(context, "STRUCTURE_RETRIEVAL_HIT"),
                "literature_record_count": _evidence_count(context, "LITERATURE"),
                "sequence_claim_count": _claim_count(report, "SEQUENCE"),
                "structure_claim_count": _claim_count(report, "STRUCTURE"),
                "literature_claim_count": _claim_count(report, "LITERATURE"),
                "function_assessment": "",
                "sequence_section_review": "",
                "structure_section_review": "NA"
                if _evidence_count(context, "STRUCTURE_RETRIEVAL_HIT") == 0
                else "",
                "cross_modal_handling": "",
                "literature_grounding": "",
                "citation_grounding": "",
                "unsupported_claims": "",
                "report_usefulness": "",
                "overall_decision": "",
                "notes": "",
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "schema_version": 1,
        "review_schema_version": REVIEW_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "source_run": str(run_dir),
        "report_count": len(rows),
        "human_judgment_columns": FIELDS[16:],
        "allowed_values": {
            "function_assessment": ["CORRECT", "PLAUSIBLE", "INCORRECT", "UNSURE"],
            "sequence_section_review": ["CORRECT", "PARTIAL", "INCORRECT", "NA"],
            "structure_section_review": ["CORRECT", "PARTIAL", "INCORRECT", "NA"],
            "cross_modal_handling": ["CORRECT", "PARTIAL", "INCORRECT"],
            "literature_grounding": ["CORRECT", "PARTIAL", "INCORRECT", "NA"],
            "citation_grounding": ["CORRECT", "PARTIAL", "INCORRECT", "NA"],
            "unsupported_claims": ["NONE", "MINOR", "MAJOR"],
            "report_usefulness": ["USEFUL", "PARTLY_USEFUL", "NOT_USEFUL"],
            "overall_decision": ["ACCEPT", "REVISE", "REJECT"],
        },
        "inputs": {
            "generated_reports": file_sha256(reports_path),
            "report_verifications": file_sha256(verifications_path),
            "generation_manifest": file_sha256(generation_manifest_path),
        },
        "output": {"path": str(output_path), "sha256": file_sha256(output_path)},
        "claim_boundary": "Human report-quality review does not experimentally validate functions.",
    }
    write_json(manifest_path, manifest)
    return manifest


def _evidence_count(context: GenerationContext, evidence_type: str) -> int:
    return sum(item.evidence_type == evidence_type for item in context.evidence)


def _claim_count(report: GroundedProteinReport, claim_type: str) -> int:
    return sum(claim.claim_type.value == claim_type for claim in report.claims)
