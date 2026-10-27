from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, write_json
from dualrag.literature.io import read_jsonl, write_jsonl
from dualrag.literature.pubmed import EUtilsClient, PubMedConfig
from dualrag.literature.schemas import ArticleMetadata, FullTextStatus

PMC_ADAPTER_VERSION = "pmc-oa-eutils-v1"


def acquire_pmc_open_access(
    *, article_path: Path, output_dir: Path, config: PubMedConfig, session: Any | None = None
) -> dict[str, Any]:
    """Acquire full text only after PMC OA service confirms reusable availability."""
    articles = read_jsonl(article_path, ArticleMetadata)
    raw_dir = output_dir / "raw" / "pmc"
    client = EUtilsClient(config, raw_dir, session)
    retrieved_at = datetime.now(UTC)
    records: list[dict[str, Any]] = []
    for article in articles:
        if not article.pmcid:
            records.append(_state(article, FullTextStatus.NOT_FOUND, "No PMCID in PubMed record"))
            continue
        try:
            eligibility_response = client.get(
                "esearch",
                {
                    "db": "pmc",
                    "term": (
                        f'{article.pmcid}[pmcid] AND '
                        "(open_access[filter] OR author_manuscript[filter]) "
                        "NOT pmc embargo[filter]"
                    ),
                    "retmode": "json",
                    "retmax": "1",
                },
                "json",
            )
            eligibility = json.loads(eligibility_response.content).get("esearchresult", {})
            if not eligibility.get("idlist"):
                records.append(
                    _state(
                        article,
                        FullTextStatus.NOT_OPEN_ACCESS,
                        "Not present in the PMC open-access or author-manuscript filter",
                    )
                )
                continue
            full_response = client.get(
                "efetch",
                {"db": "pmc", "id": article.pmcid.removeprefix("PMC"), "retmode": "xml"},
                "xml",
            )
            path = raw_dir / "fulltext" / f"{article.pmcid}.xml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(full_response.content)
            root = ET.fromstring(full_response.content)
            license_text = _all_text(root.find(".//article-meta/permissions/license"))
            records.append(
                {
                    **_state(article, FullTextStatus.PMC_OPEN_ACCESS, None),
                    "raw_full_text_path": str(path),
                    "raw_full_text_sha256": file_sha256(path),
                    "license": license_text,
                    "source_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{article.pmcid}/",
                    "retrieved_at": retrieved_at.isoformat(),
                    "from_cache": full_response.from_cache,
                }
            )
        except Exception as exc:  # boundary failure is recorded per article
            records.append(
                _state(
                    article,
                    FullTextStatus.RETRIEVAL_ERROR,
                    _redact_error(str(exc), config),
                )
            )
    write_jsonl(output_dir / "pmc_acquisitions.jsonl", records)
    manifest = {
        "schema_version": 1,
        "adapter_version": PMC_ADAPTER_VERSION,
        "retrieved_at": retrieved_at.isoformat(),
        "article_count": len(articles),
        "pmcid_count": sum(bool(item.pmcid) for item in articles),
        "open_access_count": sum(
            item["full_text_status"] == FullTextStatus.PMC_OPEN_ACCESS for item in records
        ),
        "not_open_access_count": sum(
            item["full_text_status"] == FullTextStatus.NOT_OPEN_ACCESS for item in records
        ),
        "retrieval_error_count": sum(
            item["full_text_status"] == FullTextStatus.RETRIEVAL_ERROR for item in records
        ),
        "input": {"path": str(article_path), "sha256": file_sha256(article_path)},
        "output": {
            "path": str(output_dir / "pmc_acquisitions.jsonl"),
            "sha256": file_sha256(output_dir / "pmc_acquisitions.jsonl"),
        },
        "limitations": [
            "PMC acquisition is attempted only when an ESearch license/access filter confirms "
            "open-access or author-manuscript availability.",
            "Article-specific license text is retained and must govern downstream reuse.",
        ],
    }
    write_json(output_dir / "pmc_acquisition_manifest.json", manifest)
    return manifest


def _state(
    article: ArticleMetadata, status: FullTextStatus, error: str | None
) -> dict[str, Any]:
    return {
        "source_article_id": article.source_article_id,
        "pmid": article.pmid,
        "pmcid": article.pmcid,
        "doi": article.doi,
        "full_text_status": status,
        "acquisition_error": error,
        "raw_full_text_path": None,
        "raw_full_text_sha256": None,
        "license": None,
        "source_url": article.source_url,
        "retrieved_at": article.retrieved_at.isoformat(),
        "from_cache": False,
    }


def _all_text(node: ET.Element | None) -> str | None:
    if node is None:
        return None
    value = re.sub(r"\s+", " ", "".join(node.itertext())).strip()
    return value or None


def _redact_error(value: str, config: PubMedConfig) -> str:
    redacted = re.sub(r"([?&]api_key=)[^&\s]+", r"\1<redacted>", value)
    redacted = redacted.replace(config.email, "<redacted-email>")
    return redacted
