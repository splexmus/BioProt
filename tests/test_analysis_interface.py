from __future__ import annotations

import json
from pathlib import Path

import pytest

from dualrag.analysis import AnalysisError, run_analysis
from dualrag.config import load_config

ROOT = Path(__file__).parents[1]


class FakeResponse:
    status_code = 200
    text = ">sp|P69905|HBA_HUMAN Hemoglobin subunit alpha\nMVLSPADK\n"


class FakeSession:
    def get(self, url: str, *, timeout: float) -> FakeResponse:
        assert url.endswith("/P69905.fasta")
        assert timeout == 30
        return FakeResponse()


def test_analyze_fasta_runs_existing_pipeline_and_writes_summary(tmp_path: Path) -> None:
    output = tmp_path / "analysis"
    result = run_analysis(
        config=load_config(ROOT / "config/config.yaml"),
        output_dir=output,
        fasta_path=ROOT / "tests/fixtures/queries.fasta",
    )

    assert result["status"] == "COMPLETE"
    assert result["query_count"] == 5
    assert (output / "biological/function_candidates.tsv").is_file()
    assert "confidence NOT_CALIBRATED" in (output / "summary.md").read_text()
    manifest = json.loads((output / "input/input_manifest.json").read_text())
    assert manifest["source_type"] == "FASTA_FILE"


def test_uniprot_input_is_validated_before_pipeline(tmp_path: Path) -> None:
    config = load_config(ROOT / "config/config.yaml")
    result = run_analysis(
        config=config,
        output_dir=tmp_path / "analysis",
        uniprot_accession="P69905",
        session=FakeSession(),
    )
    manifest = json.loads(
        (tmp_path / "analysis/input/input_manifest.json").read_text(encoding="utf-8")
    )
    assert result["status"] == "COMPLETE"
    assert manifest["requested_accession"] == "P69905"
    assert manifest["queries"][0]["resolved_accession"] == "P69905"
    assert json.loads((tmp_path / "analysis/status.json").read_text())["status"] == "COMPLETE"


def test_analyze_requires_exactly_one_input_and_refuses_overwrite(tmp_path: Path) -> None:
    config = load_config(ROOT / "config/config.yaml")
    with pytest.raises(AnalysisError, match="exactly one"):
        run_analysis(config=config, output_dir=tmp_path / "none")
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(AnalysisError, match="already exists"):
        run_analysis(
            config=config,
            output_dir=output,
            fasta_path=ROOT / "tests/fixtures/queries.fasta",
        )
    with pytest.raises(AnalysisError, match="exactly one"):
        run_analysis(
            config=config,
            output_dir=tmp_path / "both",
            fasta_path=ROOT / "tests/fixtures/queries.fasta",
            uniprot_accession="P69905",
        )
