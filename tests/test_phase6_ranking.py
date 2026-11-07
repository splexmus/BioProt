from __future__ import annotations

from dualrag.benchmark.ranking import _rank


def _candidate(identifier: str, modalities: str, provenance: str, score: float) -> dict[str, str]:
    return {
        "query_id": "sp|P1|TEST",
        "candidate_id": identifier,
        "candidate_kind": "GO",
        "modalities": modalities,
        "mapping_provenance": provenance,
        "rerank_score": str(score),
        "sequence_source_ids": "S1" if "sequence" in modalities else "",
        "structure_source_ids": "T1" if "structure" in modalities else "",
    }


def test_ranking_profile_prefers_consensus_and_penalizes_domain_only() -> None:
    rows = [
        _candidate("GO:1", "structure", "DOMAIN_PROJECTION:INTERPRO2GO", 0.8),
        _candidate("GO:2", "sequence;structure", "DIRECT_STRUCTURE_TARGET", 0.7),
    ]
    predictions = _rank(
        rows,
        {
            "consensus_bonus": 0.1,
            "direct_structure_bonus": 0.05,
            "structure_only_penalty": 0.05,
            "domain_projection_penalty": 0.1,
            "max_structure_only_per_namespace": 2,
        },
    )

    assert predictions[0]["identifier"] == "GO:2"
    assert predictions[0]["rank"] == 1


def test_ranking_profile_caps_structure_only_candidates() -> None:
    rows = [
        _candidate(f"GO:{index}", "structure", "DIRECT_STRUCTURE_TARGET", 1 - index / 10)
        for index in range(5)
    ]
    predictions = _rank(
        rows,
        {
            "consensus_bonus": 0.0,
            "direct_structure_bonus": 0.0,
            "structure_only_penalty": 0.0,
            "domain_projection_penalty": 0.0,
            "max_structure_only_per_namespace": 2,
        },
    )

    assert len(predictions) == 2


def test_ranking_profile_can_anchor_sequence_top1() -> None:
    rows = [
        _candidate("GO:1", "sequence", "", 0.4),
        _candidate("GO:2", "sequence;structure", "DIRECT_STRUCTURE_TARGET", 0.9),
    ]
    predictions = _rank(
        rows,
        {
            "consensus_bonus": 0.0,
            "direct_structure_bonus": 0.0,
            "structure_only_penalty": 0.0,
            "domain_projection_penalty": 0.0,
            "max_structure_only_per_namespace": 2,
            "sequence_top1_anchor": True,
        },
        {("P1", "GO_MF"): "GO:1"},
    )

    assert [row["identifier"] for row in predictions] == ["GO:1", "GO:2"]
