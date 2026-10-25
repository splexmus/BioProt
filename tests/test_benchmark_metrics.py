from __future__ import annotations

from dualrag.benchmark.metrics import (
    bootstrap_mean_interval,
    cross_modal_metrics,
    ec_hierarchical_score,
    evaluate_function_predictions,
    go_lin_best_match_average,
    holm_adjust,
    paired_sign_flip_pvalue,
)


def gold() -> list[dict[str, str]]:
    return [
        {
            "accession": "Q1",
            "namespace": "EC",
            "identifier": "1.2.3.4",
            "admissible_for_primary": "true",
        },
        {
            "accession": "Q2",
            "namespace": "GO_MF",
            "identifier": "GO:0000001",
            "admissible_for_primary": "true",
        },
    ]


def prediction(
    baseline: str, query: str, namespace: str, identifier: str, rank: int
) -> dict[str, object]:
    return {
        "baseline": baseline,
        "query_accession": query,
        "namespace": namespace,
        "identifier": identifier,
        "rank": rank,
    }


def test_exact_function_metrics_and_paired_comparison() -> None:
    predictions = [
        prediction("B2_SEQUENCE_ONLY", "Q1", "EC", "EC:9.9.9.9", 1),
        prediction("B2_SEQUENCE_ONLY", "Q2", "GO_MF", "GO:0000001", 1),
        prediction("B4_DUAL_DETERMINISTIC", "Q1", "EC", "EC:1.2.3.4", 1),
        prediction("B4_DUAL_DETERMINISTIC", "Q2", "GO_MF", "GO:0000001", 1),
    ]

    per_query, aggregate, comparison = evaluate_function_predictions(
        predictions, gold(), ["Q1", "Q2"], bootstrap_replicates=100, seed=42
    )

    b2 = [row for row in aggregate if row["baseline"] == "B2_SEQUENCE_ONLY"]
    recall = next(row for row in b2 if row["metric"] == "function_recall_at_10")
    assert recall["estimate"] == 0.5
    assert len(per_query) == 4
    assert comparison["estimate"] == 0.5
    assert comparison["paired_query_count"] == 2


def test_cross_modal_categories_are_explicit() -> None:
    predictions = [
        prediction("B2_SEQUENCE_ONLY", "Q1", "EC", "EC:9.9.9.9", 1),
        prediction("B3_STRUCTURE_ONLY", "Q1", "EC", "EC:1.2.3.4", 1),
        prediction("B2_SEQUENCE_ONLY", "Q2", "GO_MF", "GO:0000001", 1),
    ]

    summary, details = cross_modal_metrics(predictions, gold(), ["Q1", "Q2"])

    assert summary["structure_rescue_rate"] == 0.5
    assert summary["sequence_rescue_rate"] == 0.5
    assert {row["category"] for row in details} == {"STRUCTURE_RESCUE", "SEQUENCE_RESCUE"}


def test_bootstrap_is_deterministic_and_ec_hierarchy_uses_leading_levels() -> None:
    assert bootstrap_mean_interval([0.0, 1.0, 1.0], 100, 42) == bootstrap_mean_interval(
        [0.0, 1.0, 1.0], 100, 42
    )
    assert ec_hierarchical_score("EC:1.2.9.9", "EC:1.2.3.4") == 0.5


def test_paired_randomization_and_holm_adjustment() -> None:
    assert paired_sign_flip_pvalue([0.0, 0.0]) == 1.0
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted == [0.03, 0.06, 0.06]


def test_go_lin_best_match_average_uses_most_informative_common_ancestor() -> None:
    parents = {"GO:A": {"GO:P"}, "GO:B": {"GO:P"}, "GO:P": {"GO:R"}}
    information_content = {"GO:A": 4.0, "GO:B": 3.0, "GO:P": 2.0, "GO:R": 0.0}

    assert go_lin_best_match_average(
        {"GO:A"}, {"GO:B"}, parents, information_content
    ) == 4 / 7
