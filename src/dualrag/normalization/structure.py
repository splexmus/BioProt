from __future__ import annotations

from dualrag.models import StructureEvidence
from dualrag.normalization.common import clamp01, evalue_strength, saturating


def normalize(hit: StructureEvidence, version: str) -> StructureEvidence:
    """PoC heuristic feature, deliberately not a calibrated confidence value."""
    score = (
        0.35 * clamp01(hit.tm_score)
        + 0.25 * clamp01(hit.query_coverage)
        + 0.15 * clamp01(hit.target_coverage)
        + 0.15 * evalue_strength(hit.foldseek_evalue)
        + 0.10 * saturating(hit.foldseek_score, 200.0)
    )
    hit.normalized_score = round(score, 6)
    hit.normalization_version = version
    return hit
