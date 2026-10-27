from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dualrag.literature.io import write_jsonl
from dualrag.literature.schemas import (
    EvidencePacket,
    EvidenceRole,
    FullTextStatus,
    LiteratureHit,
    LiteratureQuery,
    LiteratureSource,
    SectionType,
)
from dualrag.rag.context import build_generation_context
from dualrag.rag.ollama import OllamaClient, OllamaConfig
from dualrag.rag.pipeline import run_generation_pipeline
from dualrag.rag.schemas import (
    ClaimType,
    ContextEvidence,
    GroundedProteinReport,
    InferenceLevel,
    ReportClaim,
    ReportReference,
    VerificationStatus,
)
from dualrag.rag.verifier import verify_report

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _packet() -> EvidencePacket:
    query = LiteratureQuery(
        query_id="P01040",
        query_accession="P01040",
        protein_name="Cystatin-A",
        organism="Homo sapiens",
        candidate_ids=["GO:0004869"],
        candidate_labels=["cysteine-type endopeptidase inhibitor activity"],
        cross_modal_status="CONSENSUS",
        query_terms=["P01040", "Cystatin-A"],
        query_variants=['"Cystatin-A"'],
        query_builder_version="test",
        source_biological_run_id="run-1",
        source_parameters_hash="parameters",
        created_at=NOW,
    )
    hit = LiteratureHit.model_validate(
        {
            "hit_id": "P01040:chunk-1",
            "query_id": "P01040",
            "chunk": {
                "chunk_id": "chunk-1",
                "source_article_id": "PMID:1",
                "source": LiteratureSource.PUBMED,
                "pmid": "1",
                "title": "Human cystatin A",
                "article_is_review": False,
                "full_text_status": FullTextStatus.ABSTRACT_ONLY,
                "section_type": SectionType.TITLE_ABSTRACT,
                "text": "Human cystatin A inhibited a cysteine protease in an assay.",
                "start_character": 0,
                "end_character": 61,
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                "retrieved_at": NOW,
                "chunker_version": "test",
            },
            "rank": 1,
            "retrieval_score": 1,
            "retrieval_method": "hybrid",
            "retriever_version": "test",
            "query_terms": ["Cystatin-A"],
            "retrieved_at": NOW,
            "evidence_role": EvidenceRole.UNASSESSED,
        }
    )
    return EvidencePacket(
        packet_id="packet:run-1:P01040",
        query=query,
        literature_hits=[hit],
        claim_boundaries=["Putative function only."],
        created_at=NOW,
    )


def _report(
    *, inference: InferenceLevel = InferenceLevel.BACKGROUND_CONTEXT
) -> GroundedProteinReport:
    return GroundedProteinReport(
        report_id="report:P01040",
        query_id="P01040",
        title="Putative cystatin-A report",
        proposed_function="cysteine-type endopeptidase inhibitor activity",
        summary="The retrieved evidence is unassessed.",
        claims=[
            ReportClaim(
                claim_id="claim-1",
                claim_type=ClaimType.LITERATURE,
                text="A retrieved passage discusses cystatin-A inhibition.",
                inference_level=inference,
                evidence_ids=["P01040:chunk-1"],
            )
        ],
        uncertainty=["Phase 4 literature labels are not validated."],
        references=[
            ReportReference(
                evidence_id="P01040:chunk-1",
                citation_id="1",
                source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
            )
        ],
    )


def test_context_records_phase4_override_and_not_calibrated() -> None:
    context = build_generation_context(
        _packet(), phase4_exit_status="NOT_EVALUATED", phase4_exit_override=True
    )
    assert context.phase4_exit_override is True
    assert context.confidence_status == "NOT_CALIBRATED"
    assert any(item.assessed_role == "UNASSESSED" for item in context.evidence)
    assert any(item.evidence_id == "candidate:1" for item in context.evidence)


def test_verifier_rejects_unassessed_literature_as_direct_support() -> None:
    context = build_generation_context(
        _packet(), phase4_exit_status="NOT_EVALUATED", phase4_exit_override=True
    )
    verification = verify_report(
        _report(inference=InferenceLevel.DIRECT_EXPERIMENTAL_EVIDENCE), context
    )
    assert verification.status is VerificationStatus.REJECT_UNSUPPORTED_CLAIMS
    assert any(
        finding.code == "UNASSESSED_LITERATURE_OUTSIDE_BACKGROUND"
        for finding in verification.findings
    )


def test_verifier_warns_when_available_modality_is_not_discussed() -> None:
    context = build_generation_context(
        _packet(), phase4_exit_status="PASS", phase4_exit_override=False
    )
    context = context.model_copy(
        update={
            "evidence": [
                *context.evidence,
                ContextEvidence(
                    evidence_id="bio:sequence:T1",
                    evidence_type="SEQUENCE_RETRIEVAL_HIT",
                    label="Sequence target",
                    assessed_role="COMPUTATIONAL_PREDICTION",
                ),
            ]
        }
    )
    context = type(context).model_validate(context.model_dump())
    verification = verify_report(_report(), context)
    assert any(
        finding.code == "SEQUENCE_SUPPORT_NOT_DISCUSSED"
        for finding in verification.findings
    )


class _Response:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class _Session:
    def __init__(self, report: GroundedProteinReport):
        self.report = report
        self.last_payload: dict[str, object] | None = None

    def get(self, url: str, timeout: float) -> _Response:
        if url.endswith("/api/version"):
            return _Response({"version": "test"})
        return _Response({"models": [{"name": "test-model"}]})

    def post(self, url: str, json: dict[str, object], timeout: float) -> _Response:
        self.last_payload = json
        return _Response(
            {
                "message": {
                    "content": self.report.model_dump_json(),
                }
            }
        )


