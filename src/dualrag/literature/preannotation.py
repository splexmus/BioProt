from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from pathlib import Path

from dualrag.literature.evaluation import CANDIDATE_REVIEW_FIELDS
from dualrag.literature.io import read_jsonl
from dualrag.literature.schemas import ArticleMetadata, LiteratureCandidate, LiteratureQuery

PREANNOTATOR = "codex_preannotation"
PREANNOTATION_VERSION = "conservative-literature-preannotation-v1"
_TOKEN = re.compile(r"[a-z0-9]+")
_EXPERIMENT_TERMS = {
    "activity",
    "assay",
    "binding",
    "catalytic",
    "characterized",
    "demonstrated",
    "identified",
    "measured",
    "mutant",
    "mutation",
    "purified",
    "structure",
}
_NEGATIVE_RESULT_TERMS = {
    "abolished",
    "decreased",
    "did not",
    "different specificity",
    "failed to",
    "inactive",
    "inhibited",
    "loss of",
    "no activity",
    "not required",
    "reduced",
    "unable to",
}
_NON_PRIMARY_TYPES = {
    "biography",
    "comment",
    "editorial",
    "historical article",
    "letter",
    "retracted publication",
    "review",
}


def write_preannotation(
    *,
    queries_path: Path,
    candidates_path: Path,
    articles_path: Path,
    output_path: Path,
    review_queue_path: Path,
) -> dict[str, int]:
    queries = {item.query_id: item for item in read_jsonl(queries_path, LiteratureQuery)}
    candidates = read_jsonl(candidates_path, LiteratureCandidate)
    articles = read_jsonl(articles_path, ArticleMetadata)
    by_pmid = {item.pmid: item for item in articles if item.pmid}
    by_source_id = {item.source_article_id: item for item in articles}

    annotations: list[dict[str, str]] = []
    review_rows: list[dict[str, str | int]] = []
    for candidate in sorted(
        candidates, key=lambda item: (item.query_id, item.reranker_rank, item.chunk.chunk_id)
    ):
        query = queries[candidate.query_id]
        article = (
            by_pmid.get(candidate.chunk.pmid)
            if candidate.chunk.pmid
            else by_source_id.get(candidate.chunk.source_article_id)
        )
        annotation, review = _suggest(query, candidate, article)
        annotations.append(annotation)
        review_rows.append(review)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CANDIDATE_REVIEW_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(annotations)

    queue_fields = [
        "review_priority",
        "query_id",
        "protein_name",
        "organism",
        "chunk_id",
        "pmid",
        "reranker_rank",
        "suggested_relevant",
        "suggested_citation_supported",
        "suggested_contradiction",
        "suggested_entity_correct",
        "suggested_organism_correct",
        "suggested_primary_experiment",
        "reason",
        "title",
        "text",
        "source_url",
    ]
    review_rows.sort(
        key=lambda row: (
            int(row["review_priority"]),
            str(row["query_id"]),
            int(row["reranker_rank"]),
        )
    )
    with review_queue_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=queue_fields, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(review_rows)

    return {
        "row_count": len(annotations),
        "relevant_count": _true_count(annotations, "relevant"),
        "citation_supported_count": _true_count(annotations, "citation_supported"),
        "contradiction_count": _true_count(annotations, "contradiction"),
        "entity_correct_count": _true_count(annotations, "entity_correct"),
        "organism_correct_count": _true_count(annotations, "organism_correct"),
        "primary_experiment_count": _true_count(annotations, "primary_experiment"),
        "priority_one_count": sum(row["review_priority"] == 1 for row in review_rows),
    }


