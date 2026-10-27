from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dualrag.literature.chunking import normalize_and_chunk
from dualrag.literature.evaluation import (
    evaluate_literature,
    write_candidate_label_template,
    write_label_template,
)
from dualrag.literature.io import read_jsonl, write_jsonl
from dualrag.literature.packets import build_evidence_packets
from dualrag.literature.pmc import acquire_pmc_open_access
from dualrag.literature.pubmed import PubMedConfig, acquire_pubmed, translate_pubmed_query
from dualrag.literature.retrieval import retrieve_and_rerank
from dualrag.literature.schemas import (
    ArticleMetadata,
    EvidencePacket,
    LiteratureHit,
    LiteratureQuery,
)


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, esearch: bytes, efetch: bytes):
        self.esearch = esearch
        self.efetch = efetch
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, *, params: dict[str, str], timeout: float) -> FakeResponse:
        del timeout
        self.calls.append((url, params))
        return FakeResponse(self.esearch if "esearch.fcgi" in url else self.efetch)


class FakePmcSession:
    def get(self, url: str, *, params: dict[str, str], timeout: float) -> FakeResponse:
        del params, timeout
        if "esearch.fcgi" in url:
            return FakeResponse(
                b'{"esearchresult":{"count":"1","idlist":["123"]}}'
            )
        return FakeResponse(
            b"<article><front><article-meta><permissions><license>CC BY</license>"
            b"</permissions><abstract><p>Abstract text.</p></abstract></article-meta></front>"
            b"<body><sec><title>Results</title><p>P69905 activity was measured in an "
            b"assay.</p></sec></body></article>"
        )


def _query() -> LiteratureQuery:
    return LiteratureQuery(
        query_id="q1",
        query_accession="P69905",
        protein_name="hemoglobin subunit alpha",
        organism="Homo sapiens",
        taxonomy_id=9606,
        candidate_ids=["GO:0005344"],
        candidate_labels=["oxygen carrier activity"],
        cross_modal_status="CONSENSUS",
        query_terms=["P69905", "hemoglobin subunit alpha", "Homo sapiens"],
        query_variants=['"P69905" AND "oxygen carrier activity"'],
        query_builder_version="test-v1",
        source_biological_run_id="run-1",
        source_parameters_hash="abc",
        created_at=datetime(2026, 10, 26, tzinfo=UTC),
    )


def _pubmed_xml() -> bytes:
    return b"""<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle><MedlineCitation>
<PMID>123</PMID><Article><Journal><JournalIssue><PubDate><Year>2024</Year></PubDate>
</JournalIssue><Title>Journal X</Title></Journal><ArticleTitle>Hemoglobin experiment</ArticleTitle>
<Abstract><AbstractText Label="RESULTS">P69905 oxygen binding activity was measured
in Homo sapiens.</AbstractText></Abstract>
<PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList>
</Article><KeywordList><Keyword>hemoglobin</Keyword></KeywordList>
<MeshHeadingList><MeshHeading><DescriptorName>Hemoglobins</DescriptorName></MeshHeading></MeshHeadingList>
</MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="pubmed">123</ArticleId>
<ArticleId IdType="pmc">PMC123</ArticleId><ArticleId IdType="doi">10.1/test</ArticleId>
</ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>"""


def test_pubmed_acquisition_is_deterministic_and_redacts_secret(
    tmp_path: Path, monkeypatch: Any
) -> None:
    query_path = tmp_path / "queries.jsonl"
    write_jsonl(query_path, [_query()])
    session = FakeSession(
        json.dumps(
            {"esearchresult": {"count": "1", "idlist": ["123"], "querytranslation": "x"}}
        ).encode(),
        _pubmed_xml(),
    )
    monkeypatch.setenv("MY_NCBI_KEY", "do-not-record")
    manifest = acquire_pubmed(
        queries_path=query_path,
        output_dir=tmp_path / "output",
        config=PubMedConfig(
            email="test@example.org", api_key_env="MY_NCBI_KEY", request_interval_seconds=0
        ),
        session=session,
    )
    articles = read_jsonl(tmp_path / "output/article_metadata.jsonl", ArticleMetadata)
    assert manifest["article_count"] == 1
    assert articles[0].pmcid == "PMC123"
    assert articles[0].abstract_sections[0]["label"] == "RESULTS"
    assert all(call[1]["api_key"] == "do-not-record" for call in session.calls)
    assert manifest["api_key_configured"] is True
    assert "do-not-record" not in json.dumps(manifest)
    assert translate_pubmed_query('"P69905" AND "oxygen"') == (
        '"P69905"[Title/Abstract] AND "oxygen"[Title/Abstract]'
    )


