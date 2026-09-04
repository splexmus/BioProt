from __future__ import annotations

from collections import defaultdict
from typing import Any

from dualrag.fusion.agreement import compare
from dualrag.models import ProteinQuery, SequenceEvidence, StructureEvidence


def merge_evidence(
    queries: list[ProteinQuery],
    sequence_hits: list[SequenceEvidence],
    structure_hits: list[StructureEvidence],
) -> list[dict[str, Any]]:
    by_sequence: dict[str, list[SequenceEvidence]] = defaultdict(list)
    by_structure: dict[str, list[StructureEvidence]] = defaultdict(list)
    for hit in sequence_hits:
        by_sequence[hit.query_id].append(hit)
    for hit in structure_hits:
        by_structure[hit.query_id].append(hit)

    merged: list[dict[str, Any]] = []
    for query in queries:
        sequences: list[SequenceEvidence | None] = by_sequence[query.query_id] or [None]
        structures: list[StructureEvidence | None] = by_structure[query.query_id] or [None]
        for sequence in sequences:
            for structure in structures:
                status, shared, reason = compare(sequence, structure)
                row: dict[str, Any] = {
                    "query_id": query.query_id,
                    "cross_modal_status": status.value,
                    "shared_identifiers": ";".join(shared),
                    "comparison_reason": reason,
                }
                row.update(_prefixed("seq", sequence.to_row() if sequence else {}))
                row.update(_prefixed("struct", structure.to_row() if structure else {}))
                merged.append(row)
    return merged


def _prefixed(prefix: str, row: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in row.items() if key != "query_id"}
