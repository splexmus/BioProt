from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class CrossModalStatus(StrEnum):
    CONSENSUS = "CONSENSUS"
    PARTIAL_CONSENSUS = "PARTIAL_CONSENSUS"
    SEQUENCE_ONLY = "SEQUENCE_ONLY"
    STRUCTURE_ONLY = "STRUCTURE_ONLY"
    CONFLICT = "CONFLICT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class ProteinQuery:
    query_id: str
    sequence: str
    description: str | None = None

    def to_row(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "description": self.description,
            "sequence_length": len(self.sequence),
            "sequence": self.sequence,
        }


@dataclass
class SequenceEvidence:
    query_id: str
    target_id: str
    tool: str
    tool_version: str
    database: str
    database_version: str
    sequence_identity: float | None = None
    alignment_coverage: float | None = None
    evalue: float | None = None
    bitscore: float | None = None
    orthologous_group: str | None = None
    protein_name: str | None = None
    go_terms: list[str] = field(default_factory=list)
    ec_numbers: list[str] = field(default_factory=list)
    kegg_terms: list[str] = field(default_factory=list)
    interpro_ids: list[str] = field(default_factory=list)
    pfam_ids: list[str] = field(default_factory=list)
    raw_output_path: str = ""
    source_accession: str | None = None
    parameters_hash: str = ""
    run_id: str = ""
    normalized_score: float | None = None
    normalization_version: str = ""

    def to_row(self) -> dict[str, Any]:
        return _row(asdict(self))


@dataclass
class StructureEvidence:
    query_id: str
    target_structure_id: str
    target_uniprot_id: str | None
    tool: str
    tool_version: str
    database: str
    database_version: str
    foldseek_evalue: float | None = None
    foldseek_score: float | None = None
    tm_score: float | None = None
    alignment_length: int | None = None
    query_coverage: float | None = None
    target_coverage: float | None = None
    sequence_identity: float | None = None
    protein_name: str | None = None
    interpro_ids: list[str] = field(default_factory=list)
    supfam_ids: list[str] = field(default_factory=list)
    structure_source: str | None = None
    experimental_structure: bool | None = None
    raw_output_path: str = ""
    source_accession: str | None = None
    parameters_hash: str = ""
    run_id: str = ""
    normalized_score: float | None = None
    normalization_version: str = ""

    def to_row(self) -> dict[str, Any]:
        return _row(asdict(self))


def _row(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: ";".join(value) if isinstance(value, list) else value for key, value in values.items()
    }
