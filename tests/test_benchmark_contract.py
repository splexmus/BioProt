from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
CONTRACT_PATH = ROOT / "config" / "benchmark-contract-v1.yaml"


def load_contract() -> dict[str, object]:
    value = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_primary_endpoint_cannot_be_satisfied_by_domain_only_agreement() -> None:
    contract = load_contract()
    primary = contract["primary_endpoint"]
    correctness = contract["correctness"]

    assert primary["name"] == "macro_function_recall_at_10"
    assert primary["namespaces"] == ["EC", "GO_MF"]
    assert correctness["interpro"]["counts_as_exact_function_correctness"] is False
    assert correctness["pfam"]["counts_as_exact_function_correctness"] is False
    assert correctness["labels"]["automated_scoring"] is False


def test_contract_freezes_gold_and_leakage_rules() -> None:
    contract = load_contract()
    gold = contract["gold_standard"]
    leakage = contract["leakage_control"]
    exclusion = leakage["retrieval_target_exclusion"]

    assert gold["tier_a_primary"]["protein_existence"] == "evidence_at_protein_level"
    assert gold["inclusion"]["require_at_least_one_tier_a_label_in"] == ["EC", "GO_MF"]
    assert exclusion["exact_accession"] is True
    assert exclusion["exact_sequence_sha256"] is True
    assert exclusion["close_homolog_identity_at_least"] == 0.90
    assert exclusion["close_homolog_bidirectional_coverage_at_least"] == 0.80
    assert leakage["annotation_leakage"]["smoke_set_derived_synonyms_allowed_in_primary"] is False


def test_difficulty_bins_are_contiguous() -> None:
    bins = load_contract()["difficulty_strata"]["bins"]
    numeric = [item for item in bins if not item.get("no_allowed_hit")]

    assert numeric[-1]["lower_inclusive"] == 0.0
    assert numeric[-1]["upper_inclusive"] == 0.20
    assert numeric[0]["upper_inclusive"] == 1.0
    assert [item["name"] for item in bins] == [
        "GT_70",
        "FROM_50_TO_70",
        "FROM_30_TO_50",
        "FROM_20_TO_30",
        "LT_OR_EQ_20",
        "NO_ALLOWED_HIT",
    ]


def test_contract_requires_label_and_target_decision_provenance() -> None:
    requirements = load_contract()["manifest_requirements"]

    assert {
        "evidence_tier",
        "evidence_code",
        "supporting_reference",
        "admissible_for_primary",
        "decision_reason",
    } <= set(requirements["gold_label"])
    assert {
        "exclusion_reason",
        "sequence_identity",
        "query_coverage",
        "target_coverage",
        "resolution_source",
    } <= set(requirements["prohibited_target"])
