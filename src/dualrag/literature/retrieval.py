from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, write_json
from dualrag.literature.io import read_jsonl, write_jsonl
from dualrag.literature.schemas import (
    EntityMatch,
    LiteratureCandidate,
    LiteratureChunk,
    LiteratureHit,
    LiteratureQuery,
    OrganismMatch,
    SectionType,
)

RETRIEVER_VERSION = "hybrid-bm25-char3-v1"
RERANKER_VERSION = "biological-rule-v1"
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*")
_EXPERIMENT_TERMS = {
    "assay",
    "activity",
    "measured",
    "mutant",
    "binding",
    "catalytic",
    "experiment",
}
_SECTION_PRIOR = {
    SectionType.RESULTS: 1.0,
    SectionType.FIGURE_CAPTION: 0.9,
    SectionType.TABLE_CAPTION: 0.9,
    SectionType.TITLE_ABSTRACT: 0.75,
    SectionType.DISCUSSION: 0.6,
    SectionType.METHODS: 0.45,
    SectionType.INTRODUCTION: 0.3,
    SectionType.OTHER: 0.4,
}


def retrieve_and_rerank(
    *,
    queries_path: Path,
    chunks_path: Path,
    output_dir: Path,
    query_article_links_path: Path | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    queries = read_jsonl(queries_path, LiteratureQuery)
    chunks = read_jsonl(chunks_path, LiteratureChunk)
    now = datetime.now(UTC)
    hits: list[LiteratureHit] = []
    candidates: list[LiteratureCandidate] = []
    links = (
        json.loads(query_article_links_path.read_text(encoding="utf-8"))
        if query_article_links_path
        else None
    )
    for query in queries:
        allowed_pmids = set(links.get(query.query_id, {})) if links is not None else None
        query_chunks = [
            chunk for chunk in chunks if allowed_pmids is None or chunk.pmid in allowed_pmids
        ]
        scored = _score_query(query, query_chunks)
        rank_maps = {
            "lexical": _rank_map(scored, 1),
            "vector": _rank_map(scored, 2),
            "hybrid": _rank_map(scored, 3),
            "reranker": _rank_map(scored, 4),
        }
        for item in scored:
            chunk, lexical, vector, hybrid, reranker, entity, basis, organism, primary = item
            candidates.append(
                LiteratureCandidate(
                    candidate_id=f"{query.query_id}:{chunk.chunk_id}",
                    query_id=query.query_id,
                    chunk=chunk,
                    lexical_score=lexical,
                    vector_score=vector,
                    hybrid_score=hybrid,
                    reranker_score=reranker,
                    lexical_rank=rank_maps["lexical"][chunk.chunk_id],
                    vector_rank=rank_maps["vector"][chunk.chunk_id],
                    hybrid_rank=rank_maps["hybrid"][chunk.chunk_id],
                    reranker_rank=rank_maps["reranker"][chunk.chunk_id],
                    entity_match=entity,
                    entity_match_basis=basis,
                    organism_match=organism,
                    is_primary_experiment=primary,
                    retriever_version=RETRIEVER_VERSION,
                    reranker_version=RERANKER_VERSION,
                    scored_at=now,
                )
            )
        ranked = _article_limited(scored, article_limit=10, per_article=3, total=top_k)
        for rank, item in enumerate(ranked, 1):
            chunk, lexical, vector, hybrid, reranker, entity, basis, organism, primary = item
            hits.append(
                LiteratureHit(
                    hit_id=f"{query.query_id}:{chunk.chunk_id}",
                    query_id=query.query_id,
                    chunk=chunk,
                    rank=rank,
                    retrieval_score=reranker,
                    lexical_score=lexical,
                    vector_score=vector,
                    reranker_score=reranker,
                    retrieval_method="hybrid",
                    retriever_version=RETRIEVER_VERSION,
                    reranker_version=RERANKER_VERSION,
                    query_terms=query.query_terms,
                    retrieved_at=now,
                    entity_match=entity,
                    entity_match_basis=basis,
                    organism_match=organism,
                    source_organism=(
                        query.organism if organism is not OrganismMatch.UNRESOLVED else None
                    ),
                    is_primary_experiment=primary,
                    uncertainty_notes=[
                        "Rule-based identity and organism matches require manual verification."
                    ],
                )
            )
    write_jsonl(output_dir / "literature_candidates.jsonl", candidates)
    write_jsonl(output_dir / "literature_hits.jsonl", hits)
    manifest = {
        "schema_version": 1,
        "retriever_version": RETRIEVER_VERSION,
        "reranker_version": RERANKER_VERSION,
        "created_at": now.isoformat(),
        "query_count": len(queries),
        "chunk_count": len(chunks),
        "hit_count": len(hits),
        "candidate_count": len(candidates),
        "top_k": top_k,
        "inputs": {
            "queries": file_sha256(queries_path),
            "chunks": file_sha256(chunks_path),
            "query_article_links": (
                file_sha256(query_article_links_path) if query_article_links_path else None
            ),
        },
        "output": {
            "path": str(output_dir / "literature_hits.jsonl"),
            "sha256": file_sha256(output_dir / "literature_hits.jsonl"),
        },
        "candidate_output": {
            "path": str(output_dir / "literature_candidates.jsonl"),
            "sha256": file_sha256(output_dir / "literature_candidates.jsonl"),
        },
        "score_warning": (
            "Scores rank passages; they are not calibrated confidence or evidence roles."
        ),
    }
    write_json(output_dir / "retrieval_manifest.json", manifest)
    return manifest


def _score_query(query: LiteratureQuery, chunks: list[LiteratureChunk]) -> list[tuple[Any, ...]]:
    query_tokens = _tokens(" ".join(query.query_terms))
    documents = [_tokens(chunk.text) for chunk in chunks]
    document_frequency = Counter(term for terms in documents for term in set(terms))
    average_length = sum(map(len, documents)) / max(len(documents), 1)
    lexical_values = [
        _bm25(query_tokens, terms, document_frequency, len(documents), average_length)
        for terms in documents
    ]
    query_chars = Counter(_chargrams(" ".join(query.query_terms)))
    vector_values = [_cosine(query_chars, Counter(_chargrams(chunk.text))) for chunk in chunks]
    lexical_norm = _normalize(lexical_values)
    vector_norm = _normalize(vector_values)
    scored: list[tuple[Any, ...]] = []
    for chunk, lexical, vector in zip(chunks, lexical_norm, vector_norm, strict=True):
        hybrid = 0.5 * lexical + 0.5 * vector
        entity, basis = _entity_match(query, chunk.text)
        organism = _organism_match(query, chunk.text)
        lower = chunk.text.casefold()
        primary = not chunk.article_is_review and any(term in lower for term in _EXPERIMENT_TERMS)
        entity_prior = {
            EntityMatch.EXACT_ACCESSION: 1.0,
            EntityMatch.EXACT_NAMED_PROTEIN: 0.9,
            EntityMatch.TRACEABLE_HOMOLOG: 0.75,
            EntityMatch.FAMILY_ONLY: 0.45,
            EntityMatch.NONE: 0.0,
            EntityMatch.UNRESOLVED: 0.1,
        }[entity]
        organism_prior = (
            1.0
            if organism in {OrganismMatch.EXACT_TAXON, OrganismMatch.SAME_SPECIES}
            else 0.4
        )
        reranker = (
            0.65 * hybrid
            + 0.15 * entity_prior
            + 0.1 * organism_prior
            + 0.1 * _SECTION_PRIOR[chunk.section_type]
        )
        scored.append((chunk, lexical, vector, hybrid, reranker, entity, basis, organism, primary))
    return sorted(scored, key=lambda value: (-value[4], value[0].chunk_id))


def _article_limited(
    values: list[tuple[Any, ...]], *, article_limit: int, per_article: int, total: int
) -> list[tuple[Any, ...]]:
    counts: dict[str, int] = defaultdict(int)
    articles: set[str] = set()
    result: list[tuple[Any, ...]] = []
    for value in values:
        article_id = value[0].source_article_id
        new_article_over_limit = article_id not in articles and len(articles) >= article_limit
        if counts[article_id] >= per_article or new_article_over_limit:
            continue
        counts[article_id] += 1
        articles.add(article_id)
        result.append(value)
        if len(result) == total:
            break
    return result


def _rank_map(values: list[tuple[Any, ...]], score_index: int) -> dict[str, int]:
    ordered = sorted(values, key=lambda value: (-value[score_index], value[0].chunk_id))
    return {value[0].chunk_id: rank for rank, value in enumerate(ordered, 1)}


def _entity_match(query: LiteratureQuery, text: str) -> tuple[EntityMatch, list[str]]:
    folded = text.casefold()
    if query.query_accession and query.query_accession.casefold() in folded:
        return EntityMatch.EXACT_ACCESSION, [f"accession:{query.query_accession}"]
    if query.protein_name and query.protein_name.casefold() in folded:
        return EntityMatch.EXACT_NAMED_PROTEIN, [f"protein_name:{query.protein_name}"]
    for homolog in query.selected_homologs:
        if homolog.accession.casefold() in folded:
            return EntityMatch.TRACEABLE_HOMOLOG, [f"homolog:{homolog.accession}"]
    for label in [*query.candidate_ids, *query.candidate_labels]:
        if label.casefold() in folded:
            return EntityMatch.FAMILY_ONLY, [f"candidate:{label}"]
    return EntityMatch.UNRESOLVED, []


def _organism_match(query: LiteratureQuery, text: str) -> OrganismMatch:
    folded = text.casefold()
    if query.taxonomy_id and str(query.taxonomy_id) in folded:
        return OrganismMatch.EXACT_TAXON
    if query.organism and query.organism.casefold() in folded:
        return OrganismMatch.SAME_SPECIES
    return OrganismMatch.UNRESOLVED


def _tokens(text: str) -> list[str]:
    return [value.casefold() for value in _TOKEN.findall(text)]


def _chargrams(text: str) -> list[str]:
    value = re.sub(r"\s+", " ", text.casefold())
    return [value[index : index + 3] for index in range(max(len(value) - 2, 0))]


def _bm25(query: list[str], document: list[str], df: Counter[str], n: int, avgdl: float) -> float:
    counts = Counter(document)
    score = 0.0
    for term in set(query):
        frequency = counts[term]
        if not frequency:
            continue
        inverse = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
        denominator = frequency + 1.2 * (
            0.25 + 0.75 * len(document) / max(avgdl, 1)
        )
        score += inverse * frequency * 2.2 / denominator
    return score


def _cosine(first: Counter[str], second: Counter[str]) -> float:
    numerator = sum(value * second[key] for key, value in first.items())
    denominator = math.sqrt(
        sum(value * value for value in first.values())
        * sum(value * value for value in second.values())
    )
    return numerator / denominator if denominator else 0.0


def _normalize(values: list[float]) -> list[float]:
    maximum = max(values, default=0.0)
    return [value / maximum if maximum else 0.0 for value in values]
