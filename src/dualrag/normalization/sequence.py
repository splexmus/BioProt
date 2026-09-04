from __future__ import annotations

from dualrag.models import SequenceEvidence
from dualrag.normalization.common import clamp01, evalue_strength, saturating


def normalize(hit: SequenceEvidence, version: str) -> SequenceEvidence:
    """PoC heuristic feature, deliberately not a calibrated confidence value."""
    score = (
        0.35 * clamp01(hit.sequence_identity)
        + 0.30 * clamp01(hit.alignment_coverage)
        + 0.25 * evalue_strength(hit.evalue)
        + 0.10 * saturating(hit.bitscore, 200.0)
    )
    hit.normalized_score = round(score, 6)
    hit.normalization_version = version
    return hit
