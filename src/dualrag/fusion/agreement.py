from __future__ import annotations

import re

from dualrag.models import CrossModalStatus, SequenceEvidence, StructureEvidence


def compare(
    sequence: SequenceEvidence | None, structure: StructureEvidence | None
) -> tuple[CrossModalStatus, list[str], str]:
    if sequence is None and structure is None:
        return CrossModalStatus.INSUFFICIENT_EVIDENCE, [], "no hits in either channel"
    if structure is None:
        return CrossModalStatus.SEQUENCE_ONLY, [], "sequence hit has no paired structure hit"
    if sequence is None:
        return CrossModalStatus.STRUCTURE_ONLY, [], "structure hit has no paired sequence hit"

    sequence_domains = {f"InterPro:{x}" for x in sequence.interpro_ids} | {
        f"Pfam:{x}" for x in sequence.pfam_ids
    }
    structure_domains = {f"InterPro:{x}" for x in structure.interpro_ids} | {
        f"SUPFAM:{x}" for x in structure.supfam_ids
    }
    shared = sorted(sequence_domains & structure_domains)
    sequence_name = _normalize_label(sequence.protein_name)
    structure_name = _normalize_label(structure.protein_name)
    if sequence_name and sequence_name == structure_name:
        return CrossModalStatus.CONSENSUS, shared, "normalized function labels match exactly"
    if shared:
        return CrossModalStatus.PARTIAL_CONSENSUS, shared, "one or more domain identifiers overlap"
    return (
        CrossModalStatus.CONFLICT,
        [],
        "both channels are informative but no identifier/label overlaps",
    )


def _normalize_label(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).strip()