def test_chunk_retrieve_packet_and_evaluate(tmp_path: Path) -> None:
    query_path = tmp_path / "queries.jsonl"
    article_path = tmp_path / "articles.jsonl"
    write_jsonl(query_path, [_query()])
    write_jsonl(
        article_path,
        [
            ArticleMetadata(
                source_article_id="123",
                source="PUBMED",
                pmid="123",
                title="Hemoglobin experiment",
                abstract="P69905 oxygen carrier activity was measured in Homo sapiens.",
                year=2024,
                source_url="https://pubmed.ncbi.nlm.nih.gov/123/",
                full_text_status="ABSTRACT_ONLY",
                retrieved_at=datetime(2026, 10, 26, tzinfo=UTC),
            )
        ],
    )
    links = tmp_path / "links.json"
    links.write_text('{"q1":{"123":[{"rank":1,"variant_index":0}]}}', encoding="utf-8")
    normalize_and_chunk(article_path=article_path, output_dir=tmp_path)
    retrieve_and_rerank(
        queries_path=query_path,
        chunks_path=tmp_path / "literature_chunks.jsonl",
        query_article_links_path=links,
        output_dir=tmp_path,
    )
    assert (tmp_path / "literature_candidates.jsonl").is_file()
    build_evidence_packets(
        queries_path=query_path,
        hits_path=tmp_path / "literature_hits.jsonl",
        output_dir=tmp_path,
    )
    hits = read_jsonl(tmp_path / "literature_hits.jsonl", LiteratureHit)
    packets = read_jsonl(tmp_path / "evidence_packets.jsonl", EvidencePacket)
    assert hits[0].entity_match == "EXACT_ACCESSION"
    assert hits[0].evidence_role == "UNASSESSED"
    assert packets[0].literature_hits[0].hit_id == hits[0].hit_id

    template = tmp_path / "labels.tsv"
    write_label_template(hits_path=tmp_path / "literature_hits.jsonl", output_path=template)
    with template.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for row in rows:
        for field in (
            "relevant",
            "citation_supported",
            "entity_correct",
            "organism_correct",
            "primary_experiment",
        ):
            row[field] = "true"
        row["contradiction"] = "false"
        row["annotator"] = "fixture"
    with template.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    result = evaluate_literature(
        hits_path=tmp_path / "literature_hits.jsonl",
        labels_path=template,
        output_dir=tmp_path / "evaluation",
        minimum_queries=2,
    )
    assert result["status"] == "INSUFFICIENT_MANUAL_LABELS"
    assert result["metrics"]["precision_at_1"] == 1.0


def test_pooled_evaluation_requires_complete_candidate_labels(tmp_path: Path) -> None:
    query_path = tmp_path / "queries.jsonl"
    article_path = tmp_path / "articles.jsonl"
    write_jsonl(query_path, [_query()])
    write_jsonl(
        article_path,
        [
            ArticleMetadata(
                source_article_id="123",
                source="PUBMED",
                pmid="123",
                title="Hemoglobin experiment",
                abstract="P69905 oxygen carrier activity was measured in Homo sapiens.",
                source_url="https://pubmed.ncbi.nlm.nih.gov/123/",
                full_text_status="ABSTRACT_ONLY",
                retrieved_at=datetime(2026, 10, 26, tzinfo=UTC),
            )
        ],
    )
    links = tmp_path / "links.json"
    links.write_text('{"q1":{"123":[{"rank":1,"variant_index":0}]}}', encoding="utf-8")
    normalize_and_chunk(article_path=article_path, output_dir=tmp_path)
    retrieve_and_rerank(
        queries_path=query_path,
        chunks_path=tmp_path / "literature_chunks.jsonl",
        query_article_links_path=links,
        output_dir=tmp_path,
    )
    labels = tmp_path / "pool-labels.tsv"
    write_candidate_label_template(
        candidates_path=tmp_path / "literature_candidates.jsonl", output_path=labels
    )
    with labels.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for row in rows:
        for field in (
            "relevant",
            "citation_supported",
            "entity_correct",
            "organism_correct",
            "primary_experiment",
        ):
            row[field] = "true"
        row["contradiction"] = "false"
        row["annotator"] = "human-test-fixture"
    with labels.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    acceptance = tmp_path / "acceptance.yaml"
    acceptance.write_text(
        """evaluation_version: test-v1
minimum_manually_labeled_queries: 1
minimum_contradiction_labels: 0
acceptance_policy:
  thresholds:
    query_candidate_coverage: 1.0
    precision_at_1: 1.0
""",
        encoding="utf-8",
    )
    result = evaluate_literature(
        hits_path=tmp_path / "literature_hits.jsonl",
        candidates_path=tmp_path / "literature_candidates.jsonl",
        queries_path=query_path,
        labels_path=labels,
        acceptance_path=acceptance,
        output_dir=tmp_path / "pooled-evaluation",
    )
    assert result["status"] == "PASS"
    assert result["candidate_pool_complete"] is True
    assert result["method_metrics"]["reranked"]["recall_at_10"] == 1.0


def test_pmc_requires_oa_check_and_preserves_license(tmp_path: Path) -> None:
    article_path = tmp_path / "articles.jsonl"
    write_jsonl(
        article_path,
        [
            ArticleMetadata(
                source_article_id="123",
                source="PUBMED",
                pmid="123",
                pmcid="PMC123",
                title="Full text article",
                source_url="https://pubmed.ncbi.nlm.nih.gov/123/",
                full_text_status="ABSTRACT_ONLY",
                retrieved_at=datetime(2026, 10, 26, tzinfo=UTC),
            )
        ],
    )
    output = tmp_path / "output"
    manifest = acquire_pmc_open_access(
        article_path=article_path,
        output_dir=output,
        config=PubMedConfig(email="test@example.org", request_interval_seconds=0),
        session=FakePmcSession(),
    )
    record = json.loads((output / "pmc_acquisitions.jsonl").read_text(encoding="utf-8"))
    assert manifest["open_access_count"] == 1
    assert record["license"] == "CC BY"
    assert Path(record["raw_full_text_path"]).is_file()


def test_hdd_runner_refuses_relative_root() -> None:
    script = Path("scripts/run_phase4_on_hdd.sh").read_text(encoding="utf-8")
    assert '[[ "$data_root" = /* ]]' in script
    assert "Refusing internal-disk fallback" in script
    assert "errors=remount-ro" in script
