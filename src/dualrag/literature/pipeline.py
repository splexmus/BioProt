from __future__ import annotations

from pathlib import Path
from typing import Any

from dualrag.io import write_json
from dualrag.literature.chunking import normalize_and_chunk
from dualrag.literature.packets import build_evidence_packets
from dualrag.literature.pmc import acquire_pmc_open_access
from dualrag.literature.pubmed import PubMedConfig, acquire_pubmed
from dualrag.literature.retrieval import retrieve_and_rerank


def run_literature_pipeline(
    *,
    queries_path: Path,
    output_dir: Path,
    config: PubMedConfig,
    fetch_pmc: bool = True,
    top_k: int = 20,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stages: dict[str, Any] = {}
    stages["pubmed"] = acquire_pubmed(
        queries_path=queries_path, output_dir=output_dir, config=config
    )
    pmc_path: Path | None = None
    if fetch_pmc:
        stages["pmc"] = acquire_pmc_open_access(
            article_path=output_dir / "article_metadata.jsonl",
            output_dir=output_dir,
            config=config,
        )
        pmc_path = output_dir / "pmc_acquisitions.jsonl"
    stages["chunking"] = normalize_and_chunk(
        article_path=output_dir / "article_metadata.jsonl",
        output_dir=output_dir,
        pmc_acquisitions_path=pmc_path,
    )
    stages["retrieval"] = retrieve_and_rerank(
        queries_path=queries_path,
        chunks_path=output_dir / "literature_chunks.jsonl",
        query_article_links_path=output_dir / "query_article_links.json",
        output_dir=output_dir,
        top_k=top_k,
    )
    stages["packets"] = build_evidence_packets(
        queries_path=queries_path,
        hits_path=output_dir / "literature_hits.jsonl",
        output_dir=output_dir,
    )
    manifest = {
        "schema_version": 1,
        "phase": "4.3-4.6",
        "status": "PIPELINE_COMPLETE_EVALUATION_PENDING",
        "stages": {
            name: {
                key: value
                for key, value in stage.items()
                if key
                in {
                    "adapter_version",
                    "chunker_version",
                    "retriever_version",
                    "builder_version",
                    "article_count",
                    "chunk_count",
                    "candidate_count",
                    "hit_count",
                    "packet_count",
                }
            }
            for name, stage in stages.items()
        },
        "phase_4_7_note": (
            "Generate and manually complete the label template, then run evaluate-literature."
        ),
    }
    write_json(output_dir / "phase4_run_manifest.json", manifest)
    return manifest
