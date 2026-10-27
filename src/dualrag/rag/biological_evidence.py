from __future__ import annotations

import csv
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, write_json
from dualrag.literature.io import read_jsonl, write_jsonl
from dualrag.literature.schemas import (
    BiologicalEvidenceReference,
    EvidenceModality,
    EvidencePacket,
)

BIOLOGICAL_ENRICHER_VERSION = "phase5-biological-evidence-v1"
MAX_TOTAL_BIOLOGICAL_RECORDS = 10


def enrich_evidence_packets(
    *,
    packets_path: Path,
    sequence_evidence_path: Path,
    structure_evidence_path: Path,
    output_path: Path,
    manifest_path: Path,
    max_per_modality: int = 5,
    source_manifest_path: Path | None = None,
) -> dict[str, Any]:
    if max_per_modality < 1:
        raise ValueError("max_per_modality must be positive")
    if max_per_modality * 2 > MAX_TOTAL_BIOLOGICAL_RECORDS:
        raise ValueError("at most 10 total biological records are allowed per packet")

    packets = read_jsonl(packets_path, EvidencePacket)
    sequence_rows = _read_tsv(sequence_evidence_path)
    structure_rows = _read_tsv(structure_evidence_path)
    sequence_by_query = _group_by_accession(sequence_rows)
    structure_by_query = _group_by_accession(structure_rows)

    enriched: list[EvidencePacket] = []
    modality_counts = {"SEQUENCE": 0, "STRUCTURE": 0}
    missing = {"SEQUENCE": [], "STRUCTURE": []}
    for packet in packets:
        accession = packet.query.query_accession or _accession(packet.query.query_id)
        sequence = _select(sequence_by_query.get(accession, []), max_per_modality)
        structure = _select(structure_by_query.get(accession, []), max_per_modality)
        if not sequence:
            missing["SEQUENCE"].append(packet.query.query_id)
        if not structure:
            missing["STRUCTURE"].append(packet.query.query_id)
        biological = [
            _sequence_reference(
                row,
                rank=index,
                query=packet,
                artifact_path=sequence_evidence_path,
            )
            for index, row in enumerate(sequence, start=1)
        ]
        biological.extend(
            _structure_reference(
                row,
                rank=index,
                query=packet,
                artifact_path=structure_evidence_path,
            )
            for index, row in enumerate(structure, start=1)
        )
        modality_counts["SEQUENCE"] += len(sequence)
        modality_counts["STRUCTURE"] += len(structure)
        boundaries = list(packet.claim_boundaries)
        boundaries.extend(
            boundary
            for boundary in (
                "Sequence and structure retrieval records are computational evidence and "
                "must remain separate modalities.",
                "A Foldseek structural match is not automatically a sequence homolog or "
                "an exact-function match.",
                "Transferred GO, EC, InterPro, Pfam, or SUPFAM annotations are candidate "
                "context, not experimental confirmation for the query protein.",
                "GO annotations in source hits are preserved without assuming Molecular "
                "Function aspect unless an aspect-aware mapping explicitly establishes it.",
            )
            if boundary not in boundaries
        )
        enriched.append(
            EvidencePacket.model_validate(
                {
                    **packet.model_dump(mode="python"),
                    "biological_evidence": biological,
                    "claim_boundaries": boundaries,
                }
            )
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_path, enriched)
    now = datetime.now(UTC)
    inputs = {
        "packets": _input_record(packets_path),
        "sequence_evidence": _input_record(sequence_evidence_path),
        "structure_evidence": _input_record(structure_evidence_path),
    }
    if source_manifest_path is not None:
        inputs["source_manifest"] = _input_record(source_manifest_path)
    manifest = {
        "schema_version": 1,
        "enricher_version": BIOLOGICAL_ENRICHER_VERSION,
        "created_at": now.isoformat(),
        "packet_count": len(enriched),
        "max_per_modality": max_per_modality,
        "modality_record_counts": modality_counts,
        "queries_without_modality": missing,
        "inputs": inputs,
        "output": _input_record(output_path),
        "selection": "descending normalized_score with stable target-ID tie break",
        "gold_labels_used": False,
        "claim_boundary": (
            "Records are leakage-filtered computational retrieval evidence. Scores rank "
            "hits within their modality and are not calibrated confidence probabilities."
        ),
    }
    write_json(manifest_path, manifest)
    return manifest


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _group_by_accession(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[_accession(row.get("query_id", ""))].append(row)
    return grouped


def _accession(identifier: str) -> str:
    fields = identifier.split("|")
    if len(fields) >= 3 and fields[0] in {"sp", "tr"}:
        return fields[1]
    return identifier


def _select(rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            -(_float(row.get("normalized_score")) or 0.0),
            row.get("target_id") or row.get("target_structure_id") or "",
        ),
    )[:limit]


