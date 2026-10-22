from __future__ import annotations

from pathlib import Path

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


def test_exact_cross_namespace_mapping_consolidates_and_keeps_provenance(
    tmp_path: Path,
) -> None:
    mapping = tmp_path / "mapping.tsv"
    mapping.write_text(
        "source_candidate_id\tcanonical_candidate_id\trelation\tsource\tsource_version\n"
        "PFAM:PF1\tINTERPRO:IPR1\tEXACT\ttest-map\t2026-01\n",
        encoding="utf-8",
    )
    result = fuse_candidates(
        [ProteinQuery("q", "MA")],
        [sequence(pfam_ids=["PF1"])],
        [structure(interpro_ids=["IPR1"])],
        FusionConfig(mapping_path=mapping),
        run_id="run",
        parameters_hash="parameters",
    )

    candidate = result.candidates[0]
    assert candidate.candidate_id == "INTERPRO:IPR1"
    assert candidate.candidate_aliases == ["INTERPRO:IPR1", "PFAM:PF1"]
    assert candidate.mapping_provenance == ["test-map@2026-01:EXACT"]
    assert result.summaries[0]["cross_modal_status"] == "PARTIAL_CONSENSUS"
    assert result.audit["mapped_contribution_count"] == 1
    assert result.audit["mapping_inputs"][0]["sha256"]
    assert result.audit["mapping_sources"] == [
        {"source": "test-map", "source_version": "2026-01", "relation": "EXACT"}
    ]


def test_curated_synonym_can_create_exact_function_consensus(tmp_path: Path) -> None:
    synonyms = tmp_path / "synonyms.tsv"
    synonyms.write_text(
        "normalized_label\tcanonical_candidate_id\tsource\tsource_version\n"
        "Alcohol dehydrogenase\tEC:1.1.1.1\tcurated-test\tv1\n",
        encoding="utf-8",
    )
    result = fuse_candidates(
        [ProteinQuery("q", "MA")],
        [sequence(ec_numbers=["1.1.1.1"])],
        [structure(protein_name="alcohol dehydrogenase")],
        FusionConfig(synonym_path=synonyms),
        run_id="run",
        parameters_hash="parameters",
    )

    assert result.summaries[0]["cross_modal_status"] == "CONSENSUS"
    assert result.candidates[0].candidate_id == "EC:1.1.1.1"


def test_related_mapping_yields_partial_not_exact_consensus(tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.tsv"
    mapping.write_text(
        "source_candidate_id\tcanonical_candidate_id\trelation\tsource\tsource_version\n"
        "PFAM:PF1\tINTERPRO:IPR1\tRELATED\ttest-map\tv1\n",
        encoding="utf-8",
    )
    result = fuse_candidates(
        [ProteinQuery("q", "MA")],
        [sequence(pfam_ids=["PF1"])],
        [structure(interpro_ids=["IPR1"])],
        FusionConfig(mapping_path=mapping),
        run_id="run",
        parameters_hash="parameters",
    )

    assert result.summaries[0]["cross_modal_status"] == "PARTIAL_CONSENSUS"
    assert result.audit["compatible_cross_modal_pair_count"] == 1
    assert {item.candidate_id for item in result.candidates} == {
        "PFAM:PF1",
        "INTERPRO:IPR1",
    }
    assert all(item.cross_modal_status.value == "PARTIAL_CONSENSUS" for item in result.candidates)


def test_reranking_and_alternative_margin_are_explicit() -> None:
    result = fuse_candidates(
        [ProteinQuery("q", "MA")],
        [sequence(ec_numbers=["1.1.1.1"], go_terms=["GO:0005524"])],
        [],
        FusionConfig(alternatives_top_k=2, ambiguity_margin=1.0),
        run_id="run",
        parameters_hash="parameters",
    )

    assert len(result.alternatives) == 2
    assert result.alternatives[0]["score_delta_from_top"] == 0
    assert result.alternatives[1]["ambiguous_with_top"] is True
    assert result.candidates[0].rerank_score != result.candidates[0].fused_score
