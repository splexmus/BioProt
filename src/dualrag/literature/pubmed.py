from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, ConfigDict, Field

from dualrag.io import file_sha256, stable_hash, write_json
from dualrag.literature.io import read_jsonl, write_jsonl
from dualrag.literature.schemas import (
    ArticleMetadata,
    FullTextStatus,
    LiteratureQuery,
    LiteratureSource,
)

PUBMED_ADAPTER_VERSION = "pubmed-eutils-v1"
_QUOTED_TERM = re.compile(r'"((?:[^"\\]|\\.)*)"')


class PubMedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_url: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    tool: str = "dualrag-bioprot"
    email: str
    api_key_env: str = "NCBI_API_KEY"
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    backoff_seconds: float = Field(default=1.0, ge=0)
    request_interval_seconds: float = Field(default=0.34, ge=0)
    retmax_per_variant: int = Field(default=50, ge=1, le=10_000)
    candidate_pool_per_query: int = Field(default=100, ge=1)
    efetch_batch_size: int = Field(default=100, ge=1, le=500)
    seed: int = 42


@dataclass
class _Response:
    content: bytes
    from_cache: bool
    retries: int
    status_code: int


class EUtilsClient:
    def __init__(self, config: PubMedConfig, cache_dir: Path, session: Any | None = None):
        self.config = config
        self.cache_dir = cache_dir
        self.session = session or requests.Session()
        self._last_request = 0.0
        self._rng = random.Random(config.seed)

    def get(self, endpoint: str, params: dict[str, str], suffix: str) -> _Response:
        safe = {**params, "tool": self.config.tool, "email": self.config.email}
        api_key = os.getenv(self.config.api_key_env)
        request_params = dict(safe)
        if api_key:
            request_params["api_key"] = api_key
        key = stable_hash({"version": PUBMED_ADAPTER_VERSION, "endpoint": endpoint, "params": safe})
        path = self.cache_dir / endpoint / f"{key}.{suffix}"
        if path.is_file():
            return _Response(path.read_bytes(), True, 0, 200)
        path.parent.mkdir(parents=True, exist_ok=True)
        retries = 0
        while True:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.config.request_interval_seconds:
                time.sleep(self.config.request_interval_seconds - elapsed)
            try:
                response = self.session.get(
                    f"{self.config.base_url.rstrip('/')}/{endpoint}.fcgi",
                    params=request_params,
                    timeout=self.config.timeout_seconds,
                )
                self._last_request = time.monotonic()
                if response.status_code == 429 or response.status_code >= 500:
                    if retries >= self.config.max_retries:
                        response.raise_for_status()
                    delay = _retry_delay(response, self.config.backoff_seconds, retries, self._rng)
                    time.sleep(delay)
                    retries += 1
                    continue
                response.raise_for_status()
                content = bytes(response.content)
                path.write_bytes(content)
                return _Response(content, False, retries, response.status_code)
            except (requests.Timeout, requests.ConnectionError):
                if retries >= self.config.max_retries:
                    raise
                time.sleep(self.config.backoff_seconds * (2**retries) + self._rng.random() * 0.1)
                retries += 1


def translate_pubmed_query(variant: str) -> str:
    """Apply deterministic PubMed fields without adding biological terms."""
    return _QUOTED_TERM.sub(lambda match: f'"{match.group(1)}"[Title/Abstract]', variant)


