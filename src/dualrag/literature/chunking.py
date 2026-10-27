from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, write_json
from dualrag.literature.io import read_jsonl, write_jsonl
from dualrag.literature.schemas import (
    ArticleMetadata,
    FullTextStatus,
    LiteratureChunk,
    LiteratureSource,
    SectionType,
)

CHUNKER_VERSION = "section-aware-v1"


def normalize_and_chunk(
    *, article_path: Path, output_dir: Path, pmc_acquisitions_path: Path | None = None
) -> dict[str, Any]:
    articles = read_jsonl(article_path, ArticleMetadata)
    pmc_by_id: dict[str, dict[str, Any]] = {}
    if pmc_acquisitions_path and pmc_acquisitions_path.is_file():
        for item in _read_dict_jsonl(pmc_acquisitions_path):
            if item.get("pmcid"):
                pmc_by_id[item["pmcid"]] = item
    chunks: list[LiteratureChunk] = []
    article_states: list[dict[str, Any]] = []
    for article in articles:
        acquisition = pmc_by_id.get(article.pmcid or "")
        if acquisition and acquisition["full_text_status"] == FullTextStatus.PMC_OPEN_ACCESS:
            full_path = Path(acquisition["raw_full_text_path"])
            article_chunks = _chunk_pmc(article, full_path, acquisition)
            chosen_source = "PMC_OPEN_ACCESS"
        else:
            article_chunks = _chunk_abstract(article)
            chosen_source = "PUBMED_ABSTRACT"
        chunks.extend(article_chunks)
        article_states.append(
            {
                "source_article_id": article.source_article_id,
                "pmid": article.pmid,
                "pmcid": article.pmcid,
                "chosen_source": chosen_source,
                "chunk_count": len(article_chunks),
                "full_text_status": (
                    acquisition["full_text_status"] if acquisition else article.full_text_status
                ),
            }
        )
    write_jsonl(output_dir / "literature_chunks.jsonl", chunks)
    write_jsonl(output_dir / "article_normalization.jsonl", article_states)
    manifest = {
        "schema_version": 1,
        "chunker_version": CHUNKER_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "article_count": len(articles),
        "chunk_count": len(chunks),
        "full_text_article_count": sum(
            x["chosen_source"] == "PMC_OPEN_ACCESS" for x in article_states
        ),
        "section_counts": _counts(chunk.section_type for chunk in chunks),
        "inputs": {
            "articles": file_sha256(article_path),
            "pmc_acquisitions": (
                file_sha256(pmc_acquisitions_path)
                if pmc_acquisitions_path and pmc_acquisitions_path.is_file()
                else None
            ),
        },
        "output": {
            "path": str(output_dir / "literature_chunks.jsonl"),
            "sha256": file_sha256(output_dir / "literature_chunks.jsonl"),
        },
    }
    write_json(output_dir / "chunking_manifest.json", manifest)
    return manifest


def _chunk_abstract(article: ArticleMetadata) -> list[LiteratureChunk]:
    text = "\n\n".join(value for value in (article.title, article.abstract) if value)
    return _make_chunks(
        article=article,
        text=text,
        section_type=SectionType.TITLE_ABSTRACT,
        section_title="Title and abstract",
        source=LiteratureSource.PUBMED,
        status=article.full_text_status,
        source_url=article.source_url,
    )


