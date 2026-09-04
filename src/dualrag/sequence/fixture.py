from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from dualrag.io import read_tsv
from dualrag.models import ProteinQuery, SequenceEvidence
from dualrag.parsing import optional_float, terms

REQUIRED_COLUMNS = {
    "query_id",
    "target_id",
    "tool",
    "tool_version",
    "database",
    "database_version",
}


def retrieve(
    queries: list[ProteinQuery], fixture_path: Path, raw_output_path: Path, top_k: int
) -> list[SequenceEvidence]:
    """Read synthetic tool output and preserve an exact raw copy in the run directory."""
    raw_output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture_path, raw_output_path)
    rows = read_tsv(raw_output_path)
    missing = REQUIRED_COLUMNS - (set(rows[0]) if rows else set())
    if missing:
        raise ValueError(f"sequence fixture lacks columns: {', '.join(sorted(missing))}")
    query_ids = {query.query_id for query in queries}
    grouped: dict[str, list[SequenceEvidence]] = defaultdict(list)
    for row in rows:
        if row["query_id"] not in query_ids:
            continue
        grouped[row["query_id"]].append(
            SequenceEvidence(
                query_id=row["query_id"],
                target_id=row["target_id"],
                tool=row["tool"],
                tool_version=row["tool_version"],
                database=row["database"],
                database_version=row["database_version"],
                sequence_identity=optional_float(row.get("sequence_identity")),
                alignment_coverage=optional_float(row.get("alignment_coverage")),
                evalue=optional_float(row.get("evalue")),
                bitscore=optional_float(row.get("bitscore")),
                orthologous_group=row.get("orthologous_group") or None,
                protein_name=row.get("protein_name") or None,
                go_terms=terms(row.get("go_terms")),
                ec_numbers=terms(row.get("ec_numbers")),
                kegg_terms=terms(row.get("kegg_terms")),
                interpro_ids=terms(row.get("interpro_ids")),
                pfam_ids=terms(row.get("pfam_ids")),
                raw_output_path=str(raw_output_path),
                source_accession=row.get("source_accession") or row["target_id"],
            )
        )
    return [hit for query in queries for hit in grouped[query.query_id][:top_k]]