def acquire_pubmed(
    *, queries_path: Path, output_dir: Path, config: PubMedConfig, session: Any | None = None
) -> dict[str, Any]:
    queries = read_jsonl(queries_path, LiteratureQuery)
    raw_dir = output_dir / "raw" / "pubmed"
    client = EUtilsClient(config, raw_dir, session)
    retrieved_at = datetime.now(UTC)
    searches: list[dict[str, Any]] = []
    query_pmids: dict[str, dict[str, list[dict[str, int]]]] = {}
    retry_total = 0
    cache_hits = 0
    for query in queries:
        found: dict[str, list[dict[str, int]]] = {}
        for variant_index, variant in enumerate(query.query_variants):
            translated = translate_pubmed_query(variant)
            response = client.get(
                "esearch",
                {
                    "db": "pubmed",
                    "term": translated,
                    "retmode": "json",
                    "retmax": str(config.retmax_per_variant),
                    "sort": "relevance",
                    "retstart": "0",
                },
                "json",
            )
            retry_total += response.retries
            cache_hits += int(response.from_cache)
            payload = json.loads(response.content)
            result = payload.get("esearchresult", {})
            ids = [str(value) for value in result.get("idlist", [])]
            for rank, pmid in enumerate(ids, 1):
                found.setdefault(pmid, []).append({"variant_index": variant_index, "rank": rank})
            searches.append(
                {
                    "query_id": query.query_id,
                    "variant_index": variant_index,
                    "source_variant": variant,
                    "translated_query": translated,
                    "pubmed_query_translation": result.get("querytranslation"),
                    "count": int(result.get("count", 0)),
                    "pmids": ids,
                    "retrieved_at": retrieved_at.isoformat(),
                    "adapter_version": PUBMED_ADAPTER_VERSION,
                    "from_cache": response.from_cache,
                }
            )
        ordered = sorted(found, key=lambda value: min(x["rank"] for x in found[value]))
        query_pmids[query.query_id] = {
            pmid: found[pmid] for pmid in ordered[: config.candidate_pool_per_query]
        }
    all_pmids = list(dict.fromkeys(pmid for values in query_pmids.values() for pmid in values))
    articles: list[ArticleMetadata] = []
    parse_errors: list[str] = []
    for start in range(0, len(all_pmids), config.efetch_batch_size):
        batch = all_pmids[start : start + config.efetch_batch_size]
        response = client.get(
            "efetch",
            {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"},
            "xml",
        )
        retry_total += response.retries
        cache_hits += int(response.from_cache)
        raw_path = _cache_path(raw_dir, "efetch", response.content, "xml")
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            parse_errors.append(f"PMIDs {','.join(batch)}: {exc}")
            continue
        for record in root.findall("./PubmedArticle"):
            try:
                articles.append(_parse_pubmed_article(record, retrieved_at, raw_path))
            except (ValueError, TypeError) as exc:
                parse_errors.append(str(exc))
    articles = _deduplicate_articles(articles)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "pubmed_searches.jsonl", searches)
    write_jsonl(output_dir / "article_metadata.jsonl", articles)
    write_json(output_dir / "query_article_links.json", query_pmids)
    manifest = {
        "schema_version": 1,
        "adapter_version": PUBMED_ADAPTER_VERSION,
        "retrieved_at": retrieved_at.isoformat(),
        "query_count": len(queries),
        "search_count": len(searches),
        "unique_pmid_count": len(all_pmids),
        "article_count": len(articles),
        "abstract_count": sum(bool(item.abstract) for item in articles),
        "pmcid_count": sum(bool(item.pmcid) for item in articles),
        "cache_hits": cache_hits,
        "retry_count": retry_total,
        "parse_errors": parse_errors,
        "config": config.model_dump(exclude={"email"}),
        "contact_email_recorded": bool(config.email),
        "api_key_env": config.api_key_env,
        "api_key_configured": bool(os.getenv(config.api_key_env)),
        "api_key_value_recorded": False,
        "inputs": {"queries": file_sha256(queries_path)},
        "outputs": {
            name: file_sha256(output_dir / name)
            for name in (
                "pubmed_searches.jsonl",
                "article_metadata.jsonl",
                "query_article_links.json",
            )
        },
        "limitations": [
            "PubMed retrieval provides metadata and abstracts, not licensed full text.",
            "Retrieved articles remain UNASSESSED and are not scientific support by "
            "retrieval alone.",
        ],
    }
    write_json(output_dir / "pubmed_acquisition_manifest.json", manifest)
    return manifest


