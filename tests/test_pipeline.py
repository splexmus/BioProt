import csv
import json
from pathlib import Path

from dualrag.config import load_config
from dualrag.pipeline import run_pipeline

ROOT = Path(__file__).parents[1]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_fixture_pipeline_end_to_end(tmp_path: Path) -> None:
    output = tmp_path / "run"
    metadata = run_pipeline(
        load_config(ROOT / "config" / "config.yaml"),
        ROOT / "tests" / "fixtures" / "queries.fasta",
        output,
    )
    assert metadata["query_count"] == 5
    assert metadata["sequence_hit_count"] == 4
    assert metadata["structure_hit_count"] == 3
    assert (output / "raw" / "sequence_hits.tsv").read_bytes() == (
        ROOT / "tests" / "fixtures" / "sequence_hits.tsv"
    ).read_bytes()
    statuses = {row["cross_modal_status"] for row in read_rows(output / "merged_results.tsv")}
    assert statuses == {
        "CONSENSUS",
        "SEQUENCE_ONLY",
        "STRUCTURE_ONLY",
        "CONFLICT",
        "INSUFFICIENT_EVIDENCE",
    }
    sequence_rows = read_rows(output / "sequence_results.tsv")
    assert all(0 <= float(row["normalized_score"]) <= 1 for row in sequence_rows)
    assert all(row["normalization_version"] == "poc-sequence-v1" for row in sequence_rows)
    persisted = json.loads((output / "run_metadata.json").read_text(encoding="utf-8"))
    assert persisted["synthetic_fixture_data"] is True


def test_normalized_outputs_are_repeatable(tmp_path: Path) -> None:
    config = load_config(ROOT / "config" / "config.yaml")
    input_path = ROOT / "tests" / "fixtures" / "queries.fasta"
    first, second = tmp_path / "first", tmp_path / "second"
    run_pipeline(config, input_path, first)
    run_pipeline(config, input_path, second)
    for name in ("sequence_results.tsv", "structure_results.tsv", "merged_results.tsv"):
        first_text = (first / name).read_text(encoding="utf-8").replace(str(first), "RUN")
        second_text = (second / name).read_text(encoding="utf-8").replace(str(second), "RUN")
        assert first_text == second_text
