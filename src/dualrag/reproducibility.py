from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

TABLE_IGNORED_COLUMNS = {
    "raw_output_path",
    "seq_raw_output_path",
    "struct_raw_output_path",
}
METADATA_FIELDS = [
    "package_version",
    "python_version",
    "input_sha256",
    "parameters_hash",
    "sequence_backend",
    "structure_backend",
    "synthetic_fixture_data",
    "query_count",
    "sequence_hit_count",
    "structure_hit_count",
    "merged_row_count",
]
ACQUISITION_FIELDS = [
    "query_id",
    "requested_uniprot_accession",
    "resolution_method",
    "api_base_url",
    "request_url",
    "alphafold_entry_id",
    "model_version",
    "structure_format",
    "source_structure_url",
    "sha256",
    "sequence_compatible",
]


def compare_runs(first: Path, second: Path) -> dict[str, Any]:
    """Compare stable biological and provenance fields from two completed runs."""
    first = first.resolve()
    second = second.resolve()
    artifacts: dict[str, dict[str, Any]] = {}
    for name in [
        "queries.tsv",
        "sequence_results.tsv",
        "structure_results.tsv",
        "merged_results.tsv",
    ]:
        left = _stable_table(first / name, group_by_query=name != "queries.tsv")
        right = _stable_table(second / name, group_by_query=name != "queries.tsv")
        artifacts[name] = _comparison(left, right)

    left_config = yaml.safe_load((first / "config.snapshot.yaml").read_text(encoding="utf-8"))
    right_config = yaml.safe_load(
        (second / "config.snapshot.yaml").read_text(encoding="utf-8")
    )
    artifacts["config.snapshot.yaml"] = _comparison(left_config, right_config)

    left_metadata = json.loads((first / "run_metadata.json").read_text(encoding="utf-8"))
    right_metadata = json.loads((second / "run_metadata.json").read_text(encoding="utf-8"))
    artifacts["run_metadata.json"] = _comparison(
        {field: left_metadata.get(field) for field in METADATA_FIELDS},
        {field: right_metadata.get(field) for field in METADATA_FIELDS},
    )

    left_acquisition = _stable_acquisitions(first / "alphafold_acquisition.tsv")
    right_acquisition = _stable_acquisitions(second / "alphafold_acquisition.tsv")
    artifacts["alphafold_acquisition.tsv"] = _comparison(
        left_acquisition, right_acquisition
    )

    return {
        "schema_version": 1,
        "first_run": str(first),
        "second_run": str(second),
        "equivalent": all(item["equivalent"] for item in artifacts.values()),
        "ignored_table_columns": sorted(TABLE_IGNORED_COLUMNS),
        "cross_query_block_order_ignored": True,
        "within_query_rank_order_preserved": True,
        "artifacts": artifacts,
    }


def _stable_table(
    path: Path, *, group_by_query: bool
) -> list[dict[str, str]] | dict[str, list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        if not rows.fieldnames:
            raise ValueError(f"TSV has no header: {path}")
        stable_rows = [
            {key: value for key, value in row.items() if key not in TABLE_IGNORED_COLUMNS}
            for row in rows
        ]
    if not group_by_query:
        return stable_rows
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in stable_rows:
        query_id = row.get("query_id")
        if not query_id:
            raise ValueError(f"TSV row has no query_id: {path}")
        grouped.setdefault(query_id, []).append(row)
    return grouped


def _stable_acquisitions(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [
        {
            **{field: row.get(field, "") for field in ACQUISITION_FIELDS},
            "availability": _availability(row.get("status", "")),
        }
        for row in rows
    ]


def _availability(status: str) -> str:
    if status in {"DOWNLOADED", "CACHED"}:
        return "AVAILABLE"
    return status


def _comparison(left: object, right: object) -> dict[str, Any]:
    return {
        "equivalent": left == right,
        "first_digest": _digest(left),
        "second_digest": _digest(right),
    }


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()
