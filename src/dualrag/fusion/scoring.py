from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from dualrag.config import FusionConfig
from dualrag.fusion.candidates import extract_contributions
from dualrag.fusion.mapping import (
    MappingBundle,
    apply_exact_mappings,
    compatibility_pairs,
    load_mapping_bundle,
)
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
IDENTIFIER_QUALITY = {
    CandidateKind.EC: 1.0,
    CandidateKind.GO: 0.9,
    CandidateKind.INTERPRO: 0.75,
    CandidateKind.PFAM: 0.7,
    CandidateKind.SUPFAM: 0.7,
    CandidateKind.ORTHOLOGOUS_GROUP: 0.6,
    CandidateKind.LABEL: 0.5,
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
ALTERNATIVE_FIELDS = [
    "query_id",
    "rank",
    "candidate_id",
    "candidate_labels",
    "candidate_kind",
    "cross_modal_status",
    "fused_score",
    "evidence_quality_score",
    "rerank_score",
    "score_delta_from_top",
    "ambiguous_with_top",
    "modalities",
    "mapping_provenance",
    "run_id",
    "parameters_hash",
]


@dataclass(frozen=True)
class FusionResult:
    candidates: list[FunctionCandidate]
    summaries: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    alternatives: list[dict[str, Any]]
    audit: dict[str, Any]


def fuse_candidates(
    queries: list[ProteinQuery],
    sequence_hits: list[SequenceEvidence],
    structure_hits: list[StructureEvidence],
    config: FusionConfig,
    *,
    run_id: str,
    parameters_hash: str,
) -> FusionResult:
    """Build and rank auditable candidates; scores are not calibrated confidence."""
    bundle = load_mapping_bundle(config.mapping_path, config.synonym_path)
    raw = extract_contributions(sequence_hits, structure_hits)
    contributions, mapped_count = apply_exact_mappings(raw, bundle)
    candidates = _aggregate(contributions, config, run_id, parameters_hash)
    compatible_count = _apply_compatible_relations(candidates, bundle, config)
    by_query: dict[str, list[FunctionCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_query[candidate.query_id].append(candidate)
    ordered: list[FunctionCandidate] = []
    summaries: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    alternatives: list[dict[str, Any]] = []
    for query in queries:
        current = sorted(by_query[query.query_id], key=_candidate_sort_key)
        for rank, candidate in enumerate(current, start=1):
            candidate.rank = rank
        ordered.extend(current)
        summary = _summarize_query(query.query_id, current, config, run_id, parameters_hash)
        summaries.append(summary)
        alternatives.extend(_alternative_rows(current, config))
        if summary["cross_modal_status"] == CrossModalStatus.CONFLICT.value:
            conflicts.append(
                _conflict_row(
                    query.query_id,
                    current,
                    summary,
                    config.conflict_report_top_k,
                    run_id,
                    parameters_hash,
                )
            )
    audit = _audit(
        queries,
        ordered,
        summaries,
        conflicts,
        alternatives,
        bundle,
        len(raw),
        mapped_count,
        compatible_count,
        config,
        run_id,
        parameters_hash,
    )
    return FusionResult(ordered, summaries, conflicts, alternatives, audit)


def _aggregate(
    contributions: list[CandidateContribution],
    config: FusionConfig,
    run_id: str,
    parameters_hash: str,
) -> list[FunctionCandidate]:
    grouped: dict[tuple[str, str], list[CandidateContribution]] = defaultdict(list)
    for item in contributions:
        grouped[(item.query_id, item.candidate_id)].append(item)
    candidates: list[FunctionCandidate] = []
    for (query_id, candidate_id), items in grouped.items():
        seq = [item for item in items if item.modality == "sequence"]
        struct = [item for item in items if item.modality == "structure"]
        informative = any(item.informative for item in items)
        kind = items[0].candidate_kind
        status = _candidate_status(kind, informative, seq, struct)
        seq_score, struct_score = _max_score(seq), _max_score(struct)
        fused_score = _base_score(seq_score, struct_score, status, config)
        identifier_quality = IDENTIFIER_QUALITY[kind] if informative else 0.0
        modality_support = len({item.modality for item in items}) / 2
        hit_support = min(len({(item.modality, item.source_id) for item in items}) / 3, 1.0)
        quality = 0.5 * identifier_quality + 0.3 * modality_support + 0.2 * hit_support
        rerank = config.base_score_weight * fused_score + config.quality_weight * quality
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
                sequence_score=seq_score,
                structure_score=struct_score,
                sequence_evidence_count=len({item.source_id for item in seq}),
                structure_evidence_count=len({item.source_id for item in struct}),
                sequence_source_ids=sorted({item.source_id for item in seq}),
                structure_source_ids=sorted({item.source_id for item in struct}),
                sequence_provenance=sorted({item.provenance for item in seq}),
                structure_provenance=sorted({item.provenance for item in struct}),
                candidate_aliases=sorted(
                    {item.original_candidate_id or item.candidate_id for item in items}
                ),
                mapping_provenance=sorted(
                    {item.mapping_provenance for item in items if item.mapping_provenance}
                ),
                cross_modal_status=status,
                fused_score=round(fused_score, 6),
                identifier_quality=round(identifier_quality, 6),
                modality_support=round(modality_support, 6),
                hit_support=round(hit_support, 6),
                evidence_quality_score=round(quality, 6),
                rerank_score=round(rerank, 6),
                fusion_version=config.version,
                rerank_version=config.rerank_version,
                run_id=run_id,
                parameters_hash=parameters_hash,
            )
        )
    return candidates


def _apply_compatible_relations(
    candidates: list[FunctionCandidate], bundle: MappingBundle, config: FusionConfig
) -> int:
    pairs = compatibility_pairs(bundle)
    by_query: dict[str, dict[str, FunctionCandidate]] = defaultdict(dict)
    for candidate in candidates:
        by_query[candidate.query_id][candidate.candidate_id] = candidate
    matches = 0
    for current in by_query.values():
        for pair, provenance in pairs.items():
            if len(pair) != 2 or not pair.issubset(current):
                continue
            left, right = (current[item] for item in sorted(pair))
            if (
                not left.informative
                or not right.informative
                or not ({"sequence", "structure"} <= set(left.modalities + right.modalities))
            ):
                continue
            matches += 1
            for candidate in (left, right):
                candidate.cross_modal_status = CrossModalStatus.PARTIAL_CONSENSUS
                candidate.mapping_provenance = sorted(
                    set(candidate.mapping_provenance + provenance)
                )
                candidate.fused_score = round(
                    _base_score(
                        candidate.sequence_score,
                        candidate.structure_score,
                        candidate.cross_modal_status,
                        config,
                    ),
                    6,
                )
                candidate.rerank_score = round(
                    config.base_score_weight * candidate.fused_score
                    + config.quality_weight * candidate.evidence_quality_score,
                    6,
                )
    return matches


def _candidate_status(
    kind: CandidateKind,
    informative: bool,
    seq: list[CandidateContribution],
    struct: list[CandidateContribution],
) -> CrossModalStatus:
    if not informative:
        return CrossModalStatus.INSUFFICIENT_EVIDENCE
    if seq and struct:
        return (
            CrossModalStatus.CONSENSUS
            if kind in FUNCTION_KINDS
            else CrossModalStatus.PARTIAL_CONSENSUS
        )
    return CrossModalStatus.SEQUENCE_ONLY if seq else CrossModalStatus.STRUCTURE_ONLY


def _base_score(
    seq: float | None, struct: float | None, status: CrossModalStatus, config: FusionConfig
) -> float:
    bonus = {CrossModalStatus.CONSENSUS: 1.0, CrossModalStatus.PARTIAL_CONSENSUS: 0.5}.get(
        status, 0.0
    )
    return (
        config.sequence_weight * (seq or 0.0)
        + config.structure_weight * (struct or 0.0)
        + config.agreement_weight * bonus
    )


def _summarize_query(
    query_id: str,
    candidates: list[FunctionCandidate],
    config: FusionConfig,
    run_id: str,
    parameters_hash: str,
) -> dict[str, Any]:
    informative = [item for item in candidates if item.informative]
    seq = [item for item in informative if item.sequence_score is not None]
    struct = [item for item in informative if item.structure_score is not None]
    shared = [
        item
        for item in informative
        if item.sequence_score is not None and item.structure_score is not None
    ]
    consensus = [item for item in shared if item.cross_modal_status is CrossModalStatus.CONSENSUS]
    partial = [
        item
        for item in informative
        if item.cross_modal_status is CrossModalStatus.PARTIAL_CONSENSUS
    ]
    if consensus:
        status, reason = (
            CrossModalStatus.CONSENSUS,
            "both modalities support at least one specific mapped or exact function candidate",
        )
    elif partial:
        status, reason = (
            CrossModalStatus.PARTIAL_CONSENSUS,
            "both modalities share or have a versioned compatible family/domain candidate",
        )
    elif seq and struct:
        status, reason = (
            CrossModalStatus.CONFLICT,
            "both modalities are informative but support disjoint candidates "
            "under configured mappings",
        )
    elif seq:
        status, reason = (
            CrossModalStatus.SEQUENCE_ONLY,
            "only the sequence channel has informative function candidates",
        )
    elif struct:
        status, reason = (
            CrossModalStatus.STRUCTURE_ONLY,
            "only the structure channel has informative function candidates",
        )
    else:
        status, reason = (
            CrossModalStatus.INSUFFICIENT_EVIDENCE,
            "neither modality has an informative function candidate",
        )
    top = informative[0] if informative else (candidates[0] if candidates else None)
    return {
        "query_id": query_id,
        "cross_modal_status": status.value,
        "classification_reason": reason,
        "informative_candidate_count": len(informative),
        "unclear_candidate_count": len(candidates) - len(informative),
        "sequence_candidate_count": len(seq),
        "structure_candidate_count": len(struct),
        "shared_candidate_count": len(shared),
        "sequence_provenance": ";".join(
            sorted({x for item in seq for x in item.sequence_provenance})
        ),
        "structure_provenance": ";".join(
            sorted({x for item in struct for x in item.structure_provenance})
        ),
        "top_candidate_id": top.candidate_id if top else None,
        "top_candidate_labels": ";".join(top.candidate_labels) if top else None,
        "top_candidate_kind": top.candidate_kind.value if top else None,
        "top_candidate_score": top.rerank_score if top else None,
        "top_candidate_base_score": top.fused_score if top else None,
        "fusion_version": config.version,
        "rerank_version": config.rerank_version,
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
    seq, struct = (
        _top_for_modality(candidates, "sequence", top_k),
        _top_for_modality(candidates, "structure", top_k),
    )
    return {
        "query_id": query_id,
        "cross_modal_status": CrossModalStatus.CONFLICT.value,
        "conflict_reason": summary["classification_reason"],
        "top_sequence_candidates": ";".join(item.candidate_id for item in seq),
        "top_structure_candidates": ";".join(item.candidate_id for item in struct),
        "sequence_provenance": summary["sequence_provenance"],
        "structure_provenance": summary["structure_provenance"],
        "sequence_candidate_count": summary["sequence_candidate_count"],
        "structure_candidate_count": summary["structure_candidate_count"],
        "reported_top_k": top_k,
        "run_id": run_id,
        "parameters_hash": parameters_hash,
    }


def _alternative_rows(
    candidates: list[FunctionCandidate], config: FusionConfig
) -> list[dict[str, Any]]:
    informative = [item for item in candidates if item.informative][: config.alternatives_top_k]
    if not informative:
        return []
    top = informative[0].rerank_score
    return [
        {
            "query_id": item.query_id,
            "rank": item.rank,
            "candidate_id": item.candidate_id,
            "candidate_labels": ";".join(item.candidate_labels),
            "candidate_kind": item.candidate_kind.value,
            "cross_modal_status": item.cross_modal_status.value,
            "fused_score": item.fused_score,
            "evidence_quality_score": item.evidence_quality_score,
            "rerank_score": item.rerank_score,
            "score_delta_from_top": round(top - item.rerank_score, 6),
            "ambiguous_with_top": item.rank > 1
            and top - item.rerank_score <= config.ambiguity_margin,
            "modalities": ";".join(item.modalities),
            "mapping_provenance": ";".join(item.mapping_provenance),
            "run_id": item.run_id,
            "parameters_hash": item.parameters_hash,
        }
        for item in informative
    ]


def _audit(
    queries: list[ProteinQuery],
    candidates: list[FunctionCandidate],
    summaries: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    alternatives: list[dict[str, Any]],
    bundle: MappingBundle,
    contribution_count: int,
    mapped_count: int,
    compatible_count: int,
    config: FusionConfig,
    run_id: str,
    parameters_hash: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "parameters_hash": parameters_hash,
        "fusion_version": config.version,
        "rerank_version": config.rerank_version,
        "query_count": len(queries),
        "contribution_count": contribution_count,
        "candidate_count": len(candidates),
        "informative_candidate_count": sum(item.informative for item in candidates),
        "unclear_candidate_count": sum(not item.informative for item in candidates),
        "mapped_contribution_count": mapped_count,
        "compatible_cross_modal_pair_count": compatible_count,
        "conflict_count": len(conflicts),
        "alternative_row_count": len(alternatives),
        "status_counts": dict(
            sorted(Counter(row["cross_modal_status"] for row in summaries).items())
        ),
        "candidate_kind_counts": dict(
            sorted(Counter(item.candidate_kind.value for item in candidates).items())
        ),
        "mapping_inputs": list(bundle.inputs),
        "mapping_sources": [
            {"source": source, "source_version": version, "relation": relation}
            for source, version, relation in sorted(
                {
                    (item.source, item.source_version, item.relation.value)
                    for item in bundle.mappings
                }
            )
        ],
        "limitations": [
            "ranking scores are uncalibrated and are not probabilities or confidence",
            "only explicit versioned mappings and synonyms are applied",
            "absence of a mapping is not biological disagreement",
        ],
    }


def _top_for_modality(
    candidates: list[FunctionCandidate], modality: str, top_k: int
) -> list[FunctionCandidate]:
    field = "sequence_score" if modality == "sequence" else "structure_score"
    return sorted(
        [item for item in candidates if item.informative and getattr(item, field) is not None],
        key=lambda item: (
            -(getattr(item, field) or 0.0),
            KIND_PRIORITY[item.candidate_kind],
            item.candidate_id,
        ),
    )[:top_k]


def _candidate_sort_key(candidate: FunctionCandidate) -> tuple[object, ...]:
    return (
        not candidate.informative,
        -candidate.rerank_score,
        KIND_PRIORITY[candidate.candidate_kind],
        candidate.candidate_id,
    )


def _max_score(items: list[CandidateContribution]) -> float | None:
    return max((item.normalized_score for item in items), default=None)
