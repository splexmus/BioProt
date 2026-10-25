from __future__ import annotations

import re

from dualrag.models import (
    CandidateContribution,
    CandidateKind,
    SequenceEvidence,
    StructureEvidence,
)

GENERIC_GO_TERMS = {
    "GO:0003674",  # molecular function
    "GO:0005575",  # cellular component
    "GO:0008150",  # biological process
}
GENERIC_LABELS = {
    "function unknown",
    "hypothetical protein",
    "protein",
    "uncharacterized protein",
    "unknown function",
    "unknown protein",
}
GENERIC_LABEL_PATTERNS = (
    re.compile(r"^hypothetical protein(?:\s+.+)?$"),
    re.compile(r"^uncharacterized protein(?:\s+.+)?$"),
    re.compile(r"^protein of unknown function(?:\s+.+)?$"),
    re.compile(r"^.+ domain containing protein$"),
    re.compile(r"^.+ family protein$"),
)


def extract_contributions(
    sequence_hits: list[SequenceEvidence], structure_hits: list[StructureEvidence]
) -> list[CandidateContribution]:
    """Convert heterogeneous hit annotations into explicit candidate assertions."""
    contributions: list[CandidateContribution] = []
    for hit in sequence_hits:
        values: list[tuple[CandidateKind, str]] = []
        values.extend((CandidateKind.EC, value) for value in hit.ec_numbers)
        values.extend((CandidateKind.GO, value) for value in hit.go_terms)
        values.extend((CandidateKind.INTERPRO, value) for value in hit.interpro_ids)
        values.extend((CandidateKind.PFAM, value) for value in hit.pfam_ids)
        values.extend(
            (CandidateKind.ORTHOLOGOUS_GROUP, value)
            for value in _split_orthologous_groups(hit.orthologous_group)
        )
        if hit.protein_name:
            values.append((CandidateKind.LABEL, hit.protein_name))
        contributions.extend(
            _from_values(
                query_id=hit.query_id,
                modality="sequence",
                source_id=hit.target_id,
                provenance=_provenance(
                    hit.tool, hit.tool_version, hit.database, hit.database_version
                ),
                score=hit.normalized_score,
                protein_name=hit.protein_name,
                values=values,
            )
        )

    for hit in structure_hits:
        values = []
        values.extend((CandidateKind.EC, value) for value in hit.ec_numbers)
        values.extend((CandidateKind.GO, value) for value in hit.go_terms)
        values.extend((CandidateKind.INTERPRO, value) for value in hit.interpro_ids)
        values.extend((CandidateKind.SUPFAM, value) for value in hit.supfam_ids)
        if hit.protein_name:
            values.append((CandidateKind.LABEL, hit.protein_name))
        contributions.extend(
            _from_values(
                query_id=hit.query_id,
                modality="structure",
                source_id=hit.target_structure_id,
                provenance=_provenance(
                    hit.tool, hit.tool_version, hit.database, hit.database_version
                ),
                score=hit.normalized_score,
                protein_name=hit.protein_name,
                values=values,
            )
        )
    return contributions


def _from_values(
    *,
    query_id: str,
    modality: str,
    source_id: str,
    provenance: str,
    score: float | None,
    protein_name: str | None,
    values: list[tuple[CandidateKind, str]],
) -> list[CandidateContribution]:
    contributions: list[CandidateContribution] = []
    seen: set[str] = set()
    for kind, raw_value in values:
        value = raw_value.strip()
        if not value:
            continue
        candidate_id = canonical_candidate_id(kind, value)
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        informative, reason = assess_informativeness(kind, value)
        contributions.append(
            CandidateContribution(
                query_id=query_id,
                candidate_id=candidate_id,
                candidate_kind=kind,
                candidate_label=(protein_name or value).strip(),
                modality=modality,
                source_id=source_id,
                provenance=provenance,
                normalized_score=score or 0.0,
                informative=informative,
                informativeness_reason=reason,
                original_candidate_id=candidate_id,
            )
        )
    return contributions


def canonical_candidate_id(kind: CandidateKind, value: str) -> str:
    normalized = value.strip()
    prefixes = {
        CandidateKind.EC: "EC",
        CandidateKind.GO: "GO",
        CandidateKind.INTERPRO: "INTERPRO",
        CandidateKind.PFAM: "PFAM",
        CandidateKind.SUPFAM: "SUPFAM",
        CandidateKind.ORTHOLOGOUS_GROUP: "OG",
    }
    if kind is CandidateKind.LABEL:
        return f"LABEL:{_normalize_label(normalized).replace(' ', '_')}"
    prefix = prefixes[kind]
    if normalized.casefold().startswith(f"{prefix.casefold()}:"):
        normalized = normalized.split(":", 1)[1]
    return f"{prefix}:{normalized}"


def assess_informativeness(kind: CandidateKind, value: str) -> tuple[bool, str]:
    if kind is CandidateKind.GO and canonical_candidate_id(kind, value) in GENERIC_GO_TERMS:
        return False, "root GO term is too broad for a function candidate"
    if kind is CandidateKind.LABEL:
        label = _normalize_label(value)
        if not label or label in GENERIC_LABELS:
            return False, "generic or missing free-text annotation"
        if any(pattern.fullmatch(label) for pattern in GENERIC_LABEL_PATTERNS):
            return False, "generic family/domain label without a specific function"
        return True, "specific normalized free-text annotation"
    if kind in {CandidateKind.EC, CandidateKind.GO}:
        return True, "controlled function identifier"
    return True, "controlled family or orthology identifier"


def _split_orthologous_groups(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _provenance(tool: str, tool_version: str, database: str, database_version: str) -> str:
    return f"{tool}@{tool_version}|{database}@{database_version}"
