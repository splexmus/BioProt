from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from dualrag.config import FusionConfig
from dualrag.fusion.candidates import extract_contributions
from dualrag.models import (
    CandidateContribution,
    CandidateKind,
    CrossModalStatus,
    FunctionCandidate,
    ProteinQuery,
    SequenceEvidence,
    StructureEvidence,
)

KIND_PRIORITY = {
    CandidateKind.EC: 0,
    CandidateKind.GO: 1,
    CandidateKind.INTERPRO: 2,
    CandidateKind.PFAM: 3,
    CandidateKind.SUPFAM: 4,
    CandidateKind.ORTHOLOGOUS_GROUP: 5,
    CandidateKind.LABEL: 6,
}
FUNCTION_KINDS = {CandidateKind.EC, CandidateKind.GO, CandidateKind.LABEL}
CONFLICT_FIELDS = [
    "query_id",
    "cross_modal_status",
    "conflict_reason",
    "top_sequence_candidates",
    "top_structure_candidates",
    "sequence_provenance",
    "structure_provenance",
    "sequence_candidate_count",
    "structure_candidate_count",
    "reported_top_k",
    "run_id",
    "parameters_hash",
]


@dataclass(frozen=True)
class FusionResult:
    candidates: list[FunctionCandidate]
    summaries: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]


