from __future__ import annotations

from dualrag.literature.schemas import EvidencePacket
from dualrag.rag.schemas import ContextEvidence, GenerationContext

CONTEXT_BUILDER_VERSION = "phase5-context-v1"


def build_generation_context(
    packet: EvidencePacket,
    *,
    phase4_exit_status: str,
    phase4_exit_override: bool,
) -> GenerationContext:
    evidence: list[ContextEvidence] = []
    query = packet.query
    for index, candidate in enumerate([*query.candidate_ids, *query.candidate_labels], start=1):
        evidence.append(
            ContextEvidence(
                evidence_id=f"candidate:{index}",
                evidence_type="COMPUTATIONAL_CANDIDATE",
                label=candidate,
                details={
                    "cross_modal_status": query.cross_modal_status,
                    "source_biological_run_id": query.source_biological_run_id,
                    "source_parameters_hash": query.source_parameters_hash,
                },
                assessed_role="COMPUTATIONAL_PREDICTION",
            )
        )
    for homolog in query.selected_homologs:
        evidence.append(
            ContextEvidence(
                evidence_id=f"homolog:{homolog.accession}",
                evidence_type="SEQUENCE_HOMOLOG",
                label=homolog.accession,
                details=homolog.model_dump(mode="json"),
                assessed_role="INDIRECT_HOMOLOG_EVIDENCE",
            )
        )
    for reference in packet.biological_evidence:
        evidence.append(
            ContextEvidence(
                evidence_id=f"bio:{reference.modality}:{reference.candidate_id}",
                evidence_type=str(reference.modality),
                label=reference.candidate_id,
                details={
                    "score": reference.score,
                    "source_ids": reference.source_ids,
                    "run_id": reference.run_id,
                    "parameters_hash": reference.parameters_hash,
                },
            )
        )
    for hit in packet.literature_hits:
        evidence.append(
            ContextEvidence(
                evidence_id=hit.hit_id,
                evidence_type="LITERATURE",
                label=hit.chunk.title,
                details={
                    "passage": hit.chunk.text,
                    "section": str(hit.chunk.section_type),
                    "entity_match": str(hit.entity_match),
                    "organism_match": str(hit.organism_match),
                    "primary_experiment": hit.is_primary_experiment,
                    "article_is_review": hit.chunk.article_is_review,
                },
                citation_id=hit.chunk.pmid or hit.chunk.pmcid or hit.chunk.doi,
                source_url=hit.chunk.source_url,
                assessed_role=str(hit.evidence_role),
            )
        )
    boundaries = list(packet.claim_boundaries)
    if phase4_exit_override:
        boundaries.append(
            "Phase 4 exit was explicitly bypassed. UNASSESSED literature may be described "
            "only as retrieved context, never as verified support or contradiction."
        )
    boundaries.extend(
        [
            "Confidence is not calibrated in Phase 5; emit NOT_CALIBRATED.",
            "Do not invent identifiers, citations, active sites, pathways, or experiments.",
            "Every scientific claim must cite one or more supplied evidence IDs.",
        ]
    )
    return GenerationContext(
        context_version=CONTEXT_BUILDER_VERSION,
        packet_id=packet.packet_id,
        query_id=query.query_id,
        query_accession=query.query_accession,
        protein_name=query.protein_name,
        organism=query.organism,
        cross_modal_status=query.cross_modal_status,
        candidate_functions=[*query.candidate_ids, *query.candidate_labels],
        alternatives=packet.alternative_hypotheses,
        evidence=evidence,
        claim_boundaries=boundaries,
        phase4_exit_status=phase4_exit_status,
        phase4_exit_override=phase4_exit_override,
    )
