from __future__ import annotations

from datetime import UTC, datetime

from dualrag.literature.preannotation import _organism_aliases, _protein_aliases, _suggest
from dualrag.literature.schemas import (
    ArticleMetadata,
    FullTextStatus,
    LiteratureCandidate,
    LiteratureChunk,
    LiteratureQuery,
    LiteratureSource,
    SectionType,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _query() -> LiteratureQuery:
    return LiteratureQuery(
        query_id="P01040",
        query_accession="P01040",
        protein_name="Cystatin-A",
        organism="Homo sapiens (Human)",
        cross_modal_status="CONSENSUS",
        query_terms=["P01040", "Cystatin-A", "Homo sapiens"],
        query_variants=['"Cystatin-A"'],
        query_builder_version="test",
        source_biological_run_id="test",
        source_parameters_hash="test",
        created_at=NOW,
    )


def _candidate(text: str, *, primary: bool = True) -> LiteratureCandidate:
    chunk = LiteratureChunk(
        chunk_id="chunk-1",
        source_article_id="PMID:1",
        source=LiteratureSource.PUBMED,
        pmid="1",
        title="Experiment",
        article_is_review=False,
        full_text_status=FullTextStatus.ABSTRACT_ONLY,
        section_type=SectionType.TITLE_ABSTRACT,
        text=text,
        start_character=0,
        end_character=len(text),
        source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
        retrieved_at=NOW,
        chunker_version="test",
    )
    return LiteratureCandidate(
        candidate_id="P01040:chunk-1",
        query_id="P01040",
        chunk=chunk,
        lexical_score=1,
        vector_score=1,
        hybrid_score=1,
        reranker_score=1,
        lexical_rank=1,
        vector_rank=1,
        hybrid_rank=1,
        reranker_rank=1,
        is_primary_experiment=primary,
        retriever_version="test",
        reranker_version="test",
        scored_at=NOW,
    )


def _article(*, review: bool = False) -> ArticleMetadata:
    return ArticleMetadata(
        source_article_id="PMID:1",
        source=LiteratureSource.PUBMED,
        pmid="1",
        title="Human cystatin A experiment",
        publication_types=["Review" if review else "Journal Article"],
        is_review=review,
        source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
        full_text_status=FullTextStatus.ABSTRACT_ONLY,
        retrieved_at=NOW,
    )


def test_exact_name_organism_experiment_is_suggested_support() -> None:
    annotation, _review = _suggest(
        _query(),
        _candidate("Cystatin-A activity was measured in human cells."),
        _article(),
    )
    assert annotation["annotator"] == "codex_preannotation"
    assert annotation["relevant"] == "true"
    assert annotation["citation_supported"] == "true"
    assert annotation["entity_correct"] == "true"
    assert annotation["organism_correct"] == "true"
    assert annotation["primary_experiment"] == "true"
    assert annotation["contradiction"] == "false"


def test_review_cannot_be_primary_support() -> None:
    annotation, _review = _suggest(
        _query(),
        _candidate("Cystatin-A activity in human cells was reviewed."),
        _article(review=True),
    )
    assert annotation["relevant"] == "true"
    assert annotation["primary_experiment"] == "false"
    assert annotation["citation_supported"] == "false"


def test_unrelated_primary_experiment_stays_irrelevant_but_primary() -> None:
    annotation, _review = _suggest(
        _query(),
        _candidate("A bacterial DNA polymerase activity was measured."),
        _article(),
    )
    assert annotation["relevant"] == "false"
    assert annotation["entity_correct"] == "false"
    assert annotation["organism_correct"] == "false"
    assert annotation["primary_experiment"] == "true"


def test_preannotation_aliases_cover_subunits_and_phage_names() -> None:
    assert "Reverse gyrase" in _protein_aliases("Reverse gyrase subunit B")
    assert "D-glucuronyl C5-epimerase" in _protein_aliases("D-glucuronyl C5-epimerase B")
    assert "SF6" in _organism_aliases("Bacillus phage SF6 (Bacteriophage SF6)")
