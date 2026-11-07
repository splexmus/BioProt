from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from dualrag.benchmark.dataset import _sha256_file, _write_tsv


def materialize_split_view(
    *,
    pipeline_dir: Path,
    alignments_path: Path,
    output_dir: Path,
    include_splits: set[str],
) -> dict[str, object]:
    """Create a query-scoped benchmark view without consulting sealed test labels."""
    if output_dir.exists():
        raise FileExistsError(f"output already exists: {output_dir}")
    split_rows = _read_tsv(pipeline_dir / "splits.tsv")
    selected = {
        row["accession"] for row in split_rows if row["split"] in include_splits
    }
    if not selected:
        raise ValueError("no accessions matched the requested splits")

    output_dir.mkdir(parents=True)
    query_rows = _filter_rows(
        pipeline_dir / "queries.tsv", lambda row: row["accession"] in selected
    )
    if {row["accession"] for row in query_rows} != selected:
        raise ValueError("queries.tsv does not contain every selected accession")
    _write_rows(output_dir / "queries.tsv", query_rows)
    (output_dir / "queries.fasta").write_text(
        "".join(
            f">{row['fasta_id']}\n{row['canonical_sequence']}\n" for row in query_rows
        ),
        encoding="utf-8",
    )

    accession_tables = (
        "splits.tsv",
        "cluster_membership.tsv",
        "difficulty_strata.tsv",
        "domain_labels.tsv",
        "exposed_queries.tsv",
        "gold_labels.tsv",
    )
    for name in accession_tables:
        rows = _filter_rows(
            pipeline_dir / name, lambda row, key="accession": row[key] in selected
        )
        _write_rows(output_dir / name, rows, source=pipeline_dir / name)

    prohibited = _filter_rows(
        pipeline_dir / "prohibited_targets.tsv",
        lambda row: row["query_accession"] in selected,
    )
    _write_rows(output_dir / "prohibited_targets.tsv", prohibited)

    alignment_rows = _filter_rows(
        alignments_path,
        lambda row: _accession(row["query"]) in selected,
        fieldnames=["query", "target", "fident", "qcov", "tcov", "evalue", "bits"],
        has_header=False,
    )
    _write_rows(
        output_dir / "reference_alignments.tsv",
        alignment_rows,
        fieldnames=["query", "target", "fident", "qcov", "tcov", "evalue", "bits"],
        include_header=False,
    )

    split_counts = Counter(row["split"] for row in split_rows if row["accession"] in selected)
    gold_rows = _read_tsv(output_dir / "gold_labels.tsv")
    unexpected_gold = sorted({row["split"] for row in gold_rows} - include_splits)
    if unexpected_gold:
        raise ValueError(f"unexpected gold-label splits in output: {unexpected_gold}")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "pipeline_source": str(pipeline_dir),
        "alignment_source": str(alignments_path),
        "included_splits": sorted(include_splits),
        "query_count": len(selected),
        "split_counts": dict(sorted(split_counts.items())),
        "gold_label_row_count": len(gold_rows),
        "contains_test_queries": "test" in split_counts,
        "contains_test_gold": any(row["split"] == "test" for row in gold_rows),
        "sealed_test_vault_accessed": False,
    }
    (output_dir / "split_view_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths = sorted(path for path in output_dir.iterdir() if path.name != "CHECKSUMS.sha256")
    (output_dir / "CHECKSUMS.sha256").write_text(
        "".join(f"{_sha256_file(path)}  {path.name}\n" for path in paths),
        encoding="utf-8",
    )
    return manifest


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _filter_rows(
    path: Path,
    predicate,
    *,
    fieldnames: list[str] | None = None,
    has_header: bool = True,
) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            handle,
            fieldnames=None if has_header else fieldnames,
            delimiter="\t",
        )
        return [row for row in reader if predicate(row)]


def _write_rows(
    path: Path,
    rows: list[dict[str, str]],
    *,
    source: Path | None = None,
    fieldnames: list[str] | None = None,
    include_header: bool = True,
) -> None:
    if fieldnames is None:
        if rows:
            fieldnames = list(rows[0])
        elif source is not None:
            with source.open(encoding="utf-8", newline="") as handle:
                fieldnames = next(csv.reader(handle, delimiter="\t"))
        else:
            raise ValueError(f"cannot infer columns for empty table: {path.name}")
    if include_header:
        _write_tsv(path, fieldnames, rows)
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
        )
        writer.writerows(rows)


def _accession(identifier: str) -> str:
    parts = identifier.split("|")
    return parts[1] if len(parts) >= 3 else identifier