def fuse_candidates(
    queries: list[ProteinQuery],
    sequence_hits: list[SequenceEvidence],
    structure_hits: list[StructureEvidence],
    config: FusionConfig,
    *,
    run_id: str,
    parameters_hash: str,
) -> FusionResult:
    """Build, classify, and rank function candidates without hiding either modality."""
    contributions = extract_contributions(sequence_hits, structure_hits)
    candidates = _aggregate(contributions, config, run_id, parameters_hash)
    by_query: dict[str, list[FunctionCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_query[candidate.query_id].append(candidate)

    ordered: list[FunctionCandidate] = []
    summaries: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for query in queries:
        query_candidates = sorted(by_query[query.query_id], key=_candidate_sort_key)
        for rank, candidate in enumerate(query_candidates, start=1):
            candidate.rank = rank
        ordered.extend(query_candidates)
        summary = _summarize_query(
            query.query_id, query_candidates, config.version, run_id, parameters_hash
        )
        summaries.append(summary)
        if summary["cross_modal_status"] == CrossModalStatus.CONFLICT.value:
            conflicts.append(
                _conflict_row(
                    query.query_id,
                    query_candidates,
                    summary,
                    config.conflict_report_top_k,
                    run_id,
                    parameters_hash,
                )
            )
    return FusionResult(ordered, summaries, conflicts)


def _aggregate(
    contributions: list[CandidateContribution],
    config: FusionConfig,
    run_id: str,
    parameters_hash: str,
) -> list[FunctionCandidate]:
    grouped: dict[tuple[str, str], list[CandidateContribution]] = defaultdict(list)
    for contribution in contributions:
        grouped[(contribution.query_id, contribution.candidate_id)].append(contribution)

    candidates: list[FunctionCandidate] = []
    for (query_id, candidate_id), items in grouped.items():
        sequence_items = [item for item in items if item.modality == "sequence"]
        structure_items = [item for item in items if item.modality == "structure"]
        informative = any(item.informative for item in items)
        kind = items[0].candidate_kind
        status = _candidate_status(kind, informative, sequence_items, structure_items)
        sequence_score = _max_score(sequence_items)
        structure_score = _max_score(structure_items)
        agreement_bonus = {
            CrossModalStatus.CONSENSUS: 1.0,
            CrossModalStatus.PARTIAL_CONSENSUS: 0.5,
        }.get(status, 0.0)
        fused_score = (
            config.sequence_weight * (sequence_score or 0.0)
            + config.structure_weight * (structure_score or 0.0)
            + config.agreement_weight * agreement_bonus
        )
        candidates.append(
            FunctionCandidate(
                query_id=query_id,
                candidate_id=candidate_id,
                candidate_kind=kind,
                candidate_labels=sorted({item.candidate_label for item in items}),
                informative=informative,
                informativeness_reason="; ".join(
                    sorted({item.informativeness_reason for item in items})
                ),
                modalities=sorted({item.modality for item in items}),
                sequence_score=sequence_score,
                structure_score=structure_score,
                sequence_evidence_count=len({item.source_id for item in sequence_items}),
                structure_evidence_count=len({item.source_id for item in structure_items}),
                sequence_source_ids=sorted({item.source_id for item in sequence_items}),
                structure_source_ids=sorted({item.source_id for item in structure_items}),
                sequence_provenance=sorted({item.provenance for item in sequence_items}),
                structure_provenance=sorted({item.provenance for item in structure_items}),
                cross_modal_status=status,
                fused_score=round(fused_score, 6),
                fusion_version=config.version,
                run_id=run_id,
                parameters_hash=parameters_hash,
            )
        )
    return candidates


def _candidate_status(
    kind: CandidateKind,
    informative: bool,
    sequence_items: list[CandidateContribution],
    structure_items: list[CandidateContribution],
) -> CrossModalStatus:
    if not informative:
        return CrossModalStatus.INSUFFICIENT_EVIDENCE
    if sequence_items and structure_items:
        if kind in FUNCTION_KINDS:
            return CrossModalStatus.CONSENSUS
        return CrossModalStatus.PARTIAL_CONSENSUS
    if sequence_items:
        return CrossModalStatus.SEQUENCE_ONLY
    return CrossModalStatus.STRUCTURE_ONLY


def _summarize_query(
    query_id: str,
    candidates: list[FunctionCandidate],
    fusion_version: str,
    run_id: str,
    parameters_hash: str,
) -> dict[str, Any]:
    informative = [candidate for candidate in candidates if candidate.informative]
    sequence = [candidate for candidate in informative if candidate.sequence_score is not None]
    structure = [candidate for candidate in informative if candidate.structure_score is not None]
    shared = [
        candidate
        for candidate in informative
        if candidate.sequence_score is not None and candidate.structure_score is not None
    ]
    consensus = [
        candidate
        for candidate in shared
        if candidate.cross_modal_status is CrossModalStatus.CONSENSUS
    ]
    partial = [
        candidate
        for candidate in shared
        if candidate.cross_modal_status is CrossModalStatus.PARTIAL_CONSENSUS
    ]

    if consensus:
        status = CrossModalStatus.CONSENSUS
        reason = "both modalities support at least one specific function identifier or label"
    elif partial:
        status = CrossModalStatus.PARTIAL_CONSENSUS
        reason = "both modalities share family/domain evidence but no specific function candidate"
    elif sequence and structure:
        status = CrossModalStatus.CONFLICT
        reason = "both modalities are informative but support disjoint function candidates"
    elif sequence:
        status = CrossModalStatus.SEQUENCE_ONLY
        reason = "only the sequence channel has informative function candidates"
    elif structure:
        status = CrossModalStatus.STRUCTURE_ONLY
        reason = "only the structure channel has informative function candidates"
    else:
        status = CrossModalStatus.INSUFFICIENT_EVIDENCE
        reason = "neither modality has an informative function candidate"

    top = informative[0] if informative else (candidates[0] if candidates else None)
    return {
        "query_id": query_id,
        "cross_modal_status": status.value,
        "classification_reason": reason,
        "informative_candidate_count": len(informative),
        "unclear_candidate_count": len(candidates) - len(informative),
        "sequence_candidate_count": len(sequence),
        "structure_candidate_count": len(structure),
        "shared_candidate_count": len(shared),
        "sequence_provenance": ";".join(
            sorted({item for candidate in sequence for item in candidate.sequence_provenance})
        ),
        "structure_provenance": ";".join(
            sorted({item for candidate in structure for item in candidate.structure_provenance})
        ),
        "top_candidate_id": top.candidate_id if top else None,
        "top_candidate_labels": ";".join(top.candidate_labels) if top else None,
        "top_candidate_kind": top.candidate_kind.value if top else None,
        "top_candidate_score": top.fused_score if top else None,
        "fusion_version": fusion_version,
        "run_id": run_id,
        "parameters_hash": parameters_hash,
    }


def _conflict_row(
    query_id: str,
    candidates: list[FunctionCandidate],
    summary: dict[str, Any],
    top_k: int,
    run_id: str,
    parameters_hash: str,
) -> dict[str, Any]:
    sequence = _top_for_modality(candidates, "sequence", top_k)
    structure = _top_for_modality(candidates, "structure", top_k)
    return {
        "query_id": query_id,
        "cross_modal_status": CrossModalStatus.CONFLICT.value,
        "conflict_reason": summary["classification_reason"],
        "top_sequence_candidates": ";".join(item.candidate_id for item in sequence),
        "top_structure_candidates": ";".join(item.candidate_id for item in structure),
        "sequence_provenance": summary["sequence_provenance"],
        "structure_provenance": summary["structure_provenance"],
        "sequence_candidate_count": summary["sequence_candidate_count"],
        "structure_candidate_count": summary["structure_candidate_count"],
        "reported_top_k": top_k,
        "run_id": run_id,
        "parameters_hash": parameters_hash,
    }


def _top_for_modality(
    candidates: list[FunctionCandidate], modality: str, top_k: int
) -> list[FunctionCandidate]:
    score_field = "sequence_score" if modality == "sequence" else "structure_score"
    supported = [
        candidate
        for candidate in candidates
        if candidate.informative and getattr(candidate, score_field) is not None
    ]
    return sorted(
        supported,
        key=lambda candidate: (
            -(getattr(candidate, score_field) or 0.0),
            KIND_PRIORITY[candidate.candidate_kind],
            candidate.candidate_id,
        ),
    )[:top_k]


def _candidate_sort_key(candidate: FunctionCandidate) -> tuple[object, ...]:
    return (
        not candidate.informative,
        -candidate.fused_score,
        KIND_PRIORITY[candidate.candidate_kind],
        candidate.candidate_id,
    )


def _max_score(items: list[CandidateContribution]) -> float | None:
    return max((item.normalized_score for item in items), default=None)
