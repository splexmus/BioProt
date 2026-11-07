from __future__ import annotations

import csv
import json
from pathlib import Path

from dualrag.benchmark.sealing import BLINDED_COPY_FILES, seal_test_labels


def _write_tsv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_seal_removes_test_gold_from_pipeline_view(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for name in BLINDED_COPY_FILES:
        (source / name).write_text(f"fixture {name}\n", encoding="utf-8")
    _write_tsv(
        source / "splits.tsv",
        ["accession", "split"],
        [
            {"accession": "DEV", "split": "development"},
            {"accession": "VAL", "split": "validation"},
            {"accession": "TEST", "split": "test"},
        ],
    )
    _write_tsv(
        source / "gold_labels.tsv",
        ["accession", "split", "namespace", "identifier"],
        [
            {
                "accession": "DEV",
                "split": "development",
                "namespace": "EC",
                "identifier": "1.1.1.1",
            },
            {"accession": "VAL", "split": "validation", "namespace": "GO_MF", "identifier": "GO:1"},
            {"accession": "TEST", "split": "test", "namespace": "EC", "identifier": "2.2.2.2"},
        ],
    )

    blinded = tmp_path / "blinded"
    vault = tmp_path / "vault"
    manifest = seal_test_labels(source_dir=source, blinded_dir=blinded, vault_dir=vault)

    with (blinded / "gold_labels.tsv").open(encoding="utf-8", newline="") as handle:
        pipeline = list(csv.DictReader(handle, delimiter="\t"))
    with (vault / "test_gold_labels.tsv").open(encoding="utf-8", newline="") as handle:
        test = list(csv.DictReader(handle, delimiter="\t"))
    assert {row["split"] for row in pipeline} == {"development", "validation"}
    assert [row["accession"] for row in test] == ["TEST"]
    assert manifest["pipeline_contains_test_gold"] is False
    assert json.loads((blinded / "test_label_seal_manifest.json").read_text())["seal_type"] == (
        "PROCEDURAL_FILESYSTEM_SEPARATION"
    )
