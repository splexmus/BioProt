"""Versioned literature acquisition, retrieval, packet, and evaluation components."""

from dualrag.literature.pipeline import run_literature_pipeline
from dualrag.literature.schemas import (
    ArticleMetadata,
    BiologicalEvidenceReference,
    EvidencePacket,
    LiteratureCandidate,
    LiteratureChunk,
    LiteratureHit,
    LiteratureQuery,
    SelectedHomolog,
)

__all__ = [
    "ArticleMetadata",
    "BiologicalEvidenceReference",
    "EvidencePacket",
    "LiteratureChunk",
    "LiteratureCandidate",
    "LiteratureHit",
    "LiteratureQuery",
    "SelectedHomolog",
    "run_literature_pipeline",
]