def _parse_pubmed_article(
    record: ET.Element, retrieved_at: datetime, raw_path: Path
) -> ArticleMetadata:
    citation = record.find("MedlineCitation")
    article = record.find("./MedlineCitation/Article")
    if citation is None or article is None:
        raise ValueError("PubMedArticle missing MedlineCitation/Article")
    pmid = _text(citation.find("PMID"))
    if not pmid:
        raise ValueError("PubMedArticle missing PMID")
    title = _all_text(article.find("ArticleTitle")) or f"Untitled PubMed record {pmid}"
    sections: list[dict[str, str]] = []
    for node in article.findall("./Abstract/AbstractText"):
        value = _all_text(node)
        if value:
            sections.append({"label": node.attrib.get("Label", ""), "text": value})
    ids = {
        node.attrib.get("IdType", "").lower(): _text(node)
        for node in record.findall("./PubmedData/ArticleIdList/ArticleId")
    }
    publication_types = [
        value
        for node in article.findall("./PublicationTypeList/PublicationType")
        if (value := _text(node))
    ]
    date_values = article.findall("./Journal/JournalIssue/PubDate/*")
    year = next((_year(_text(node)) for node in date_values if _year(_text(node))), None)
    if year is None:
        year = _year(_text(citation.find("DateCompleted/Year")))
    return ArticleMetadata(
        source_article_id=pmid,
        source=LiteratureSource.PUBMED,
        pmid=pmid,
        pmcid=ids.get("pmc"),
        doi=ids.get("doi"),
        title=title,
        abstract=" ".join(section["text"] for section in sections) or None,
        abstract_sections=sections,
        year=year,
        journal=_text(article.find("./Journal/Title")),
        publication_types=publication_types,
        is_review=any("review" in value.lower() for value in publication_types),
        keywords=[
            value
            for node in citation.findall("./KeywordList/Keyword")
            if (value := _all_text(node))
        ],
        mesh_terms=[
            value
            for node in citation.findall("./MeshHeadingList/MeshHeading/DescriptorName")
            if (value := _all_text(node))
        ],
        related_articles=[
            {"type": node.attrib.get("RefType", ""), "pmid": _text(node) or ""}
            for node in record.findall(
                "./PubmedData/ReferenceList/Reference/ArticleIdList/"
                "ArticleId[@IdType='pubmed']"
            )
        ],
        source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        full_text_status=(
            FullTextStatus.ABSTRACT_ONLY if sections else FullTextStatus.METADATA_ONLY
        ),
        retrieved_at=retrieved_at,
        raw_record_path=str(raw_path),
        raw_record_sha256=file_sha256(raw_path),
    )


def _deduplicate_articles(records: list[ArticleMetadata]) -> list[ArticleMetadata]:
    seen: set[str] = set()
    result: list[ArticleMetadata] = []
    for record in records:
        key = (
            f"pmid:{record.pmid}"
            if record.pmid
            else f"pmcid:{record.pmcid}"
            if record.pmcid
            else f"doi:{(record.doi or '').lower()}"
        )
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


def _cache_path(root: Path, endpoint: str, content: bytes, suffix: str) -> Path:
    digest = hashlib.sha256(content).hexdigest()
    matches = list((root / endpoint).glob(f"*.{suffix}"))
    for path in matches:
        if hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            return path
    raise FileNotFoundError("cached response path not found")


def _retry_delay(response: Any, base: float, retry: int, rng: random.Random) -> float:
    header = response.headers.get("Retry-After") if hasattr(response, "headers") else None
    try:
        return float(header) if header else base * (2**retry) + rng.random() * 0.1
    except ValueError:
        return base * (2**retry) + rng.random() * 0.1


def _text(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def _all_text(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    value = "".join(node.itertext()).strip()
    return re.sub(r"\s+", " ", value) or None


def _year(value: str | None) -> int | None:
    match = re.search(r"(?:16|17|18|19|20|21)\d{2}", value or "")
    return int(match.group()) if match else None
