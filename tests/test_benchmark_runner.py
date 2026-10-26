from __future__ import annotations

from dataclasses import fields as dataclass_fields
from pathlib import Path

import pytest

from dualrag.benchmark.runner import (
    _read_acquisition_records,
    _read_sequence_evidence,
    _read_structure_evidence,
)
from dualrag.io import write_tsv
from dualrag.models import SequenceEvidence, StructureEvidence
from dualrag.structure.alphafold import AcquisitionRecord


def _write_dataclass_rows(path: Path, values: list[object], row_type: type[object]) -> None:
    write_tsv(
        path,
        [value.to_row() for value in values],  # type: ignore[attr-defined]
        [field.name for field in dataclass_fields(row_type)],
    )


def test_raw_evidence_round_trip_preserves_typed_fields(tmp_path: Path) -> None:
    sequence = SequenceEvidence(
        query_id="q",
        target_id="P1",
        tool="MMseqs2",
        tool_version="1",
        database="Swiss-Prot",
        database_version="1",
        sequence_identity=0.42,
        go_terms=["GO:0005524"],
        ec_numbers=["1.1.1.1"],
        normalized_score=0.8,
    )
    structure = StructureEvidence(
        query_id="q",
        target_structure_id="1abc-assembly1_A",
        target_uniprot_id="P1",
        tool="Foldseek",
        tool_version="1",
        database="PDB",
        database_version="1",
        alignment_length=100,
        query_coverage=0.5,
        experimental_structure=True,
        go_terms=["GO:0005524"],
        normalized_score=0.7,
    )
    acquisition = AcquisitionRecord(
        query_id="q",
        requested_uniprot_accession="P1",
        resolution_method="validated_query_id",
        api_base_url="https://example.test/api",
        request_url=None,
        http_status=404,
        alphafold_entry_id=None,
        model_version=None,
        structure_format="cif",
        source_structure_url=None,
        retrieved_at="2026-01-01T00:00:00+00:00",
        sha256=None,
        cache_path=None,
        status="NOT_FOUND",
        sequence_compatible=None,
    )

    sequence_path = tmp_path / "sequence.tsv"
    structure_path = tmp_path / "structure.tsv"
    acquisition_path = tmp_path / "acquisition.tsv"
    _write_dataclass_rows(sequence_path, [sequence], SequenceEvidence)
    _write_dataclass_rows(structure_path, [structure], StructureEvidence)
    _write_dataclass_rows(acquisition_path, [acquisition], AcquisitionRecord)

    restored_sequence = _read_sequence_evidence(sequence_path)[0]
    restored_structure = _read_structure_evidence(structure_path)[0]
    restored_acquisition = _read_acquisition_records(acquisition_path)[0]

    assert restored_sequence.go_terms == ["GO:0005524"]
    assert restored_sequence.sequence_identity == 0.42
    assert restored_structure.alignment_length == 100
    assert restored_structure.experimental_structure is True
    assert restored_acquisition.http_status == 404
    assert restored_acquisition.sequence_compatible is None


def test_raw_evidence_reuse_requires_preserved_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="raw evidence reuse requested"):
        _read_sequence_evidence(tmp_path / "missing.tsv")