def _sequence_reference(
    row: dict[str, str],
    *,
    rank: int,
    query: EvidencePacket,
    artifact_path: Path,
) -> BiologicalEvidenceReference:
    target = _required(row, "target_id")
    return BiologicalEvidenceReference(
        modality=EvidenceModality.SEQUENCE,
        evidence_id=f"bio:sequence:{target}",
        target_id=target,
        label=row.get("protein_name") or target,
        rank=rank,
        score=_float(row.get("normalized_score")) or 0.0,
        raw_metrics=_metrics(
            row,
            "sequence_identity",
            "alignment_coverage",
            "evalue",
            "bitscore",
        ),
        annotations=_annotations(
            row,
            "orthologous_group",
            "go_terms",
            "ec_numbers",
            "kegg_terms",
            "interpro_ids",
            "pfam_ids",
        ),
        tool=row.get("tool") or None,
        tool_version=row.get("tool_version") or None,
        database=row.get("database") or None,
        database_version=row.get("database_version") or None,
        normalization_version=row.get("normalization_version") or None,
        source_ids=_unique([target, row.get("source_accession", "")]),
        run_id=query.query.source_biological_run_id,
        parameters_hash=query.query.source_parameters_hash,
        artifact_path=str(artifact_path),
    )


def _structure_reference(
    row: dict[str, str],
    *,
    rank: int,
    query: EvidencePacket,
    artifact_path: Path,
) -> BiologicalEvidenceReference:
    target = _required(row, "target_structure_id")
    target_uniprot = row.get("target_uniprot_id", "")
    return BiologicalEvidenceReference(
        modality=EvidenceModality.STRUCTURE,
        evidence_id=f"bio:structure:{target}",
        target_id=target,
        label=row.get("protein_name") or target_uniprot or target,
        rank=rank,
        score=_float(row.get("normalized_score")) or 0.0,
        raw_metrics=_metrics(
            row,
            "foldseek_evalue",
            "foldseek_score",
            "tm_score",
            "alignment_length",
            "query_coverage",
            "target_coverage",
            "sequence_identity",
        ),
        annotations=_annotations(
            row,
            "go_terms",
            "ec_numbers",
            "interpro_ids",
            "supfam_ids",
        ),
        tool=row.get("tool") or None,
        tool_version=row.get("tool_version") or None,
        database=row.get("database") or None,
        database_version=row.get("database_version") or None,
        normalization_version=row.get("normalization_version") or None,
        structure_source=row.get("structure_source") or None,
        experimental_structure=_bool(row.get("experimental_structure")),
        source_ids=_unique([target, target_uniprot, row.get("source_accession", "")]),
        run_id=query.query.source_biological_run_id,
        parameters_hash=query.query.source_parameters_hash,
        artifact_path=str(artifact_path),
    )


def _metrics(row: dict[str, str], *fields: str) -> dict[str, float | int | str | bool | None]:
    result: dict[str, float | int | str | bool | None] = {}
    for field in fields:
        value = row.get(field, "").strip()
        if not value:
            continue
        parsed = _float(value)
        result[field] = parsed if parsed is not None else value
    return result


def _annotations(row: dict[str, str], *fields: str) -> dict[str, list[str]]:
    return {
        field: [value for value in row.get(field, "").split(";") if value]
        for field in fields
        if row.get(field, "").strip()
    }


def _float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _bool(value: str | None) -> bool | None:
    if value is None or not value.strip():
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise ValueError(f"invalid boolean value {value!r}")


def _required(row: dict[str, str], field: str) -> str:
    value = row.get(field, "").strip()
    if not value:
        raise ValueError(f"biological evidence row is missing {field}")
    return value


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _input_record(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": file_sha256(path)}
