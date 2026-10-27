from __future__ import annotations

import json
from pathlib import Path

from dualrag.calibration import run_confidence_calibration
from dualrag.io import read_tsv, write_tsv


def test_calibration_excludes_test_and_writes_probability_outputs(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions.tsv"
    candidates = tmp_path / "candidates.tsv"
    gold = tmp_path / "gold.tsv"
    splits = tmp_path / "splits.tsv"
    difficulty = tmp_path / "difficulty.tsv"
    contract = tmp_path / "contract.yaml"
    output = tmp_path / "output"
    accessions = ["D1", "D2", "D3", "D4", "V1", "V2", "T1"]
    split_values = {
        "D1": "development",
        "D2": "development",
        "D3": "development",
        "D4": "development",
        "V1": "validation",
        "V2": "validation",
        "T1": "test",
    }
    prediction_rows = []
    candidate_rows = []
    gold_rows = []
    for index, accession in enumerate(accessions):
        predicted = "GO:0000001" if index % 2 == 0 else "GO:0000002"
        correct = index in {0, 1, 4, 6}
        expected = predicted if correct else "GO:0000003"
        score = 0.8 if correct else 0.3
        prediction_rows.append(
            {
                "baseline": "B4_DUAL_DETERMINISTIC",
                "ablation": "ALL_MAPPINGS",
                "query_accession": accession,
                "namespace": "GO_MF",
                "identifier": predicted,
                "rank": 1,
                "score": score,
                "modalities": "sequence;structure",
                "source_ids": "X",
                "mapping_provenance": "",
            }
        )
        candidate_rows.append(
            {
                "baseline": "B4_DUAL_DETERMINISTIC",
                "ablation": "ALL_MAPPINGS",
                "query_id": f"sp|{accession}|TEST",
                "candidate_id": predicted,
                "sequence_score": 0.8,
                "structure_score": 0.7,
                "structure_reliability_score": 0.7,
                "agreement_reliability_score": 1.0,
                "modality_support": 1.0,
                "hit_support": 1.0,
                "evidence_quality_score": 1.0,
                "sequence_evidence_count": 2,
                "structure_evidence_count": 2,
                "cross_modal_status": "CONSENSUS",
            }
        )
        gold_rows.append(
            {
                "accession": accession,
                "namespace": "GO_MF",
                "identifier": expected,
                "admissible_for_primary": "true",
            }
        )
    write_tsv(predictions, prediction_rows, list(prediction_rows[0]))
    write_tsv(candidates, candidate_rows, list(candidate_rows[0]))
    write_tsv(gold, gold_rows, list(gold_rows[0]))
    write_tsv(
        splits,
        [{"accession": accession, "split": split_values[accession]} for accession in accessions],
        ["accession", "split"],
    )
    write_tsv(
        difficulty,
        [{"accession": accession, "difficulty_stratum": "GT_70"} for accession in accessions],
        ["accession", "difficulty_stratum"],
    )
    contract.write_text("contract_id: test\n", encoding="utf-8")

    result = run_confidence_calibration(
        predictions_path=predictions,
        candidates_path=candidates,
        gold_labels_path=gold,
        splits_path=splits,
        difficulty_path=difficulty,
        contract_path=contract,
        output_dir=output,
    )

    assert result["manifest"]["development_example_count"] == 4
    assert result["manifest"]["validation_example_count"] == 2
    assert result["model"]["test_split_used"] is False
    examples = read_tsv(output / "calibration_examples.tsv")
    assert {row["split"] for row in examples} == {"development", "validation"}
    assert all(0 <= float(row["calibrated_probability"]) <= 1 for row in examples)
    exclusions = read_tsv(output / "calibration_exclusions.tsv")
    assert exclusions == [
        {
            "accession": "T1",
            "split": "test",
            "namespace": "GO_MF",
            "reason": "EXPOSED_TEST_SPLIT_PROHIBITED",
        }
    ]
    assert json.loads((output / "calibration_model.json").read_text())["status"] == (
        "DEVELOPMENT_PILOT_NOT_FOR_PRODUCTION"
    )
    assert (output / "reliability_diagram.svg").is_file()