def _chunk_pmc(
    article: ArticleMetadata, path: Path, acquisition: dict[str, Any]
) -> list[LiteratureChunk]:
    root = ET.parse(path).getroot()
    chunks: list[LiteratureChunk] = []
    abstract_nodes = root.findall(".//article-meta/abstract")
    abstract = " ".join(filter(None, (_all_text(node) for node in abstract_nodes)))
    if abstract:
        chunks.extend(
            _make_chunks(
                article,
                f"{article.title}\n\n{abstract}",
                SectionType.TITLE_ABSTRACT,
                "Title and abstract",
                LiteratureSource.PMC_OPEN_ACCESS,
                FullTextStatus.PMC_OPEN_ACCESS,
                acquisition["source_url"],
            )
        )
    for section in root.findall(".//body//sec"):
        title = _all_text(section.find("title")) or "Untitled section"
        section_type = _section_type(title)
        paragraphs = [_all_text(node) for node in section.findall("./p")]
        text = "\n\n".join(value for value in paragraphs if value)
        if text:
            chunks.extend(
                _make_chunks(
                    article,
                    text,
                    section_type,
                    title,
                    LiteratureSource.PMC_OPEN_ACCESS,
                    FullTextStatus.PMC_OPEN_ACCESS,
                    acquisition["source_url"],
                )
            )
    caption_types = (
        ("fig", SectionType.FIGURE_CAPTION),
        ("table-wrap", SectionType.TABLE_CAPTION),
    )
    for tag, kind in caption_types:
        for node in root.findall(f".//body//{tag}"):
            caption = _all_text(node.find("caption"))
            if caption:
                chunks.extend(
                    _make_chunks(
                        article,
                        caption,
                        kind,
                        _all_text(node.find("label")),
                        LiteratureSource.PMC_OPEN_ACCESS,
                        FullTextStatus.PMC_OPEN_ACCESS,
                        acquisition["source_url"],
                    )
                )
    return _deduplicate_chunks(chunks)


def _make_chunks(
    article: ArticleMetadata,
    text: str,
    section_type: SectionType,
    section_title: str | None,
    source: LiteratureSource,
    status: FullTextStatus,
    source_url: str,
) -> list[LiteratureChunk]:
    normalized = re.sub(r"[ \t]+", " ", text).strip()
    values: list[LiteratureChunk] = []
    start = 0
    while start < len(normalized):
        end = min(start + 1200, len(normalized))
        if end < len(normalized):
            boundary = max(
                normalized.rfind(". ", start + 600, end),
                normalized.rfind("\n", start + 600, end),
            )
            if boundary > start:
                end = boundary + 1
        value = normalized[start:end].strip()
        actual_start = normalized.find(value, start, end + 1)
        if value:
            digest = hashlib.sha256(
                f"{article.source_article_id}|{section_type}|{actual_start}|{value}".encode()
            ).hexdigest()[:20]
            values.append(
                LiteratureChunk(
                    chunk_id=f"chunk-{digest}",
                    source_article_id=article.source_article_id,
                    source=source,
                    pmid=article.pmid,
                    pmcid=article.pmcid,
                    doi=article.doi,
                    title=article.title,
                    year=article.year,
                    journal=article.journal,
                    article_is_review=article.is_review,
                    full_text_status=status,
                    organism_context=article.source_organisms,
                    section_type=section_type,
                    section_title=section_title,
                    text=value,
                    start_character=actual_start,
                    end_character=actual_start + len(value),
                    source_url=source_url,
                    retrieved_at=article.retrieved_at,
                    chunker_version=CHUNKER_VERSION,
                )
            )
        if end >= len(normalized):
            break
        start = max(end - 150, start + 1)
    return values


def _section_type(title: str) -> SectionType:
    value = title.casefold()
    if any(term in value for term in ("result", "finding")):
        return SectionType.RESULTS
    if any(term in value for term in ("method", "material", "experimental", "procedure")):
        return SectionType.METHODS
    if "discussion" in value or "conclusion" in value:
        return SectionType.DISCUSSION
    if "introduction" in value or "background" in value:
        return SectionType.INTRODUCTION
    return SectionType.OTHER


def _deduplicate_chunks(chunks: list[LiteratureChunk]) -> list[LiteratureChunk]:
    seen: set[str] = set()
    result: list[LiteratureChunk] = []
    for chunk in chunks:
        if chunk.text_sha256 not in seen:
            seen.add(chunk.text_sha256 or "")
            result.append(chunk)
    return result


def _all_text(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    value = re.sub(r"\s+", " ", "".join(node.itertext())).strip()
    return value or None


def _read_dict_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _counts(values: Any) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return result
