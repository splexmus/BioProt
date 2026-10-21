from __future__ import annotations

from dualrag.config import FusionConfig
from dualrag.fusion.candidates import extract_contributions
from dualrag.fusion.scoring import fuse_candidates
from dualrag.models import ProteinQuery, SequenceEvidence, StructureEvidence


def sequence(**values: object) -> SequenceEvidence:
    defaults = dict(
        query_id="q",
        target_id="seq",
        tool="test",
        tool_version="1",
        database="test",
        database_version="1",
        normalized_score=0.8,
    )
    return SequenceEvidence(**(defaults | values))  # type: ignore[arg-type]


def structure(**values: object) -> StructureEvidence:
    defaults = dict(
        query_id="q",
        target_structure_id="struct",
        target_uniprot_id=None,
        tool="test",
        tool_version="1",
        database="test",
        database_version="1",
        normalized_score=0.7,
    )
    return StructureEvidence(**(defaults | values))  # type: ignore[arg-type]


def test_candidate_extraction_marks_generic_annotations_unclear() -> None:
    contributions = extract_contributions(
        [
            sequence(
                protein_name="Hypothetical protein",
                go_terms=["GO:0003674", "GO:0005524"],
                ec_numbers=["1.2.3.4"],
                interpro_ids=["IPR000001"],
                orthologous_group="OG1,OG2",
            )
        ],
        [],
    )
    by_id = {item.candidate_id: item for item in contributions}

    assert by_id["GO:0003674"].informative is False
    assert by_id["LABEL:hypothetical_protein"].informative is False
    assert by_id["GO:0005524"].informative is True
    assert by_id["EC:1.2.3.4"].informative is True
    assert {"OG:OG1", "OG:OG2"} <= by_id.keys()


def test_specific_label_consensus_scores_above_shared_family() -> None:
    result = fuse_candidates(
        [ProteinQuery("q", "MA")],
        [sequence(protein_name="ATPase", interpro_ids=["IPR1"])],
        [structure(protein_name="atpase", interpro_ids=["IPR1"])],
        FusionConfig(),
        run_id="run",
        parameters_hash="parameters",
    )
    by_id = {candidate.candidate_id: candidate for candidate in result.candidates}

    assert by_id["LABEL:atpase"].cross_modal_status.value == "CONSENSUS"
    assert by_id["LABEL:atpase"].fused_score == 0.8
    assert by_id["INTERPRO:IPR1"].cross_modal_status.value == "PARTIAL_CONSENSUS"
    assert by_id["INTERPRO:IPR1"].fused_score == 0.7
    assert result.summaries[0]["cross_modal_status"] == "CONSENSUS"
    assert result.summaries[0]["top_candidate_id"] == "LABEL:atpase"


def test_disjoint_informative_candidates_emit_conflict_report() -> None:
    result = fuse_candidates(
        [ProteinQuery("q", "MA")],
        [sequence(protein_name="Oxidoreductase", ec_numbers=["1.1.1.1"])],
        [structure(protein_name="Membrane scaffold", interpro_ids=["IPR2"])],
        FusionConfig(conflict_report_top_k=1),
        run_id="run",
        parameters_hash="parameters",
    )

    assert result.summaries[0]["cross_modal_status"] == "CONFLICT"
    assert len(result.conflicts) == 1
    assert result.conflicts[0]["top_sequence_candidates"] == "EC:1.1.1.1"
    assert result.conflicts[0]["top_structure_candidates"] == "INTERPRO:IPR2"


def test_shared_family_without_shared_label_is_partial_consensus() -> None:
    result = fuse_candidates(
        [ProteinQuery("q", "MA")],
        [sequence(protein_name="Enzyme family", interpro_ids=["IPR1"])],
        [structure(protein_name="Catalytic protein", interpro_ids=["IPR1"])],
        FusionConfig(),
        run_id="run",
        parameters_hash="parameters",
    )

    assert result.summaries[0]["cross_modal_status"] == "PARTIAL_CONSENSUS"
    assert result.summaries[0]["shared_candidate_count"] == 1


def test_only_generic_labels_are_insufficient() -> None:
    result = fuse_candidates(
        [ProteinQuery("q", "MA")],
        [sequence(protein_name="Unknown function")],
        [structure(protein_name="Uncharacterized protein")],
        FusionConfig(),
        run_id="run",
        parameters_hash="parameters",
    )

    assert result.summaries[0]["cross_modal_status"] == "INSUFFICIENT_EVIDENCE"
    assert result.summaries[0]["informative_candidate_count"] == 0
    assert result.summaries[0]["unclear_candidate_count"] == 2
