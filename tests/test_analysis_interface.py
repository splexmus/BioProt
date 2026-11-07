from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dualrag.analysis import AnalysisError, run_analysis
from dualrag.config import load_config
from dualrag.literature.io import read_jsonl, write_jsonl
from dualrag.literature.schemas import EvidencePacket, LiteratureChunk
from dualrag.literature.vector_store import build_literature_index
from dualrag.rag.ollama import OllamaConfig
from dualrag.rag.schemas import (
    ClaimType,
    GroundedProteinReport,
    InferenceLevel,
    ReportClaim,
)

ROOT = Path(__file__).parents[1]


class FakeResponse:
    status_code = 200
    text = ">sp|P69905|HBA_HUMAN Hemoglobin subunit alpha\nMVLSPADK\n"


class FakeSession:
    def get(self, url: str, *, timeout: float) -> FakeResponse:
        assert url.endswith("/P69905.fasta")
        assert timeout == 30
        return FakeResponse()


class FakeOllamaClient:
    config = OllamaConfig(model="test-model")

    def version(self) -> str:
        return "test"

    def models(self) -> list[str]:
        return ["test-model"]

    def generate_report(self, *, context: Any, system_prompt: str, report_prompt: str):
        del system_prompt, report_prompt
        evidence_id = context.evidence[0].evidence_id
        function = context.candidate_functions[0] if context.candidate_functions else "unknown"
        report = GroundedProteinReport(
            report_id=f"report:{context.query_id}",
            query_id=context.query_id,
            title=f"Putative report for {context.query_id}",
            proposed_function=function,
            summary="Computational and unassessed literature evidence were retrieved.",
            claims=[
                ReportClaim(
                    claim_id="claim-1",
                    claim_type=ClaimType.LITERATURE,
                    text="A retrieved passage provides background context.",
                    inference_level=InferenceLevel.BACKGROUND_CONTEXT,
                    evidence_ids=[evidence_id],
                )
            ],
            uncertainty=["Confidence is not calibrated."],
        )
        return report, {"message": {"content": report.model_dump_json()}}


def test_analyze_fasta_runs_existing_pipeline_and_writes_summary(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    result = run_analysis(
        config=load_config(ROOT / "config/config.yaml"),
        output_dir=output,
        fasta_path=ROOT / "tests/fixtures/queries.fasta",
    )

    assert result["status"] == "COMPLETE"
    assert result["query_count"] == 5
    assert (output / "biological/function_candidates.tsv").is_file()
    assert "confidence NOT_CALIBRATED" in (output / "summary.md").read_text()
    manifest = json.loads((output / "input/input_manifest.json").read_text())
    assert manifest["source_type"] == "FASTA_FILE"


def test_uniprot_input_is_validated_before_pipeline(tmp_path: Path) -> None:
    config = load_config(ROOT / "config/config.yaml")
    result = run_analysis(
        config=config,
        output_dir=tmp_path / "analysis",
        uniprot_accession="P69905",
        session=FakeSession(),
    )
    manifest = json.loads(
        (tmp_path / "analysis/input/input_manifest.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "COMPLETE"
    assert manifest["requested_accession"] == "P69905"
    assert manifest["queries"][0]["resolved_accession"] == "P69905"
    assert json.loads((tmp_path / "analysis/status.json").read_text())["status"] == "COMPLETE"


def test_analyze_requires_exactly_one_input_and_refuses_overwrite(tmp_path: Path) -> None:
    config = load_config(ROOT / "config/config.yaml")
    with pytest.raises(AnalysisError, match="exactly one"):
        run_analysis(config=config, output_dir=tmp_path / "none")
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(AnalysisError, match="already exists"):
        run_analysis(
            config=config,
            output_dir=output,
            fasta_path=ROOT / "tests/fixtures/queries.fasta",
        )
    with pytest.raises(AnalysisError, match="exactly one"):
        run_analysis(
            config=config,
            output_dir=tmp_path / "both",
            fasta_path=ROOT / "tests/fixtures/queries.fasta",
            uniprot_accession="P69905",
        )


def test_analyze_local_literature_and_ollama_report(tmp_path: Path) -> None:
    chunks = tmp_path / "chunks.jsonl"
    write_jsonl(
        chunks,
        [
            LiteratureChunk(
                chunk_id="chunk-1",
                source_article_id="123",
                source="PUBMED",
                pmid="123",
                title="Synthetic protein experiment",
                full_text_status="ABSTRACT_ONLY",
                section_type="TITLE_ABSTRACT",
                text="Synthetic ATPase activity was measured in an assay.",
                start_character=0,
                end_character=52,
                source_url="https://pubmed.ncbi.nlm.nih.gov/123/",
                retrieved_at=datetime(2026, 11, 8, tzinfo=UTC),
                chunker_version="test",
            )
        ],
    )
    index = tmp_path / "literature.sqlite3"
    build_literature_index(chunks_path=chunks, index_path=index)

    output = tmp_path / "analysis"
    result = run_analysis(
        config=load_config(ROOT / "config/config.yaml"),
        output_dir=output,
        fasta_path=ROOT / "tests/fixtures/queries.fasta",
        literature="local",
        literature_index=index,
        literature_context=ROOT / "tests/fixtures/literature_query_context.tsv",
        report="ollama",
        allow_unvalidated_phase4=True,
        ollama_client=FakeOllamaClient(),
    )

    assert result["stages"] == {
        "biological": "COMPLETE",
        "literature": "COMPLETE",
        "report": "COMPLETE",
    }
    packets = read_jsonl(
        output / "literature/evidence_packets.biological-v1.jsonl", EvidencePacket
    )
    assert len(packets) == 5
    assert any(packet.biological_evidence for packet in packets)
    assert (output / "report/generation_manifest.json").is_file()
    summary = (output / "summary.md").read_text(encoding="utf-8")
    assert "Literature retrieval: complete" in summary
    assert "Ollama report: complete" in summary
