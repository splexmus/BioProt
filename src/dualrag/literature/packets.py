from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, write_json
from dualrag.literature.io import read_jsonl, write_jsonl
from dualrag.literature.schemas import EvidencePacket, EvidenceRole, LiteratureHit, LiteratureQuery

PACKET_BUILDER_VERSION = "compact-evidence-packet-v1"


def build_evidence_packets(
    *, queries_path: Path, hits_path: Path, output_dir: Path
) -> dict[str, Any]:
    queries = read_jsonl(queries_path, LiteratureQuery)
    hits = read_jsonl(hits_path, LiteratureHit)
    by_query: dict[str, list[LiteratureHit]] = {}
    for hit in hits:
        by_query.setdefault(hit.query_id, []).append(hit)
    now = datetime.now(UTC)
    packets: list[EvidencePacket] = []
    for query in queries:
        selected = sorted(by_query.get(query.query_id, []), key=lambda value: value.rank)[:20]
        packets.append(
            EvidencePacket(
                packet_id=f"packet:{query.source_biological_run_id}:{query.query_id}",
                query=query,
                biological_evidence=[],
                literature_hits=selected,
                alternative_hypotheses=query.alternative_hypotheses,
                contradiction_hit_ids=[
                    hit.hit_id
                    for hit in selected
                    if hit.evidence_role is EvidenceRole.CONTRADICTION
                ],
                claim_boundaries=[
                    "This packet supports a putative functional hypothesis, not "
                    "experimental confirmation.",
                    "Retrieval scores rank passages and are not calibrated biological confidence.",
                    "UNASSESSED passages are neither support nor contradiction.",
                    "Homolog, organism, and rule-based entity assignments require "
                    "expert verification.",
                    "Missing literature or full text is not negative biological evidence.",
                ],
                created_at=now,
            )
        )
    write_jsonl(output_dir / "evidence_packets.jsonl", packets)
    manifest = {
        "schema_version": 1,
        "builder_version": PACKET_BUILDER_VERSION,
        "created_at": now.isoformat(),
        "packet_count": len(packets),
        "hit_count": sum(len(packet.literature_hits) for packet in packets),
        "inputs": {"queries": file_sha256(queries_path), "hits": file_sha256(hits_path)},
        "output": {
            "path": str(output_dir / "evidence_packets.jsonl"),
            "sha256": file_sha256(output_dir / "evidence_packets.jsonl"),
        },
        "biological_reference_note": (
            "The Phase 4.2 query record preserves the biological run ID, parameter hash, "
            "candidates, homologs, and cross-modal state. Full biological tables remain upstream."
        ),
    }
    write_json(output_dir / "evidence_packet_manifest.json", manifest)
    return manifest
