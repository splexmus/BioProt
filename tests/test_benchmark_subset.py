from __future__ import annotations

import csv
from pathlib import Path

from dualrag.benchmark.subset import materialize_split_view


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_materialize_devval_view_excludes_test_queries_and_gold(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    queries = [
        {
            "accession": accession,
            "fasta_id": f"sp|{accession}|NAME",
            "canonical_sequence": sequence,
        }
        for accession, sequence in (("DEV", "AAAA"), ("VAL", "CCCC"), ("TEST", "DDDD"))
    ]
    _write(pipeline / "queries.tsv", list(queries[0]), queries)
    (pipeline / "queries.fasta").write_text("unused\n", encoding="utf-8")
    splits = [
        {"accession": "DEV", "split": "development"},
        {"accession": "VAL", "split": "validation"},
        {"accession": "TEST", "split": "test"},
    ]
    _write(pipeline / "splits.tsv", list(splits[0]), splits)
    for name in (
        "cluster_membership.tsv",
        "difficulty_strata.tsv",
        "domain_labels.tsv",
        "exposed_queries.tsv",
    ):
        _write(pipeline / name, ["accession", "value"], [
            {"accession": row["accession"], "value": name} for row in splits
        ])
    _write(
        pipeline / "gold_labels.tsv",
        ["accession", "split", "namespace", "identifier"],
        [
            {"accession": "DEV", "split": "development", "namespace": "EC", "identifier": "1"},
            {"accession": "VAL", "split": "validation", "namespace": "EC", "identifier": "2"},
        ],
    )
    _write(
        pipeline / "prohibited_targets.tsv",
        ["query_accession", "target_accession"],
        [
            {"query_accession": "DEV", "target_accession": "X"},
            {"query_accession": "TEST", "target_accession": "Y"},
        ],
    )
    alignments = tmp_path / "alignments.tsv"
    alignments.write_text(
        "sp|DEV|NAME\tsp|X|X\t1\t1\t1\t0\t10\n"
        "sp|TEST|NAME\tsp|Y|Y\t1\t1\t1\t0\t10\n",
        encoding="utf-8",
    )

    manifest = materialize_split_view(
        pipeline_dir=pipeline,
        alignments_path=alignments,
        output_dir=tmp_path / "devval",
        include_splits={"development", "validation"},
    )

    assert manifest["query_count"] == 2
    assert manifest["contains_test_queries"] is False
    assert manifest["contains_test_gold"] is False
    assert "TEST" not in (tmp_path / "devval" / "queries.fasta").read_text()
    assert "TEST" not in (tmp_path / "devval" / "reference_alignments.tsv").read_text()