def test_ollama_adapter_requests_schema_constrained_json() -> None:
    session = _Session(_report())
    client = OllamaClient(OllamaConfig(model="test-model"), session=session)
    context = build_generation_context(
        _packet(), phase4_exit_status="NOT_EVALUATED", phase4_exit_override=True
    )
    report, _raw = client.generate_report(
        context=context,
        system_prompt="system",
        report_prompt="context={context_json}",
    )
    assert report.query_id == "P01040"
    assert report.claims[0].claim_id == "system:function-candidate"
    assert report.claims[0].inference_level is InferenceLevel.COMPUTATIONAL_PREDICTION
    assert report.claims[0].evidence_ids == ["candidate:2"]
    assert session.last_payload is not None
    assert isinstance(session.last_payload["format"], dict)
    assert session.last_payload["format"]["properties"]["proposed_function"]["enum"] == [
        "GO:0004869",
        "cysteine-type endopeptidase inhibitor activity",
    ]
    assert session.last_payload["options"] == {"temperature": 0.0, "seed": 42}


def test_ollama_adapter_adds_missing_biological_modality_claims() -> None:
    session = _Session(_report())
    client = OllamaClient(OllamaConfig(model="test-model"), session=session)
    context = build_generation_context(
        _packet(), phase4_exit_status="PASS", phase4_exit_override=False
    )
    context = context.model_copy(
        update={
            "evidence": [
                *context.evidence,
                ContextEvidence(
                    evidence_id="bio:sequence:T1",
                    evidence_type="SEQUENCE_RETRIEVAL_HIT",
                    label="Sequence target",
                    details={
                        "rank": 1,
                        "target_id": "T1",
                        "raw_metrics": {
                            "sequence_identity": 0.8,
                            "alignment_coverage": 0.9,
                        },
                    },
                    assessed_role="COMPUTATIONAL_PREDICTION",
                ),
                ContextEvidence(
                    evidence_id="bio:structure:1abc_A",
                    evidence_type="STRUCTURE_RETRIEVAL_HIT",
                    label="Structure target",
                    details={
                        "rank": 1,
                        "target_id": "1abc_A",
                        "raw_metrics": {
                            "tm_score": 0.7,
                            "query_coverage": 0.8,
                            "target_coverage": 0.9,
                        },
                    },
                    assessed_role="COMPUTATIONAL_PREDICTION",
                ),
            ]
        }
    )
    context = type(context).model_validate(context.model_dump())

    report, _raw = client.generate_report(
        context=context,
        system_prompt="system",
        report_prompt="context={context_json}",
    )

    by_id = {claim.claim_id: claim for claim in report.claims}
    assert by_id["system:sequence-top-hit"].evidence_ids == ["bio:sequence:T1"]
    assert "identity=0.8" in by_id["system:sequence-top-hit"].text
    assert by_id["system:structure-top-hit"].evidence_ids == ["bio:structure:1abc_A"]
    assert "TM-score=0.7" in by_id["system:structure-top-hit"].text


def test_pipeline_refuses_unvalidated_phase4_without_override(tmp_path: Path) -> None:
    run_dir = tmp_path / "phase4"
    run_dir.mkdir()
    packets = run_dir / "evidence_packets.jsonl"
    write_jsonl(packets, [_packet()])
    system = tmp_path / "system.txt"
    report = tmp_path / "report.txt"
    system.write_text("system", encoding="utf-8")
    report.write_text("{context_json}", encoding="utf-8")
    client = OllamaClient(OllamaConfig(model="test-model"), session=_Session(_report()))

    with pytest.raises(ValueError, match="Phase 4 exit status"):
        run_generation_pipeline(
            packets_path=packets,
            output_dir=tmp_path / "output",
            client=client,
            system_prompt_path=system,
            report_prompt_path=report,
        )


def test_pipeline_writes_experimental_override_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "phase4"
    run_dir.mkdir()
    packets = run_dir / "evidence_packets.jsonl"
    write_jsonl(packets, [_packet()])
    system = tmp_path / "system.txt"
    prompt = tmp_path / "report.txt"
    system.write_text("system", encoding="utf-8")
    prompt.write_text("{context_json}", encoding="utf-8")
    client = OllamaClient(OllamaConfig(model="test-model"), session=_Session(_report()))
    (run_dir / "phase4_exit_manifest.json").write_text(
        json.dumps(
            {
                "evaluation": {"status": "FAIL"},
                "phase5_development_transition": {
                    "status": "PASS_FOR_PHASE5_DEVELOPMENT"
                },
            }
        ),
        encoding="utf-8",
    )

    manifest = run_generation_pipeline(
        packets_path=packets,
        output_dir=tmp_path / "output",
        client=client,
        system_prompt_path=system,
        report_prompt_path=prompt,
        allow_unvalidated_phase4=True,
    )

    assert manifest["report_count"] == 1
    assert manifest["phase4_exit_override"] is True
    assert (
        manifest["phase4_development_transition_status"]
        == "PASS_FOR_PHASE5_DEVELOPMENT"
    )
    assert manifest["scientific_status"] == "EXPERIMENTAL_UNVALIDATED_PHASE4_OVERRIDE"
    assert manifest["verification_status_counts"] == {"PASS_WITH_WARNINGS": 1}
    assert (tmp_path / "output/reports/P01040.md").is_file()


def test_report_schema_rejects_calibrated_confidence_field() -> None:
    value = json.loads(_report().model_dump_json())
    value["confidence_score"] = 0.9
    with pytest.raises(ValueError):
        GroundedProteinReport.model_validate(value)