def _suggest(
    query: LiteratureQuery,
    candidate: LiteratureCandidate,
    article: ArticleMetadata | None,
) -> tuple[dict[str, str], dict[str, str | int]]:
    chunk = candidate.chunk
    text = f"{chunk.title} {chunk.text}"
    normalized = _normalize(text)
    accession_hit = _contains(normalized, query.query_accession)
    protein_hits = [
        alias for alias in _protein_aliases(query.protein_name) if _contains(normalized, alias)
    ]
    organism_hits = [
        alias for alias in _organism_aliases(query.organism) if _contains(normalized, alias)
    ]
    homolog_hits = [
        item.accession for item in query.selected_homologs if _contains(normalized, item.accession)
    ]

    organism_correct = bool(organism_hits)
    entity_correct = bool(accession_hit or homolog_hits or (protein_hits and organism_correct))
    relevant = entity_correct
    primary = _is_primary(candidate, article)
    result_terms = sorted(term for term in _EXPERIMENT_TERMS if term in normalized)
    citation_supported = bool(relevant and primary and result_terms)
    contradiction_review = bool(
        relevant and primary and any(term in normalized for term in _NEGATIVE_RESULT_TERMS)
    )

    entity_reason = "unresolved"
    if accession_hit:
        entity_reason = "accession"
    elif homolog_hits:
        entity_reason = "homolog"
    elif entity_correct:
        entity_reason = "name+organism"
    reasons = [
        f"entity={entity_reason}",
        f"organism={','.join(organism_hits[:2]) or 'unresolved'}",
        f"primary={'yes' if primary else 'no'}",
        f"result_terms={','.join(result_terms[:4]) or 'none'}",
    ]
    flags: list[str] = []
    if contradiction_review:
        flags.append("POSSIBLE_CONTRADICTION_REVIEW")
    if candidate.reranker_rank <= 10:
        flags.append("TOP10")
    if protein_hits and not organism_correct:
        flags.append("PROTEIN_NAME_WITHOUT_QUERY_ORGANISM")
    if article is None:
        flags.append("ARTICLE_METADATA_MISSING")

    priority = 1 if contradiction_review or candidate.reranker_rank <= 10 else 2
    if not relevant and candidate.reranker_rank > 20:
        priority = 3
    note = f"{PREANNOTATION_VERSION}; human_review_required; " + "; ".join(
        reasons + ([f"flags={','.join(flags)}"] if flags else [])
    )
    annotation = {
        "annotator": PREANNOTATOR,
        "query_id": query.query_id,
        "chunk_id": chunk.chunk_id,
        "relevant": _boolean(relevant),
        "citation_supported": _boolean(citation_supported),
        "contradiction": "false",
        "entity_correct": _boolean(entity_correct),
        "organism_correct": _boolean(organism_correct),
        "primary_experiment": _boolean(primary),
        "notes": note,
        "pmid": chunk.pmid or "",
        "title": chunk.title,
        "section_type": str(chunk.section_type),
        "text": chunk.text,
        "source_url": chunk.source_url,
        "lexical_rank": str(candidate.lexical_rank),
        "vector_rank": str(candidate.vector_rank),
        "hybrid_rank": str(candidate.hybrid_rank),
        "reranker_rank": str(candidate.reranker_rank),
    }
    review = {
        "review_priority": priority,
        "query_id": query.query_id,
        "protein_name": query.protein_name or "",
        "organism": query.organism or "",
        "chunk_id": chunk.chunk_id,
        "pmid": chunk.pmid or "",
        "reranker_rank": candidate.reranker_rank,
        "suggested_relevant": annotation["relevant"],
        "suggested_citation_supported": annotation["citation_supported"],
        "suggested_contradiction": annotation["contradiction"],
        "suggested_entity_correct": annotation["entity_correct"],
        "suggested_organism_correct": annotation["organism_correct"],
        "suggested_primary_experiment": annotation["primary_experiment"],
        "reason": note,
        "title": chunk.title,
        "text": chunk.text,
        "source_url": chunk.source_url,
    }
    return annotation, review


def _is_primary(candidate: LiteratureCandidate, article: ArticleMetadata | None) -> bool:
    if article is None or article.is_review:
        return False
    publication_types = {value.casefold() for value in article.publication_types}
    if publication_types & _NON_PRIMARY_TYPES:
        return False
    return bool(candidate.is_primary_experiment)


def _protein_aliases(value: str | None) -> list[str]:
    if not value:
        return []
    aliases = [value, re.sub(r"^protein\s+", "", value, flags=re.IGNORECASE)]
    final = value.rsplit(" ", 1)[-1]
    if len(final) >= 3 and (
        re.search(r"\d", final) or "-" in final or re.search(r"[a-z].*[A-Z]", final)
    ):
        aliases.append(final)
    aliases.append(re.sub(r"\s+subunit\s+[A-Z0-9]+$", "", value).strip())
    aliases.append(re.sub(r"\s+[A-Z]$", "", value).strip())
    aliases.append(re.sub(r"\s+\d+$", "", value).strip())
    if "/" in value:
        aliases.append(value.rsplit(" ", 1)[-1])
    if ":" in value and " " in value:
        suffix = value.split(" ", 1)[1]
        aliases.extend([suffix, re.sub(r"\s+subunit\s+[A-Z0-9]+$", "", suffix).strip()])
    return _unique(aliases)


def _organism_aliases(value: str | None) -> list[str]:
    if not value:
        return []
    aliases = [value.split(" (", 1)[0]]
    aliases.extend(
        match
        for match in re.findall(r"\(([^()]*)\)", value)
        if not match.casefold().startswith("strain ")
    )
    common = {
        "homo sapiens": "human",
        "mus musculus": "mouse",
        "danio rerio": "zebrafish",
    }
    primary = aliases[0].casefold()
    if primary in common:
        aliases.append(common[primary])
    if "human immunodeficiency virus type 1" in value.casefold():
        aliases.extend(["HIV-1", "HXB2"])
    if "phage" in value.casefold():
        aliases.extend(
            token
            for token in re.findall(r"[A-Za-z]*\d+[A-Za-z0-9-]*|lambda", value)
            if len(token) >= 3
        )
    return _unique(aliases)


def _normalize(value: str) -> str:
    return " ".join(_TOKEN.findall(value.casefold()))


def _contains(normalized_text: str, value: str | None) -> bool:
    if not value:
        return False
    normalized_value = _normalize(value)
    return bool(normalized_value and f" {normalized_value} " in f" {normalized_text} ")


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _boolean(value: bool) -> str:
    return "true" if value else "false"


def _true_count(rows: list[dict[str, str]], field: str) -> int:
    return sum(row[field] == "true" for row in rows)
