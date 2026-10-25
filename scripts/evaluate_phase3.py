from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from dualrag.benchmark.metrics import (
    bootstrap_mean_interval,
    cross_modal_metrics,
    ec_hierarchical_score,
    evaluate_function_predictions,
    go_lin_best_match_average,
    holm_adjust,
    load_go_information_content,
    paired_sign_flip_pvalue,
    parse_go_is_a,
)
from dualrag.io import read_tsv, write_json, write_tsv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Phase 3 function predictions.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--go-obo", type=Path, required=True)
    parser.add_argument("--go-ic", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    queries = read_tsv(args.dataset / "queries.tsv")
    gold = read_tsv(args.dataset / "gold_labels.tsv")
    predictions = read_tsv(args.run / "predictions.tsv")
    accessions = [row["accession"] for row in queries]
    split = {row["accession"]: row["split"] for row in read_tsv(args.dataset / "splits.tsv")}
    test_accessions = [accession for accession in accessions if split[accession] == "test"]
    per_query_all, aggregate_all, _comparison_all = evaluate_function_predictions(
        predictions, gold, accessions, bootstrap_replicates=10_000, seed=42
    )
    per_query, aggregate, comparison = evaluate_function_predictions(
        predictions, gold, test_accessions, bootstrap_replicates=10_000, seed=42
    )
    difficulty = {
        row["accession"]: row["difficulty_stratum"]
        for row in read_tsv(args.dataset / "difficulty_strata.tsv")
    }
    taxonomy = {row["accession"]: row["taxonomy_superkingdom"] for row in queries}
    enzyme_accessions = {
        row["accession"]
        for row in gold
        if row["namespace"] == "EC" and row["admissible_for_primary"] == "true"
    }
    for row in per_query_all:
        accession = str(row["query_accession"])
        row["split"] = split[accession]
        row["difficulty_stratum"] = difficulty[accession]
        row["taxonomy_superkingdom"] = taxonomy[accession]
        row["enzyme_group"] = "enzyme" if accession in enzyme_accessions else "non_enzyme"
    for row in per_query:
        accession = str(row["query_accession"])
        row["split"] = split[accession]
        row["difficulty_stratum"] = difficulty[accession]
        row["taxonomy_superkingdom"] = taxonomy[accession]
        row["enzyme_group"] = "enzyme" if accession in enzyme_accessions else "non_enzyme"
    cross_summary, error_rows = cross_modal_metrics(predictions, gold, accessions)
    acquisition = {
        _accession(row["query_id"]): row["status"]
        for row in read_tsv(args.run / "raw" / "alphafold_acquisition.tsv")
    }
    for row in error_rows:
        accession = str(row["query_accession"])
        row["split"] = split[accession]
        row["difficulty_stratum"] = difficulty[accession]
        row["taxonomy_superkingdom"] = taxonomy[accession]
        row["alphafold_status"] = acquisition.get(accession, "NOT_ATTEMPTED")

    write_tsv(args.output / "per_query_metrics.tsv", per_query, list(per_query[0]))
    write_tsv(args.output / "aggregate_metrics.tsv", aggregate, list(aggregate[0]))
    write_tsv(
        args.output / "per_query_metrics_all.tsv", per_query_all, list(per_query_all[0])
    )
    write_tsv(
        args.output / "aggregate_metrics_all.tsv", aggregate_all, list(aggregate_all[0])
    )
    write_tsv(args.output / "biological_error_analysis.tsv", error_rows, list(error_rows[0]))
    write_json(args.output / "primary_comparison.json", comparison)
    write_json(args.output / "cross_modal_metrics.json", cross_summary)

    go_parents = parse_go_is_a(args.go_obo)
    go_ic = load_go_information_content(args.go_ic)
    secondary_test = _secondary_function_metrics(
        predictions, gold, test_accessions, go_parents, go_ic
    )
    secondary_all = _secondary_function_metrics(
        predictions, gold, accessions, go_parents, go_ic
    )
    write_tsv(
        args.output / "secondary_function_metrics.tsv",
        secondary_test,
        list(secondary_test[0]),
    )
    write_tsv(
        args.output / "secondary_function_metrics_all.tsv",
        secondary_all,
        list(secondary_all[0]),
    )

    domain_metrics = _domain_metrics(
        read_tsv(args.run / "ablation_candidates.tsv"),
        read_tsv(args.dataset / "domain_labels.tsv"),
        test_accessions,
    )
    write_tsv(args.output / "domain_metrics.tsv", domain_metrics, list(domain_metrics[0]))

    ablation_predictions = read_tsv(args.run / "ablation_predictions.tsv")
    by_ablation: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in ablation_predictions:
        by_ablation[row["ablation"]].append(row)
    ablation_rows: list[dict[str, object]] = []
    ablation_query_scores: dict[str, dict[str, float]] = {}
    for ablation, rows in sorted(by_ablation.items()):
        current_per_query, current_aggregate, _comparison = evaluate_function_predictions(
            rows, gold, test_accessions, bootstrap_replicates=10_000, seed=42
        )
        ablation_query_scores[ablation] = {
            str(row["query_accession"]): float(row["function_recall_at_10"])
            for row in current_per_query
            if row["baseline"] == "B4_DUAL_DETERMINISTIC"
        }
        for metric in current_aggregate:
            if metric["metric"] == "function_recall_at_10":
                ablation_rows.append({"ablation": ablation, **metric})
    write_tsv(args.output / "mapping_ablation_metrics.tsv", ablation_rows, list(ablation_rows[0]))
    ablation_contrasts = _ablation_contrasts(ablation_query_scores)
    write_tsv(
        args.output / "mapping_ablation_contrasts.tsv",
        ablation_contrasts,
        list(ablation_contrasts[0]),
    )

    subgroup_rows = _subgroup_metrics(per_query_all)
    write_tsv(args.output / "subgroup_metrics.tsv", subgroup_rows, list(subgroup_rows[0]))

    summary = {
        "primary_comparison": comparison,
        "cross_modal": cross_summary,
        "primary_split": "test",
        "primary_query_count": len(test_accessions),
        "files": sorted(path.name for path in args.output.iterdir() if path.is_file()),
    }
    write_json(args.output / "evaluation_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


def _subgroup_metrics(per_query: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group_type, field in (
        ("difficulty_stratum", "difficulty_stratum"),
        ("taxonomy_superkingdom", "taxonomy_superkingdom"),
        ("enzyme_group", "enzyme_group"),
    ):
        groups = sorted({str(row[field]) for row in per_query})
        baselines = sorted({str(row["baseline"]) for row in per_query})
        for group in groups:
            for baseline in baselines:
                values = [
                    float(row["function_recall_at_10"])
                    for row in per_query
                    if row[field] == group and row["baseline"] == baseline
                ]
                interval = bootstrap_mean_interval(values, 10_000, 42)
                rows.append(
                    {
                        "group_type": group_type,
                        "group": group,
                        "baseline": baseline,
                        "metric": "function_recall_at_10",
                        "estimate": interval.estimate,
                        "ci_lower": interval.lower,
                        "ci_upper": interval.upper,
                        "query_count": len(values),
                        "exploratory": True,
                    }
                )
    contrasts: list[dict[str, object]] = []
    for group_type, field in (
        ("difficulty_stratum", "difficulty_stratum"),
        ("taxonomy_superkingdom", "taxonomy_superkingdom"),
        ("enzyme_group", "enzyme_group"),
    ):
        groups = sorted({str(row[field]) for row in per_query})
        for group in groups:
            by_query: dict[str, dict[str, float]] = defaultdict(dict)
            for row in per_query:
                if row[field] == group:
                    by_query[str(row["query_accession"])][str(row["baseline"])] = float(
                        row["function_recall_at_10"]
                    )
            differences = [
                values["B4_DUAL_DETERMINISTIC"] - values["B2_SEQUENCE_ONLY"]
                for values in by_query.values()
                if "B4_DUAL_DETERMINISTIC" in values and "B2_SEQUENCE_ONLY" in values
            ]
            interval = bootstrap_mean_interval(differences, 10_000, 42)
            contrasts.append(
                {
                    "group_type": group_type,
                    "group": group,
                    "baseline": "",
                    "metric": "function_recall_at_10",
                    "estimate": "",
                    "ci_lower": interval.lower,
                    "ci_upper": interval.upper,
                    "query_count": len(differences),
                    "exploratory": True,
                    "contrast": "B4_DUAL_DETERMINISTIC-minus-B2_SEQUENCE_ONLY",
                    "effect": interval.estimate,
                    "p_value": paired_sign_flip_pvalue(differences),
                    "holm_adjusted_p": "",
                }
            )
    adjusted = holm_adjust([float(row["p_value"]) for row in contrasts])
    for row, value in zip(contrasts, adjusted, strict=True):
        row["holm_adjusted_p"] = value
    for row in rows:
        row.update({"contrast": "", "effect": "", "p_value": "", "holm_adjusted_p": ""})
    return [*rows, *contrasts]


def _ablation_contrasts(
    scores: dict[str, dict[str, float]],
) -> list[dict[str, object]]:
    reference = scores["NO_MAPPING"]
    rows: list[dict[str, object]] = []
    for ablation in sorted(set(scores) - {"NO_MAPPING"}):
        differences = [
            scores[ablation][accession] - reference[accession]
            for accession in sorted(reference)
        ]
        interval = bootstrap_mean_interval(differences, 10_000, 42)
        rows.append(
            {
                "ablation": ablation,
                "reference": "NO_MAPPING",
                "baseline": "B4_DUAL_DETERMINISTIC",
                "metric": "function_recall_at_10",
                "effect": interval.estimate,
                "ci_lower": interval.lower,
                "ci_upper": interval.upper,
                "paired_query_count": len(differences),
                "p_value": paired_sign_flip_pvalue(differences),
                "holm_adjusted_p": "",
            }
        )
    adjusted = holm_adjust([float(row["p_value"]) for row in rows])
    for row, value in zip(rows, adjusted, strict=True):
        row["holm_adjusted_p"] = value
    return rows


def _accession(identifier: str) -> str:
    parts = identifier.split("|")
    return parts[1] if len(parts) >= 3 else identifier


def _secondary_function_metrics(
    predictions: list[dict[str, str]],
    gold_rows: list[dict[str, str]],
    accessions: list[str],
    go_parents: dict[str, set[str]],
    go_ic: dict[str, float],
) -> list[dict[str, object]]:
    gold: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in gold_rows:
        if row["admissible_for_primary"] == "true":
            gold[row["accession"]][row["namespace"]].add(row["identifier"])
    predicted: dict[str, dict[str, dict[str, list[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for row in predictions:
        if int(row["rank"]) <= 10:
            predicted[row["baseline"]][row["query_accession"]][row["namespace"]].append(
                row["identifier"]
            )
    per_query: list[dict[str, object]] = []
    for baseline in sorted(predicted):
        for accession in accessions:
            ec_gold = gold[accession]["EC"]
            ec_predictions = predicted[baseline][accession]["EC"]
            ec_score = (
                sum(
                    max(
                        (ec_hierarchical_score(value, target) for value in ec_predictions),
                        default=0.0,
                    )
                    for target in ec_gold
                )
                / len(ec_gold)
                if ec_gold
                else None
            )
            go_gold = gold[accession]["GO_MF"]
            go_predictions = set(predicted[baseline][accession]["GO_MF"])
            go_score = (
                go_lin_best_match_average(go_predictions, go_gold, go_parents, go_ic)
                if go_gold
                else None
            )
            per_query.append(
                {
                    "baseline": baseline,
                    "query_accession": accession,
                    "hierarchical_ec_at_10": ec_score if ec_score is not None else "",
                    "go_lin_bma_at_10": go_score if go_score is not None else "",
                }
            )
    rows: list[dict[str, object]] = []
    for baseline in sorted(predicted):
        current = [row for row in per_query if row["baseline"] == baseline]
        for metric in ("hierarchical_ec_at_10", "go_lin_bma_at_10"):
            values = [float(row[metric]) for row in current if row[metric] != ""]
            interval = bootstrap_mean_interval(values, 10_000, 42)
            rows.append(
                {
                    "baseline": baseline,
                    "metric": metric,
                    "estimate": interval.estimate,
                    "ci_lower": interval.lower,
                    "ci_upper": interval.upper,
                    "query_count": len(values),
                    "missing_count": len(current) - len(values),
                }
            )
    return rows


def _domain_metrics(
    candidate_rows: list[dict[str, str]],
    gold_rows: list[dict[str, str]],
    accessions: list[str],
) -> list[dict[str, object]]:
    gold: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in gold_rows:
        gold[row["accession"]][row["namespace"]].add(row["identifier"])
    predicted: dict[str, dict[str, dict[str, list[tuple[float, str]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for row in candidate_rows:
        if row["ablation"] != "ALL_MAPPINGS" or row["candidate_kind"] not in {
            "INTERPRO",
            "PFAM",
        }:
            continue
        accession = _accession(row["query_id"])
        identifier = row["candidate_id"].split(":", 1)[1]
        predicted[row["baseline"]][accession][row["candidate_kind"]].append(
            (float(row["rerank_score"]), identifier)
        )
    rows: list[dict[str, object]] = []
    for baseline in sorted(predicted):
        for namespace in ("INTERPRO", "PFAM"):
            values: list[float] = []
            missing = 0
            for accession in accessions:
                truth = gold[accession][namespace]
                if not truth:
                    missing += 1
                    continue
                ordered = [
                    identifier
                    for _score, identifier in sorted(
                        predicted[baseline][accession][namespace],
                        key=lambda item: (-item[0], item[1]),
                    )[:10]
                ]
                values.append(len(set(ordered) & truth) / len(truth))
            interval = bootstrap_mean_interval(values, 10_000, 42)
            rows.append(
                {
                    "baseline": baseline,
                    "metric": f"{namespace.casefold()}_exact_recall_at_10",
                    "estimate": interval.estimate,
                    "ci_lower": interval.lower,
                    "ci_upper": interval.upper,
                    "query_count": len(values),
                    "missing_count": missing,
                }
            )
    return rows


if __name__ == "__main__":
    main()
