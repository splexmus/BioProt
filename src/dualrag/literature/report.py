from __future__ import annotations

from pathlib import Path

from dualrag.io import file_sha256, write_tsv
from dualrag.literature.io import read_jsonl
from dualrag.literature.schemas import LiteratureHit, LiteratureQuery


def write_top_literature_report(
    *, queries_path: Path, hits_path: Path, output_dir: Path
) -> dict[str, object]:
    """Render the actual top ten ranked passages per query without promoting roles."""
    queries = read_jsonl(queries_path, LiteratureQuery)
    hits = read_jsonl(hits_path, LiteratureHit)
    lines = [
        "# Top literature passages",
        "",
        "Retrieval scores rank passages; they are not confidence probabilities.",
        "UNASSESSED passages provide context, not verified support or contradiction.",
        "",
    ]
    rows = []
    for query in queries:
        lines.extend([f"## {query.query_id}", ""])
        selected = sorted(
            [h for h in hits if h.query_id == query.query_id], key=lambda h: (h.rank, h.hit_id)
        )[:10]
        if not selected:
            lines.extend(["No literature hits retrieved; this is not contradiction.", ""])
        for hit in selected:
            chunk = hit.chunk
            citation = chunk.pmid or chunk.pmcid or chunk.doi or chunk.source_article_id
            lines.extend(
                [
                    f"### {hit.rank}. {chunk.title}",
                    "",
                    f"- Citation: [{citation}]({chunk.source_url})",
                    f"- Evidence ID: `{hit.hit_id}`; role: `{hit.evidence_role}`",
                    f"- Score: {hit.retrieval_score}; entity: `{hit.entity_match}`; "
                    f"organism: `{hit.organism_match}`",
                    f"- Section: `{chunk.section_type}`; full text: `{chunk.full_text_status}`",
                    f"- Primary experiment: {hit.is_primary_experiment}; "
                    f"retrieved: {hit.retrieved_at.isoformat()}",
                    "",
                    *[f"> {line}" for line in chunk.text.splitlines()],
                    "",
                ]
            )
            rows.append(
                {
                    "query_id": query.query_id,
                    "rank": hit.rank,
                    "hit_id": hit.hit_id,
                    "title": chunk.title,
                    "citation": citation,
                    "source_url": chunk.source_url,
                    "score": hit.retrieval_score,
                    "role": hit.evidence_role,
                    "entity_match": hit.entity_match,
                    "organism_match": hit.organism_match,
                    "passage": chunk.text,
                }
            )
    markdown = output_dir / "top_literature.md"
    markdown.write_text("\n".join(lines), encoding="utf-8")
    table = output_dir / "top_literature.tsv"
    write_tsv(
        table,
        rows,
        [
            "query_id",
            "rank",
            "hit_id",
            "title",
            "citation",
            "source_url",
            "score",
            "role",
            "entity_match",
            "organism_match",
            "passage",
        ],
    )
    return {
        "path": str(markdown),
        "sha256": file_sha256(markdown),
        "table_sha256": file_sha256(table),
        "passage_count": len(rows),
    }
