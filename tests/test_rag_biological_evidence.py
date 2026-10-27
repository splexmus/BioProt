from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dualrag.literature.io import read_jsonl, write_jsonl
from dualrag.literature.schemas import EvidencePacket, LiteratureQuery
from dualrag.rag.biological_evidence import enrich_evidence_packets
from dualrag.rag.context import build_generation_context
from dualrag.rag.render import render_markdown
from dualrag.rag.schemas import (
    ClaimType,
    GroundedProteinReport,
    InferenceLevel,
    ReportClaim,
    ReportVerification,
    VerificationStatus,
)


def _packet() -> EvidencePacket:
    return EvidencePacket(
        packet_id="packet:run:P1",
        query=LiteratureQuery(
            query_id="P1",
            query_accession="P1",
            protein_name="Protein one",
            organism="Example species",
            cross_modal_status="CONSENSUS",
            query_terms=["P1"],
            query_variants=["P1"],
            query_builder_version="test",
            source_biological_run_id="run-1",
            source_parameters_hash="parameters-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        literature_hits=[],
        claim_boundaries=["Putative function only."],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_enriches_packets_with_bounded_separate_modalities(tmp_path: Path) -> None:
    packets = tmp_path / "packets.jsonl"
    sequence = tmp_path / "sequence.tsv"
    structure = tmp_path / "structure.tsv"
    output = tmp_path / "enriched.jsonl"
    manifest = tmp_path / "manifest.json"
    write_jsonl(packets, [_packet()])
    _write_tsv(
        sequence,
        [
            {
                "query_id": "sp|P1|ONE_TEST",
                "target_id": target,
                "tool": "MMseqs2",
                "tool_version": "16",
                "database": "Swiss-Prot",
                "database_version": "2026_03",
                "sequence_identity": identity,
                "alignment_coverage": "0.9",
                "evalue": "1e-20",
                "bitscore": "100",
                "orthologous_group": "",
                "protein_name": f"Protein {target}",
                "go_terms": "GO:0000001",
                "ec_numbers": "1.1.1.1",
                "kegg_terms": "",
                "interpro_ids": "IPR000001",
                "pfam_ids": "PF00001",
                "source_accession": target,
                "normalized_score": score,
                "normalization_version": "seq-v1",
            }
            for target, identity, score in (
                ("T1", "0.8", "0.8"),
                ("T2", "0.7", "0.7"),
            )
        ],
    )
    _write_tsv(
        structure,
        [
            {
                "query_id": "sp|P1|ONE_TEST",
                "target_structure_id": "1abc_A",
                "target_uniprot_id": "U1",
                "tool": "Foldseek",
                "tool_version": "9",
                "database": "PDB",
                "database_version": "2025",
                "foldseek_evalue": "1e-8",
                "foldseek_score": "200",
                "tm_score": "0.7",
                "alignment_length": "90",
                "query_coverage": "0.8",
                "target_coverage": "0.9",
                "sequence_identity": "0.2",
                "protein_name": "Structural match",
                "go_terms": "GO:0000002",
                "ec_numbers": "",
                "interpro_ids": "IPR000002",
                "supfam_ids": "SSF1",
                "structure_source": "PDB",
                "experimental_structure": "true",
                "source_accession": "1abc",
                "normalized_score": "0.75",
                "normalization_version": "struct-v1",
            }
        ],
    )

    result = enrich_evidence_packets(
        packets_path=packets,
        sequence_evidence_path=sequence,
        structure_evidence_path=structure,
        output_path=output,
        manifest_path=manifest,
        max_per_modality=1,
    )

    enriched = read_jsonl(output, EvidencePacket)[0]
    assert [item.evidence_id for item in enriched.biological_evidence] == [
        "bio:sequence:T1",
        "bio:structure:1abc_A",
    ]
    assert enriched.biological_evidence[0].raw_metrics["sequence_identity"] == 0.8
    assert enriched.biological_evidence[1].raw_metrics["tm_score"] == 0.7
    assert enriched.biological_evidence[1].experimental_structure is True
    assert result["gold_labels_used"] is False
    assert json.loads(manifest.read_text())["modality_record_counts"] == {
        "SEQUENCE": 1,
        "STRUCTURE": 1,
    }

    context = build_generation_context(
        enriched, phase4_exit_status="FAIL", phase4_exit_override=True
    )
    biological = [item for item in context.evidence if item.evidence_id.startswith("bio:")]
    assert [item.evidence_type for item in biological] == [
        "SEQUENCE_RETRIEVAL_HIT",
        "STRUCTURE_RETRIEVAL_HIT",
    ]
    assert all(item.assessed_role == "COMPUTATIONAL_PREDICTION" for item in biological)

    report = GroundedProteinReport(
        report_id="report:P1",
        query_id="P1",
        title="Protein one report",
        proposed_function="putative function",
        summary="Sequence and structure retrieval provide computational support.",
        claims=[
            ReportClaim(
                claim_id="sequence-1",
                claim_type=ClaimType.SEQUENCE,
                text="The top sequence hit has high identity and coverage.",
                inference_level=InferenceLevel.COMPUTATIONAL_PREDICTION,
                evidence_ids=["bio:sequence:T1"],
            ),
            ReportClaim(
                claim_id="structure-1",
                claim_type=ClaimType.STRUCTURE,
                text="The top structure hit has a strong TM-score.",
                inference_level=InferenceLevel.COMPUTATIONAL_PREDICTION,
                evidence_ids=["bio:structure:1abc_A"],
            ),
        ],
        uncertainty=["Confidence is not calibrated."],
    )
    verification = ReportVerification(
        report_id="report:P1",
        query_id="P1",
        status=VerificationStatus.PASS,
        checked_at=datetime(2026, 1, 1, tzinfo=UTC),
        verifier_version="test",
    )
    rendered = render_markdown(report, verification, context)
    assert "## Sequence retrieval support" in rendered
    assert "sequence_identity=0.8" in rendered
    assert "## Structure retrieval support" in rendered
    assert "tm_score=0.7" in rendered
    assert "### Evidence-linked interpretation" in rendered


def test_rejects_more_than_ten_biological_records_per_packet(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at most 10"):
        enrich_evidence_packets(
            packets_path=tmp_path / "missing-packets",
            sequence_evidence_path=tmp_path / "missing-sequence",
            structure_evidence_path=tmp_path / "missing-structure",
            output_path=tmp_path / "output",
            manifest_path=tmp_path / "manifest",
            max_per_modality=6,
        )
