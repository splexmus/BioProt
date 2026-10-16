from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from dualrag.reproducibility import compare_runs


def _write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _make_run(path: Path, raw_path: str, status: str = "DOWNLOADED") -> None:
    path.mkdir()
    _write_tsv(path / "queries.tsv", [{"query_id": "P1", "sequence": "MA"}])
    _write_tsv(
        path / "sequence_results.tsv",
        [{"query_id": "P1", "target_id": "S1", "raw_output_path": raw_path}],
    )
    _write_tsv(
        path / "structure_results.tsv",
        [
            {
                "query_id": "P1",
                "target_structure_id": "1abc_A",
                "raw_output_path": raw_path,
            }
        ],
    )
    _write_tsv(
        path / "merged_results.tsv",
        [
            {
                "query_id": "P1",
                "cross_modal_status": "CONSENSUS",
                "seq_raw_output_path": raw_path,
                "struct_raw_output_path": raw_path,
            }
        ],
    )
    _write_tsv(
        path / "alphafold_acquisition.tsv",
        [
            {
                "query_id": "P1",
                "requested_uniprot_accession": "P1",
                "resolution_method": "test",
                "api_base_url": "https://example.test/api",
                "request_url": "https://example.test/api/P1",
                "alphafold_entry_id": "AF-P1-F1",
                "model_version": "6",
                "structure_format": "cif",
                "source_structure_url": "https://example.test/P1.cif",
                "sha256": "abc",
                "sequence_compatible": "true",
                "status": status,
                "retrieved_at": "volatile",
                "cache_path": raw_path,
            }
        ],
    )
    (path / "config.snapshot.yaml").write_text(
        yaml.safe_dump({"project": {"seed": 42}}), encoding="utf-8"
    )
    metadata = {
        "package_version": "0.1.0",
        "python_version": "3.11",
        "input_sha256": "input",
        "parameters_hash": "parameters",
        "sequence_backend": "local",
        "structure_backend": "hybrid",
        "synthetic_fixture_data": False,
        "query_count": 1,
        "sequence_hit_count": 1,
        "structure_hit_count": 1,
        "merged_row_count": 1,
        "created_at": raw_path,
    }
    (path / "run_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_compare_runs_ignores_only_expected_volatile_fields(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    _make_run(first, "/first/raw", "DOWNLOADED")
    _make_run(second, "/second/raw", "CACHED")

    report = compare_runs(first, second)

    assert report["equivalent"] is True
    assert all(item["equivalent"] for item in report["artifacts"].values())


def test_compare_runs_detects_biological_output_change(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    _make_run(first, "/first/raw")
    _make_run(second, "/second/raw")
    structure = second / "structure_results.tsv"
    structure.write_text(
        structure.read_text(encoding="utf-8").replace("1abc_A", "2xyz_B"),
        encoding="utf-8",
    )

    report = compare_runs(first, second)

    assert report["equivalent"] is False
    assert report["artifacts"]["structure_results.tsv"]["equivalent"] is False


def test_compare_runs_ignores_cross_query_block_order(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    _make_run(first, "/first/raw")
    _make_run(second, "/second/raw")
    rows = [
        {"query_id": "P1", "target_structure_id": "1abc_A", "raw_output_path": "raw"},
        {"query_id": "P1", "target_structure_id": "2abc_A", "raw_output_path": "raw"},
        {"query_id": "P2", "target_structure_id": "3abc_A", "raw_output_path": "raw"},
    ]
    _write_tsv(first / "structure_results.tsv", rows)
    _write_tsv(second / "structure_results.tsv", [rows[2], rows[0], rows[1]])

    report = compare_runs(first, second)

    assert report["artifacts"]["structure_results.tsv"]["equivalent"] is True


def test_compare_runs_preserves_within_query_rank_order(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    _make_run(first, "/first/raw")
    _make_run(second, "/second/raw")
    rows = [
        {"query_id": "P1", "target_structure_id": "1abc_A", "raw_output_path": "raw"},
        {"query_id": "P1", "target_structure_id": "2abc_A", "raw_output_path": "raw"},
    ]
    _write_tsv(first / "structure_results.tsv", rows)
    _write_tsv(second / "structure_results.tsv", list(reversed(rows)))

    report = compare_runs(first, second)

    assert report["artifacts"]["structure_results.tsv"]["equivalent"] is False
