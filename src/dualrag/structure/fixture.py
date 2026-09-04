from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from dualrag.io import read_tsv
from dualrag.models import ProteinQuery, StructureEvidence
from dualrag.parsing import optional_bool, optional_float, optional_int, terms

REQUIRED_COLUMNS = {
    "query_id",
    "target_structure_id",
    "tool",
    "tool_version",
    "database",
    "database_version",
}


def retrieve(
    queries: list[ProteinQuery], fixture_path: Path, raw_output_path: Path, top_k: int
) -> list[StructureEvidence]:
    """Read synthetic tool output and preserve an exact raw copy in the run directory."""
    raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture_path, raw_output_path)
    rows = read_tsv(raw_output_path)
    missing = REQUIRED_COLUMNS - (set(rows[0]) if rows else set())
    if missing:
        raise ValueError(f"structure fixture lacks columns: {', '.join(sorted(missing))}")
    query_ids = {query.query_id for query in queries}
    grouped: dict[str, list[StructureEvidence]] = defaultdict(list)
    for row in rows:
        if row["query_id"] not in query_ids:
            continue
        grouped[row["query_id"]].append(
            StructureEvidence(
                query_id=row["query_id"],
                target_structure_id=row["target_structure_id"],
                target_uniprot_id=row.get("target_uniprot_id") or None,
                tool=row["tool"],
                tool_version=row["tool_version"],
                database=row["database"],
                database_version=row["database_version"],
                foldseek_evalue=optional_float(row.get("foldseek_evalue")),
                foldseek_score=optional_float(row.get("foldseek_score")),
                tm_score=optional_float(row.get("tm_score")),
                alignment_length=optional_int(row.get("alignment_length")),
                query_coverage=optional_float(row.get("query_coverage")),
                target_coverage=optional_float(row.get("target_coverage")),
                sequence_identity=optional_float(row.get("sequence_identity")),
                protein_name=row.get("protein_name") or None,
                interpro_ids=terms(row.get("interpro_ids")),
                supfam_ids=terms(row.get("supfam_ids")),
                structure_source=row.get("structure_source") or None,
                experimental_structure=optional_bool(row.get("experimental_structure")),
                raw_output_path=str(raw_output_path),
                source_accession=row.get("source_accession") or row["target_structure_id"],
            )
        )
    return [hit for query in queries for hit in grouped[query.query_id][:top_k]]
