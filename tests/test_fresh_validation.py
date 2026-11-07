from __future__ import annotations

import csv
from pathlib import Path

import pytest

from dualrag.benchmark.fresh_validation import (
    _independent_candidate_accessions,
    build_fresh_validation_dataset,
    freeze_fresh_validation_inputs,
    seal_fresh_validation_labels,
)


def test_independent_candidates_exclude_old_clusters_and_deduplicate_new_clusters() -> None:
    clusters = {
        "excluded::OLD": ["excluded::OLD", "candidate::NEW1"],
        "candidate::NEW2": ["candidate::NEW2", "candidate::NEW3"],
        "candidate::NEW4": ["candidate::NEW4"],
    }

    assert _independent_candidate_accessions(clusters) == ["NEW2", "NEW4"]


def test_seal_fresh_validation_removes_pipeline_gold(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "queries.tsv").write_text("accession\nP1\n", encoding="utf-8")
    with (source / "gold_labels.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["accession", "identifier"])
        writer.writerow(["P1", "GO:1"])

    manifest = seal_fresh_validation_labels(
        source_dir=source,
        pipeline_dir=tmp_path / "pipeline",
        vault_dir=tmp_path / "vault",
    )

    assert not (tmp_path / "pipeline" / "gold_labels.tsv").exists()
    assert (tmp_path / "vault" / "validation_gold_labels.tsv").is_file()
    assert manifest["pipeline_contains_gold"] is False


def test_freeze_fresh_validation_inputs_hashes_artifacts_and_code(tmp_path: Path) -> None:
    artifact = tmp_path / "predictions.tsv"
    artifact.write_text("prediction\nP1\n", encoding="utf-8")
    code = tmp_path / "code"
    code.mkdir()
    (code / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    output = tmp_path / "freeze.json"

    manifest = freeze_fresh_validation_inputs(
        inputs={"ranked_predictions": artifact},
        code_roots=[code],
        output_path=output,
    )

    assert manifest["status"] == "PREDICTIONS_AND_MODELS_FROZEN_BEFORE_GOLD_REVEAL"
    assert manifest["validation_gold_accessed"] is False
    assert manifest["code_file_count"] == 1
    assert output.is_file()


def test_fresh_validation_builder_requires_an_exclusion_dataset(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one exclusion dataset"):
        build_fresh_validation_dataset(
            swissprot_dat=tmp_path / "missing.dat.gz",
            swissprot_fasta=tmp_path / "missing.fasta.gz",
            contract_path=tmp_path / "missing.yaml",
            output_dir=tmp_path / "output",
            source_release="test",
            source_sha256="missing",
            exclude_datasets=[],
        )
