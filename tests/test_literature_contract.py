from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dualrag.literature.schemas import (
    ArticleMetadata,
    AssignmentMethod,
    EntityMatch,
    EvidencePacket,
    EvidenceRole,
    FullTextStatus,
    LiteratureChunk,
    LiteratureHit,
    LiteratureQuery,
    LiteratureSource,
    OrganismMatch,
    SectionType,
    SelectedHomolog,
)

ROOT = Path(__file__).parents[1]
NOW = datetime(2026, 10, 26, tzinfo=UTC)


def query(**changes: object) -> LiteratureQuery:
    values = {
        "query_id": "P69905",
        "query_accession": "P69905",
        "protein_name": "Hemoglobin subunit alpha",
        "organism": "Homo sapiens",
        "taxonomy_id": 9606,
        "candidate_ids": ["GO:0019825"],
        "candidate_labels": ["oxygen binding"],
        "selected_homologs": [
            SelectedHomolog(
                accession="P01942",
                source_target_id="P01942",
                sequence_identity=0.7,
                alignment_coverage=0.9,
                normalized_score=0.8,
                provenance="MMseqs2@16|Swiss-Prot@2026_03",
            )
        ],
        "alternative_hypotheses": [],
        "cross_modal_status": "CONSENSUS",
        "query_terms": ["P69905", '"oxygen binding"'],
        "query_variants": ['"P69905" AND "oxygen binding"'],
        "query_builder_version": "deterministic-v1",
        "source_biological_run_id": "run-1",
        "source_parameters_hash": "abc123",
        "created_at": NOW,
    }
    return LiteratureQuery.model_validate(values | changes)


def chunk(**changes: object) -> LiteratureChunk:
    values = {
        "chunk_id": "PMCID:PMC1:results:1",
        "source_article_id": "PMID:1",
        "source": LiteratureSource.PMC_OPEN_ACCESS,
        "pmid": "1",
        "pmcid": "PMC1",
        "doi": "10.1/example",
        "title": "Experimental characterization",
        "year": 2025,
        "journal": "Example Journal",
        "article_is_review": False,
        "full_text_status": FullTextStatus.PMC_OPEN_ACCESS,
        "organism_context": ["Homo sapiens"],
        "section_type": SectionType.RESULTS,
        "section_title": "Results",
        "text": "Purified P69905 bound oxygen under the reported assay conditions.",
        "start_character": 100,
        "end_character": 165,
        "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/",
        "retrieved_at": NOW,
        "chunker_version": "section-v1",
    }
    return LiteratureChunk.model_validate(values | changes)


def hit(**changes: object) -> LiteratureHit:
    values = {
        "hit_id": "hit-1",
        "query_id": "P69905",
        "chunk": chunk(),
        "rank": 1,
        "retrieval_score": 0.91,
        "lexical_score": 12.5,
        "vector_score": 0.82,
        "reranker_score": 0.91,
        "retrieval_method": "hybrid_reranked",
        "retriever_version": "hybrid-v1",
        "reranker_version": "rules-v1",
        "query_terms": ["P69905", '"oxygen binding"'],
        "retrieved_at": NOW,
        "entity_match": EntityMatch.EXACT_ACCESSION,
        "entity_match_basis": ["P69905"],
        "organism_match": OrganismMatch.EXACT_TAXON,
        "source_organism": "Homo sapiens",
        "evidence_role": EvidenceRole.SUPPORT,
        "assignment_method": AssignmentMethod.MANUAL,
        "assignment_version": "curation-v1",
        "is_primary_experiment": True,
    }
    return LiteratureHit.model_validate(values | changes)


def test_machine_contract_freezes_required_boundaries() -> None:
    contract = yaml.safe_load(
        (ROOT / "config" / "literature-contract-v1.yaml").read_text(encoding="utf-8")
    )
    assert contract["contract_id"] == "phase4-literature-v1"
    assert contract["limits"] == {
        "final_unique_articles_per_query": 10,
        "final_chunks_per_query": 20,
        "final_chunks_per_article": 3,
        "maximum_chunk_characters": 1200,
        "pad_with_weak_matches": False,
        "preserve_contradictions": True,
    }
    assert contract["query_construction"]["prohibited_inputs"]
    assert contract["source_policy"]["PUBMED"]["implies_full_text"] is False
    assert contract["evidence_roles"]["review_allowed_roles"] == [
        "BACKGROUND",
        "IRRELEVANT",
        "UNASSESSED",
    ]


