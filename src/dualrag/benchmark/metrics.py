from __future__ import annotations

import csv
import math
import random
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from statistics import mean

PRIMARY_NAMESPACES = ("EC", "GO_MF")


@dataclass(frozen=True)
class Interval:
    estimate: float
    lower: float
    upper: float


def canonical_function_id(namespace: str, identifier: str) -> str:
    value = identifier.strip()
    if namespace == "EC":
        return value if value.startswith("EC:") else f"EC:{value}"
    if namespace == "GO_MF":
        return value if value.startswith("GO:") else f"GO:{value}"
    return value


def evaluate_function_predictions(
    predictions: Iterable[dict[str, object]],
    gold_rows: Iterable[dict[str, str]],
    query_accessions: Iterable[str],
    *,
    ks: tuple[int, ...] = (1, 5, 10),
    bootstrap_replicates: int = 10_000,
    seed: int = 42,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """Evaluate exact controlled function IDs with query-level macro aggregation."""
    accessions = sorted(set(query_accessions))
    gold: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in gold_rows:
        if row.get("admissible_for_primary", "").casefold() != "true":
            continue
        namespace = row["namespace"]
        if namespace in PRIMARY_NAMESPACES:
            gold[row["accession"]][namespace].add(
                canonical_function_id(namespace, row["identifier"])
            )

    ranked: dict[str, dict[str, dict[str, list[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    scored_rows = sorted(
        predictions,
        key=lambda row: (
            str(row["baseline"]),
            str(row["query_accession"]),
            str(row["namespace"]),
            int(row["rank"]),
            str(row["identifier"]),
        ),
    )
    for row in scored_rows:
        baseline = str(row["baseline"])
        accession = str(row["query_accession"])
        namespace = str(row["namespace"])
        if namespace not in PRIMARY_NAMESPACES:
            continue
        identifier = canonical_function_id(namespace, str(row["identifier"]))
        values = ranked[baseline][accession][namespace]
        if identifier not in values:
            values.append(identifier)

    baselines = sorted(ranked)
    per_query: list[dict[str, object]] = []
    for baseline in baselines:
        for accession in accessions:
            namespace_scores: dict[int, list[float]] = defaultdict(list)
            namespace_precisions: dict[int, list[float]] = defaultdict(list)
            reciprocal_ranks: list[float] = []
            ndcgs: list[float] = []
            available = sorted(gold[accession])
            for namespace in available:
                truth = gold[accession][namespace]
                values = ranked[baseline][accession][namespace]
                first_relevant = next(
                    (index for index, value in enumerate(values, start=1) if value in truth),
                    None,
                )
                reciprocal_ranks.append(1.0 / first_relevant if first_relevant else 0.0)
                ndcgs.append(_ndcg(values[: max(ks)], truth))
                for k in ks:
                    predicted = values[:k]
                    correct = len(set(predicted) & truth)
                    namespace_scores[k].append(correct / len(truth))
                    namespace_precisions[k].append(correct / len(predicted) if predicted else 0.0)
            row: dict[str, object] = {
                "baseline": baseline,
                "query_accession": accession,
                "namespace_count": len(available),
                "candidate_coverage": float(
                    any(ranked[baseline][accession][namespace] for namespace in available)
                ),
                "mrr": mean(reciprocal_ranks) if reciprocal_ranks else 0.0,
                "ndcg_at_10": mean(ndcgs) if ndcgs else 0.0,
            }
            for k in ks:
                row[f"function_recall_at_{k}"] = (
                    mean(namespace_scores[k]) if namespace_scores[k] else 0.0
                )
                row[f"precision_at_{k}"] = (
                    mean(namespace_precisions[k]) if namespace_precisions[k] else 0.0
                )
            per_query.append(row)

    aggregate: list[dict[str, object]] = []
    metrics = [
        *(f"function_recall_at_{k}" for k in ks),
        *(f"precision_at_{k}" for k in ks),
        "mrr",
        "ndcg_at_10",
        "candidate_coverage",
    ]
    for baseline in baselines:
        rows = [row for row in per_query if row["baseline"] == baseline]
        for metric in metrics:
            values = [float(row[metric]) for row in rows]
            interval = bootstrap_mean_interval(values, bootstrap_replicates, seed)
            aggregate.append(
                {
                    "baseline": baseline,
                    "metric": metric,
                    "estimate": interval.estimate,
                    "ci_lower": interval.lower,
                    "ci_upper": interval.upper,
                    "numerator": sum(values),
                    "denominator": len(values),
                    "query_count": len(values),
                    "missing_count": len(accessions) - len(values),
                }
            )

    comparison = paired_primary_comparison(
        per_query,
        first_baseline="B4_DUAL_DETERMINISTIC",
        second_baseline="B2_SEQUENCE_ONLY",
        metric="function_recall_at_10",
        replicates=bootstrap_replicates,
        seed=seed,
    )
    return per_query, aggregate, comparison


def paired_primary_comparison(
    per_query: Iterable[dict[str, object]],
    *,
    first_baseline: str,
    second_baseline: str,
    metric: str,
    replicates: int,
    seed: int,
) -> dict[str, object]:
    by_query: dict[str, dict[str, float]] = defaultdict(dict)
    for row in per_query:
        by_query[str(row["query_accession"])][str(row["baseline"])] = float(row[metric])
    differences = [
        values[first_baseline] - values[second_baseline]
        for values in by_query.values()
        if first_baseline in values and second_baseline in values
    ]
    interval = bootstrap_mean_interval(differences, replicates, seed)
    if interval.lower > 0:
        conclusion = "DUAL_IMPROVES_OVER_SEQUENCE"
    elif interval.upper < 0:
        conclusion = "DUAL_WORSE_THAN_SEQUENCE"
    else:
        conclusion = "NO_MEASURABLE_OVERALL_BENEFIT"
    return {
        "contrast": f"{first_baseline}-minus-{second_baseline}",
        "metric": metric,
        "estimate": interval.estimate,
        "ci_lower": interval.lower,
        "ci_upper": interval.upper,
        "paired_query_count": len(differences),
        "bootstrap_replicates": replicates,
        "seed": seed,
        "conclusion": conclusion,
    }


def bootstrap_mean_interval(values: list[float], replicates: int, seed: int) -> Interval:
    if not values:
        return Interval(0.0, 0.0, 0.0)
    estimate = mean(values)
    if len(values) == 1 or replicates <= 0:
        return Interval(estimate, estimate, estimate)
    rng = random.Random(seed)
    sampled = sorted(
        mean(rng.choices(values, k=len(values)))
        for _ in range(replicates)
    )
    lower = _percentile(sampled, 0.025)
    upper = _percentile(sampled, 0.975)
    return Interval(estimate, lower, upper)


def cross_modal_metrics(
    predictions: Iterable[dict[str, object]],
    gold_rows: Iterable[dict[str, str]],
    query_accessions: Iterable[str],
    *,
    k: int = 10,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    truth: dict[str, set[str]] = defaultdict(set)
    for row in gold_rows:
        if row.get("admissible_for_primary", "").casefold() == "true":
            truth[row["accession"]].add(
                canonical_function_id(row["namespace"], row["identifier"])
            )
    predicted: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in predictions:
        if int(row["rank"]) > k or str(row["namespace"]) not in PRIMARY_NAMESPACES:
            continue
        predicted[str(row["baseline"])][str(row["query_accession"])].add(
            canonical_function_id(str(row["namespace"]), str(row["identifier"]))
        )

    details: list[dict[str, object]] = []
    counts = defaultdict(int)
    accessions = sorted(set(query_accessions))
    for accession in accessions:
        seq = predicted["B2_SEQUENCE_ONLY"][accession]
        struct = predicted["B3_STRUCTURE_ONLY"][accession]
        gold = truth[accession]
        seq_ok = bool(seq & gold)
        struct_ok = bool(struct & gold)
        shared = seq & struct
        if struct_ok and not seq_ok:
            category = "STRUCTURE_RESCUE"
            counts["structure_rescue"] += 1
        elif seq_ok and not struct_ok:
            category = "SEQUENCE_RESCUE"
            counts["sequence_rescue"] += 1
        elif seq_ok and struct_ok:
            category = "BOTH_CORRECT"
            counts["both_correct"] += 1
        elif seq and struct and shared and not (shared & gold):
            category = "INCORRECT_CONSENSUS"
            counts["incorrect_consensus"] += 1
        elif seq and struct and not shared:
            category = "CONFLICT"
            counts["conflict"] += 1
        else:
            category = "BOTH_FAIL_OR_MISSING"
            counts["both_fail_or_missing"] += 1
        counts["union_correct"] += seq_ok or struct_ok
        counts["intersection_prediction"] += bool(shared)
        details.append(
            {
                "query_accession": accession,
                "category": category,
                "sequence_correct": seq_ok,
                "structure_correct": struct_ok,
                "sequence_prediction_count": len(seq),
                "structure_prediction_count": len(struct),
                "shared_prediction_count": len(shared),
                "gold_count": len(gold),
            }
        )
    denominator = len(accessions)
    summary: dict[str, object] = {
        "query_count": denominator,
        "union_recall": counts["union_correct"] / denominator if denominator else 0.0,
        "intersection_coverage": (
            counts["intersection_prediction"] / denominator if denominator else 0.0
        ),
        "structure_rescue_rate": (
            counts["structure_rescue"] / denominator if denominator else 0.0
        ),
        "sequence_rescue_rate": (
            counts["sequence_rescue"] / denominator if denominator else 0.0
        ),
        "conflict_rate": counts["conflict"] / denominator if denominator else 0.0,
        "incorrect_consensus_rate": (
            counts["incorrect_consensus"] / denominator if denominator else 0.0
        ),
        "counts": dict(sorted(counts.items())),
    }
    return summary, details


def ec_hierarchical_score(predicted: str, gold: str) -> float:
    predicted_parts = predicted.removeprefix("EC:").split(".")
    gold_parts = gold.removeprefix("EC:").split(".")
    common = 0
    for predicted_part, gold_part in zip(predicted_parts, gold_parts, strict=False):
        if predicted_part != gold_part:
            break
        common += 1
    return common / 4


def parse_go_is_a(path: Path) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = defaultdict(set)
    current = ""
    obsolete = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "[Term]":
            current = ""
            obsolete = False
        elif line.startswith("["):
            current = ""
        elif line.startswith("id: GO:"):
            current = line.split("id: ", 1)[1]
        elif line == "is_obsolete: true":
            obsolete = True
        elif current and line.startswith("is_a: GO:") and not obsolete:
            parents[current].add(line.split()[1])
    return dict(parents)


def go_ancestors(term: str, parents: dict[str, set[str]]) -> set[str]:
    result = {term}
    pending = [term]
    while pending:
        current = pending.pop()
        for parent in parents.get(current, set()):
            if parent not in result:
                result.add(parent)
                pending.append(parent)
    return result


def load_go_information_content(path: Path) -> dict[str, float]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            row["go_id"]: float(row["information_content"])
            for row in csv.DictReader(handle, delimiter="\t")
        }


def go_lin_similarity(
    first: str,
    second: str,
    parents: dict[str, set[str]],
    information_content: dict[str, float],
) -> float:
    first_ic = information_content.get(first)
    second_ic = information_content.get(second)
    if first_ic is None or second_ic is None or first_ic + second_ic == 0:
        return 1.0 if first == second else 0.0
    common = go_ancestors(first, parents) & go_ancestors(second, parents)
    mica = max((information_content.get(term, 0.0) for term in common), default=0.0)
    return 2 * mica / (first_ic + second_ic)


def go_lin_best_match_average(
    predicted: set[str],
    gold: set[str],
    parents: dict[str, set[str]],
    information_content: dict[str, float],
) -> float:
    if not predicted or not gold:
        return 0.0
    forward = mean(
        max(go_lin_similarity(item, target, parents, information_content) for target in gold)
        for item in predicted
    )
    reverse = mean(
        max(go_lin_similarity(item, target, parents, information_content) for item in predicted)
        for target in gold
    )
    return (forward + reverse) / 2


def paired_sign_flip_pvalue(
    differences: list[float], *, permutations: int = 10_000, seed: int = 42
) -> float:
    """Two-sided paired randomization test, exact for at most 20 non-zero pairs."""
    values = [value for value in differences if value != 0]
    if not values:
        return 1.0
    observed = abs(mean(values))
    if len(values) <= 20:
        statistics = [
            abs(mean([value * sign for value, sign in zip(values, signs, strict=True)]))
            for signs in product((-1, 1), repeat=len(values))
        ]
    else:
        rng = random.Random(seed)
        statistics = [
            abs(mean(value * rng.choice((-1, 1)) for value in values))
            for _ in range(permutations)
        ]
    extreme = sum(statistic >= observed - 1e-12 for statistic in statistics)
    return (extreme + 1) / (len(statistics) + 1)


def holm_adjust(pvalues: list[float]) -> list[float]:
    """Holm family-wise adjustment preserving the original order."""
    total = len(pvalues)
    ordered = sorted(enumerate(pvalues), key=lambda item: item[1])
    adjusted = [1.0] * total
    running = 0.0
    for rank, (index, value) in enumerate(ordered):
        current = min(1.0, (total - rank) * value)
        running = max(running, current)
        adjusted[index] = running
    return adjusted


def _ndcg(predicted: list[str], truth: set[str]) -> float:
    if not predicted or not truth:
        return 0.0
    dcg = sum(
        (1.0 / math.log2(index + 1)) if value in truth else 0.0
        for index, value in enumerate(predicted, start=1)
    )
    ideal_hits = min(len(truth), len(predicted))
    ideal = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / ideal if ideal else 0.0


def _percentile(values: list[float], probability: float) -> float:
    if len(values) == 1:
        return values[0]
    position = probability * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction
