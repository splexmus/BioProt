from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from dualrag.io import write_json
from dualrag.literature.io import write_jsonl
from dualrag.rag.review import build_review_table
from dualrag.rag.schemas import (
    GenerationContext,
    GroundedProteinReport,
    ReportClaim,
    ReportVerification,
)


def test_build_review_table_prefills_provenance_and_leaves_judgments_blank(
    tmp_path: Path,
) -> None:
    run = tmp_path / "run"
    (run / "contexts").mkdir(parents=True)
    (run / "reports").mkdir()
    context = GenerationContext(
        context_version="test",
        packet_id="packet:Q1",
        query_id="Q1",
        cross_modal_status="SEQUENCE_ONLY",
        evidence=[
            {
                "evidence_id": "bio:sequence:T1",
                "evidence_type": "SEQUENCE_RETRIEVAL_HIT",
                "label": "target",
            }
        ],
        claim_boundaries=["Putative."],
        phase4_exit_status="FAIL",
        phase4_exit_override=True,
    )
    report = GroundedProteinReport(
        report_id="report:Q1",
        query_id="Q1",
        title="Q1 report",
        proposed_function="function",
        summary="summary",
        claims=[
            ReportClaim(
                claim_id="sequence",
                claim_type="SEQUENCE",
                text="Sequence evidence exists.",
                inference_level="COMPUTATIONAL_PREDICTION",
                evidence_ids=["bio:sequence:T1"],
            )
        ],
        uncertainty=["uncertain"],
    )
    verification = ReportVerification(
        report_id="report:Q1",
        query_id="Q1",
        status="PASS_WITH_WARNINGS",
        findings=[],
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
        verifier_version="test",
    )
    write_json(run / "contexts/Q1.json", context.model_dump(mode="json"))
    (run / "reports/Q1.md").write_text("# Q1\n", encoding="utf-8")
    write_jsonl(run / "generated_reports.jsonl", [report])
    write_jsonl(run / "report_verifications.jsonl", [verification])
    write_json(run / "generation_manifest.json", {"report_count": 1})

    output = tmp_path / "review.tsv"
    manifest = build_review_table(run_dir=run, output_path=output)

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert manifest["report_count"] == 1
    assert rows[0]["query_id"] == "Q1"
    assert rows[0]["sequence_record_count"] == "1"
    assert rows[0]["structure_record_count"] == "0"
    assert rows[0]["structure_section_review"] == "NA"
    assert rows[0]["function_assessment"] == ""
    assert rows[0]["overall_decision"] == ""
    assert json.loads(output.with_suffix(".manifest.json").read_text())["output"]["sha256"]