def test_exported_json_schemas_match_python_models() -> None:
    exported = json.loads(
        (ROOT / "config" / "literature-schemas-v1.json").read_text(encoding="utf-8")
    )
    assert exported["contract_id"] == "phase4-literature-v1"
    assert exported["models"]["LiteratureQuery"] == LiteratureQuery.model_json_schema()
    assert exported["models"]["EvidencePacket"] == EvidencePacket.model_json_schema()


def test_query_forbids_gold_label_leakage_and_naive_timestamps() -> None:
    with pytest.raises(ValidationError, match="gold_labels"):
        query(gold_labels=["GO:0019825"])
    with pytest.raises(ValidationError, match="timezone"):
        query(created_at=datetime(2026, 10, 26))


def test_article_requires_pmcid_for_pmc_open_access() -> None:
    with pytest.raises(ValidationError, match="require a PMCID"):
        ArticleMetadata(
            source_article_id="PMC-missing",
            source=LiteratureSource.PMC_OPEN_ACCESS,
            title="Example",
            source_url="https://example.test",
            full_text_status=FullTextStatus.PMC_OPEN_ACCESS,
            retrieved_at=NOW,
        )


def test_chunk_computes_checksum_and_rejects_invalid_offsets() -> None:
    record = chunk()
    assert len(record.text_sha256 or "") == 64
    with pytest.raises(ValidationError, match="end_character"):
        chunk(start_character=100, end_character=100)


def test_support_requires_primary_experiment_and_entity_basis() -> None:
    with pytest.raises(ValidationError, match="primary experiment"):
        hit(is_primary_experiment=False)
    with pytest.raises(ValidationError, match="entity-match basis"):
        hit(entity_match_basis=[])
    with pytest.raises(ValidationError, match="review passages"):
        hit(chunk=chunk(article_is_review=True))


def test_evidence_packet_round_trip_and_contradiction_links() -> None:
    support = hit()
    contradiction = hit(
        hit_id="hit-2",
        evidence_role=EvidenceRole.CONTRADICTION,
        chunk=chunk(chunk_id="PMCID:PMC1:results:2", start_character=200, end_character=265),
    )
    packet = EvidencePacket(
        packet_id="packet-1",
        query=query(),
        literature_hits=[support, contradiction],
        contradiction_hit_ids=["hit-2"],
        claim_boundaries=[
            "Retrieved passages support a hypothesis, not experimental confirmation."
        ],
        created_at=NOW,
    )
    restored = EvidencePacket.model_validate_json(packet.model_dump_json())
    assert restored == packet
    assert json.loads(packet.model_dump_json())["contract_id"] == "phase4-literature-v1"

    with pytest.raises(ValidationError, match="contradiction_hit_ids"):
        EvidencePacket(
            packet_id="packet-invalid",
            query=query(),
            literature_hits=[contradiction],
            contradiction_hit_ids=[],
            claim_boundaries=["Keep contradictions visible."],
            created_at=NOW,
        )


def test_evidence_packet_enforces_three_chunks_per_article() -> None:
    hits = [
        hit(
            hit_id=f"hit-{index}",
            evidence_role=EvidenceRole.UNASSESSED,
            assignment_method=AssignmentMethod.UNASSESSED,
            is_primary_experiment=None,
            chunk=chunk(
                chunk_id=f"PMCID:PMC1:results:{index}",
                start_character=index * 100,
                end_character=index * 100 + 65,
            ),
        )
        for index in range(4)
    ]
    with pytest.raises(ValidationError, match="at most 3 chunks per article"):
        EvidencePacket(
            packet_id="packet-too-many",
            query=query(),
            literature_hits=hits,
            claim_boundaries=["Keep the packet compact."],
            created_at=NOW,
        )
