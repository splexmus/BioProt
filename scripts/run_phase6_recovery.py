"""Development-only nested calibration experiment; never reads validation/test gold."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import yaml

from dualrag.calibration.development import _fit_method
from dualrag.calibration.pipeline import (
    _build_examples,
    _candidate_index,
    _evaluate,
    _gold_sets,
    _principal_b4,
)
from dualrag.calibration.scientific import (
    _bootstrap_intervals,
    _fit_multifeature_logistic,
    _group_wilson,
    _method_gate,
    _predict_multifeature,
)
from dualrag.io import file_sha256, read_tsv, stable_hash, write_json, write_tsv

# Fixed before reading outcomes; the default logistic is included at penalty 1.
CANDIDATES = ["platt_logistic", "isotonic_regression"] + [
    f"logistic:{penalty}:{int(namespace)}"
    for namespace in (False, True)
    for penalty in (0.01, 0.1, 1.0)
]


def fit(name, rows):
    if not name.startswith("logistic:"):
        return _fit_method(name, rows)
    _, penalty, namespace = name.split(":")
    model = _fit_multifeature_logistic(
        rows, l2_penalty=float(penalty), namespace_aware=bool(int(namespace))
    )
    return model, _predict_multifeature


def fold_map(accessions, clusters, count, salt):
    accessions = list(accessions)
    groups = sorted({clusters[a] for a in accessions}, key=lambda c: stable_hash([salt, c]))
    if len(groups) < count:
        raise ValueError("too few clusters for cross-validation")
    assignment = {cluster: index % count for index, cluster in enumerate(groups)}
    return {a: assignment[clusters[a]] for a in accessions}


def cross_validate(name, rows, folds):
    output = []
    for fold in sorted(set(folds.values())):
        train = [r for r in rows if folds[r["accession"]] != fold]
        held = [r for r in rows if folds[r["accession"]] == fold]
        if not train or not held:
            raise ValueError("empty training or evaluation fold")
        model, predict = fit(name, train)
        output.extend(dict(r, probability=predict(model, r), fold=fold) for r in held)
    return output


def selection_key(name, metrics):
    # Apply the contract's 0.01 log-loss tie tolerance before this key.
    complexity = 0 if name == "platt_logistic" else 1 if name == "isotonic_regression" else 2
    return metrics["brier_score"], metrics["expected_calibration_error"], complexity, name


def select(scores):
    best = min(m["log_loss"] for m in scores.values())
    tied = [n for n, m in scores.items() if m["log_loss"] <= best + 0.01]
    return min(tied, key=lambda n: selection_key(n, scores[n]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--contract", type=Path, default=Path("config/calibration-evaluation-v2.yaml")
    )
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    splits = read_tsv(args.dataset / "splits.tsv")
    if {r["split"] for r in splits} != {"development"}:
        raise ValueError("requires a development-only dataset")
    gold = read_tsv(args.dataset / "gold_labels.tsv")
    if {r["split"] for r in gold} != {"development"}:
        raise ValueError("requires development-only gold")
    args.output.mkdir(parents=True)
    write_json(
        args.output / "preregistration.json",
        {
            "candidates": CANDIDATES,
            "outer_folds": 5,
            "inner_folds": 3,
            "seed": 42,
            "contract_sha256": file_sha256(args.contract),
            "predictions_sha256": file_sha256(args.run / "predictions.tsv"),
            "candidates_sha256": file_sha256(args.run / "ablation_candidates.tsv"),
            "gold_sha256": file_sha256(args.dataset / "gold_labels.tsv"),
            "selection": "log_loss; within 0.01 use Brier, ECE, complexity",
        },
    )
    rows, exclusions = _build_examples(
        gold=_gold_sets(gold),
        splits={r["accession"]: r["split"] for r in splits},
        difficulties={
            r["accession"]: r["difficulty_stratum"]
            for r in read_tsv(args.dataset / "difficulty_strata.tsv")
        },
        predictions=_principal_b4(read_tsv(args.run / "predictions.tsv")),
        candidates=_candidate_index(read_tsv(args.run / "ablation_candidates.tsv")),
    )
    clusters = {
        r["accession"]: r["cluster_representative"]
        for r in read_tsv(args.dataset / "cluster_membership.tsv")
    }
    accessions = {r["accession"] for r in rows}
    outer = fold_map(accessions, clusters, 5, 42)
    write_tsv(
        args.output / "folds.tsv",
        [{"accession": a, "cluster": clusters[a], "fold": outer[a]} for a in sorted(accessions)],
        ["accession", "cluster", "fold"],
    )
    nested, selections = [], []
    for fold in range(5):
        train = [r for r in rows if outer[r["accession"]] != fold]
        held = [r for r in rows if outer[r["accession"]] == fold]
        inner = fold_map({r["accession"] for r in train}, clusters, 3, [42, fold])
        scores = {
            name: _evaluate(cross_validate(name, train, inner), probability_key="probability")
            for name in CANDIDATES
        }
        chosen = select(scores)
        model, predict = fit(chosen, train)
        nested.extend(
            dict(r, probability=predict(model, r), fold=fold, method=chosen) for r in held
        )
        selections.append({"outer_fold": fold, "selected": chosen, "inner_metrics": scores})
        print(f"outer fold {fold + 1}/5 selected {chosen}", flush=True)
    contract = yaml.safe_load(args.contract.read_text())
    raw = _evaluate(
        [dict(r, probability=float(r["top1_score"])) for r in rows], probability_key="probability"
    )
    metrics = _evaluate(nested, probability_key="probability")
    metrics["confidence_group_wilson"] = _group_wilson(nested)
    metrics["bootstrap_95_ci"] = _bootstrap_intervals(
        nested, probability_key="probability", replicates=2000, seed=42
    )
    gate = _method_gate(metrics, raw, contract)
    full_scores = {
        n: _evaluate(cross_validate(n, rows, outer), probability_key="probability")
        for n in CANDIDATES
    }
    selected = select(full_scores)
    model, _ = fit(selected, rows)
    coverage = len(rows) / len(_gold_sets(gold))
    sane = all(math.isfinite(r["probability"]) and 0 <= r["probability"] <= 1 for r in nested)
    sane = sane and len({r["probability"] for r in nested}) > 1
    ready = gate["passes_all_checks"] and coverage >= 0.8 and sane
    write_json(
        args.output / "selected_calibrator.json",
        {
            "status": "DEVELOPMENT_ONLY_NOT_VALIDATED",
            "method": selected,
            "parameters": model,
            "validation_used": False,
            "test_used": False,
        },
    )
    write_tsv(args.output / "nested_probabilities.tsv", nested, list(nested[0]))
    subgroups = {
        field: {
            value: _evaluate(
                [r for r in nested if r[field] == value], probability_key="probability"
            )
            for value in sorted({r[field] for r in nested})
        }
        for field in ("namespace", "difficulty_stratum")
    }
    report = {
        "status": "READY_FOR_COHORT_AUDIT" if ready else "STOP_DEVELOPMENT_NOT_READY",
        "development_examples": len(rows),
        "development_proteins": len(accessions),
        "coverage": coverage,
        "exclusions": exclusions,
        "raw": raw,
        "nested_metrics": metrics,
        "nested_gate": gate,
        "probability_sanity": sane,
        "candidate_oof_metrics": full_scores,
        "outer_selections": selections,
        "selected_for_development": selected,
        "subgroups": subgroups,
        "validation_used": False,
        "test_used": False,
    }
    write_json(args.output / "recovery_evaluation.json", report)
    print(report["status"], flush=True)


if __name__ == "__main__":
    main()
