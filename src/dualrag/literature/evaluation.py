from __future__ import annotations

import csv
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from dualrag.io import file_sha256, write_json, write_tsv
from dualrag.literature.io import read_jsonl
from dualrag.literature.schemas import LiteratureCandidate, LiteratureHit, LiteratureQuery

EVALUATOR_VERSION = "literature-evaluation-v1"
LABEL_FIELDS = {
    "query_id",
    "chunk_id",
    "relevant",
    "citation_supported",
    "entity_correct",
    "organism_correct",
    "primary_experiment",
    "contradiction",
    "annotator",
    "notes",
}
CANDIDATE_REVIEW_FIELDS = [
    "annotator",
    "query_id",
    "chunk_id",
    "relevant",
    "citation_supported",
    "contradiction",
    "entity_correct",
    "organism_correct",
    "primary_experiment",
    "notes",
    "pmid",
    "title",
    "section_type",
    "text",
    "source_url",
    "lexical_rank",
    "vector_rank",
    "hybrid_rank",
    "reranker_rank",
]


def evaluate_literature(
    *,
    hits_path: Path,
    labels_path: Path,
    output_dir: Path,
    minimum_queries: int = 20,
    candidates_path: Path | None = None,
    queries_path: Path | None = None,
    acceptance_path: Path | None = None,
) -> dict[str, Any]:
    hits = read_jsonl(hits_path, LiteratureHit)
    labels = _read_labels(labels_path)
    if candidates_path is not None:
        return _evaluate_candidate_pool(
            hits=hits,
            labels=labels,
            hits_path=hits_path,
            labels_path=labels_path,
            candidates_path=candidates_path,
            queries_path=queries_path,
            acceptance_path=acceptance_path,
            output_dir=output_dir,
            minimum_queries=minimum_queries,
        )
    hit_by_query: dict[str, list[LiteratureHit]] = defaultdict(list)
    for hit in hits:
        hit_by_query[hit.query_id].append(hit)
    label_by_pair = {(row["query_id"], row["chunk_id"]): row for row in labels}
    relevant_by_query: dict[str, set[str]] = defaultdict(set)
    contradiction_by_query: dict[str, set[str]] = defaultdict(set)
    for row in labels:
        if row["relevant"]:
            relevant_by_query[row["query_id"]].add(row["chunk_id"])
        if row["contradiction"]:
            contradiction_by_query[row["query_id"]].add(row["chunk_id"])
    per_query: list[dict[str, Any]] = []
    for query_id in sorted(set(relevant_by_query) | set(hit_by_query)):
        ranked = sorted(hit_by_query.get(query_id, []), key=lambda value: value.rank)
        relevant = relevant_by_query.get(query_id, set())
        row: dict[str, Any] = {
            "query_id": query_id,
            "relevant_count": len(relevant),
            "retrieved_count": len(ranked),
            "mrr": _reciprocal_rank(ranked, relevant),
            "ndcg_at_10": _ndcg(ranked[:10], relevant),
        }
        for k in (1, 5, 10):
            selected = ranked[:k]
            matches = sum(hit.chunk.chunk_id in relevant for hit in selected)
            row[f"precision_at_{k}"] = matches / len(selected) if selected else 0.0
            row[f"recall_at_{k}"] = matches / len(relevant) if relevant else None
        contradictions = contradiction_by_query.get(query_id, set())
        row["contradiction_recall_at_10"] = (
            sum(hit.chunk.chunk_id in contradictions for hit in ranked[:10]) / len(contradictions)
            if contradictions
            else None
        )
        per_query.append(row)
    assessed = [
        (hit, label_by_pair[(hit.query_id, hit.chunk.chunk_id)])
        for hit in hits
        if (hit.query_id, hit.chunk.chunk_id) in label_by_pair
    ]
    metrics = {
        key: _mean([row[key] for row in per_query if row.get(key) is not None])
        for key in (
            "precision_at_1",
            "precision_at_5",
            "precision_at_10",
            "recall_at_1",
            "recall_at_5",
            "recall_at_10",
            "mrr",
            "ndcg_at_10",
            "contradiction_recall_at_10",
        )
    }
    metrics.update(
        {
            "citation_precision": _rate(assessed, "citation_supported"),
            "citation_recall": _citation_recall(hits, labels),
            "entity_correctness": _rate(assessed, "entity_correct"),
            "organism_correctness": _rate(assessed, "organism_correct"),
            "primary_experiment_retrieval_rate": _rate(assessed, "primary_experiment"),
        }
    )
    labeled_queries = len({row["query_id"] for row in labels})
    status = "EVALUATED" if labeled_queries >= minimum_queries else "INSUFFICIENT_MANUAL_LABELS"
    result = {
        "schema_version": 1,
        "evaluator_version": EVALUATOR_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "status": status,
        "minimum_queries": minimum_queries,
        "labeled_query_count": labeled_queries,
        "label_count": len(labels),
        "metrics": metrics,
        "per_query": per_query,
        "inputs": {"hits": file_sha256(hits_path), "labels": file_sha256(labels_path)},
        "interpretation": (
            "Fixture or insufficient-label results validate mechanics only; they do not establish "
            "scientific retrieval quality. Acceptance thresholds must be frozen before "
            "scoring the final set."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "literature_evaluation.json", result)
    return result


def _evaluate_candidate_pool(
    *,
    hits: list[LiteratureHit],
    labels: list[dict[str, Any]],
    hits_path: Path,
    labels_path: Path,
    candidates_path: Path,
    queries_path: Path | None,
    acceptance_path: Path | None,
    output_dir: Path,
    minimum_queries: int,
) -> dict[str, Any]:
    candidates = read_jsonl(candidates_path, LiteratureCandidate)
    queries = read_jsonl(queries_path, LiteratureQuery) if queries_path else []
    label_by_pair = {(row["query_id"], row["chunk_id"]): row for row in labels}
    candidate_pairs = {(row.query_id, row.chunk.chunk_id) for row in candidates}
    label_pairs = set(label_by_pair)
    missing_labels = sorted(candidate_pairs - label_pairs)
    extra_labels = sorted(label_pairs - candidate_pairs)
    pool_complete = not missing_labels and not extra_labels

    query_ids = [query.query_id for query in queries] or sorted(
        {candidate.query_id for candidate in candidates}
    )
    by_query: dict[str, list[LiteratureCandidate]] = defaultdict(list)
    for candidate in candidates:
        by_query[candidate.query_id].append(candidate)
    method_fields = {
        "lexical": "lexical_rank",
        "vector": "vector_rank",
        "hybrid": "hybrid_rank",
        "reranked": "reranker_rank",
    }
    method_metrics: dict[str, dict[str, float | None]] = {}
    method_per_query: dict[str, list[dict[str, Any]]] = {}
    for method, rank_field in method_fields.items():
        rows = [
            _pool_query_metrics(
                query_id,
                sorted(by_query.get(query_id, []), key=lambda item: getattr(item, rank_field)),
                label_by_pair,
            )
            for query_id in query_ids
        ]
        method_per_query[method] = rows
        method_metrics[method] = _aggregate_pool_metrics(rows)

    hit_pairs = {(hit.query_id, hit.chunk.chunk_id) for hit in hits}
    assessed_hits = [
        (hit, label_by_pair[(hit.query_id, hit.chunk.chunk_id)])
        for hit in hits
        if (hit.query_id, hit.chunk.chunk_id) in label_by_pair
    ]
    supported = {
        (row["query_id"], row["chunk_id"]) for row in labels if row["citation_supported"]
    }
    contradiction_count = sum(row["contradiction"] for row in labels)
    annotators = sorted({str(row["annotator"]).strip() for row in labels})
    candidate_query_count = len({candidate.query_id for candidate in candidates})
    query_coverage = candidate_query_count / len(query_ids) if query_ids else 0.0
    metrics = {
        **method_metrics["reranked"],
        "citation_precision": _rate(assessed_hits, "citation_supported"),
        "citation_recall": len(supported & hit_pairs) / len(supported) if supported else None,
        "entity_correctness": _rate(assessed_hits, "entity_correct"),
        "organism_correctness": _rate(assessed_hits, "organism_correct"),
        "primary_experiment_retrieval_rate": _rate(assessed_hits, "primary_experiment"),
        "query_candidate_coverage": query_coverage,
    }
    labeled_queries = len({row["query_id"] for row in labels})
    acceptance = _assess_acceptance(
        metrics=metrics,
        label_count=len(labels),
        labeled_queries=labeled_queries,
        contradiction_count=contradiction_count,
        pool_complete=pool_complete,
        annotators=annotators,
        acceptance_path=acceptance_path,
        minimum_queries=minimum_queries,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    error_path = output_dir / "literature_error_analysis.tsv"
    error_rows = _error_analysis(candidates, label_by_pair)
    write_tsv(
        error_path,
        error_rows,
        [
            "query_id",
            "chunk_id",
            "pmid",
            "reranker_rank",
            "relevant",
            "contradiction",
            "entity_correct",
            "organism_correct",
            "primary_experiment",
            "error_categories",
            "title",
            "source_url",
        ],
    )
    result = {
        "schema_version": 2,
        "evaluator_version": "literature-pooled-evaluation-v2",
        "created_at": datetime.now(UTC).isoformat(),
        "status": acceptance["status"],
        "minimum_queries": acceptance["minimum_queries"],
        "labeled_query_count": labeled_queries,
        "label_count": len(labels),
        "candidate_count": len(candidates),
        "candidate_pool_complete": pool_complete,
        "missing_label_count": len(missing_labels),
        "extra_label_count": len(extra_labels),
        "contradiction_label_count": contradiction_count,
        "annotators": annotators,
        "metrics": metrics,
        "method_metrics": method_metrics,
        "per_query": method_per_query["reranked"],
        "acceptance": acceptance,
        "error_analysis": {
            "path": str(error_path),
            "sha256": file_sha256(error_path),
            "flagged_candidate_count": sum(bool(row["error_categories"]) for row in error_rows),
        },
        "inputs": {
            "hits": file_sha256(hits_path),
            "labels": file_sha256(labels_path),
            "candidates": file_sha256(candidates_path),
            "queries": file_sha256(queries_path) if queries_path else None,
            "acceptance": file_sha256(acceptance_path) if acceptance_path else None,
        },
        "interpretation": (
            "Recall is pooled recall over the completely judged PubMed candidate pool, not "
            "absolute recall over all scientific literature. Human expert provenance "
            "remains required."
        ),
    }
    write_json(output_dir / "literature_evaluation.json", result)
    return result


def write_label_template(*, hits_path: Path, output_path: Path) -> None:
    hits = read_jsonl(hits_path, LiteratureHit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=sorted(LABEL_FIELDS),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for hit in hits:
            writer.writerow(
                {
                    "query_id": hit.query_id,
                    "chunk_id": hit.chunk.chunk_id,
                    "relevant": "",
                    "citation_supported": "",
                    "entity_correct": "",
                    "organism_correct": "",
                    "primary_experiment": "",
                    "contradiction": "",
                    "annotator": "",
                    "notes": "",
                }
            )


def write_candidate_label_template(*, candidates_path: Path, output_path: Path) -> None:
    candidates = read_jsonl(candidates_path, LiteratureCandidate)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CANDIDATE_REVIEW_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for candidate in sorted(
            candidates, key=lambda item: (item.query_id, item.reranker_rank, item.chunk.chunk_id)
        ):
            writer.writerow(
                {
                    "query_id": candidate.query_id,
                    "chunk_id": candidate.chunk.chunk_id,
                    "relevant": "",
                    "citation_supported": "",
                    "entity_correct": "",
                    "organism_correct": "",
                    "primary_experiment": "",
                    "contradiction": "",
                    "annotator": "",
                    "notes": "",
                    "pmid": candidate.chunk.pmid or "",
                    "title": candidate.chunk.title,
                    "section_type": candidate.chunk.section_type,
                    "text": candidate.chunk.text,
                    "source_url": candidate.chunk.source_url,
                    "lexical_rank": candidate.lexical_rank,
                    "vector_rank": candidate.vector_rank,
                    "hybrid_rank": candidate.hybrid_rank,
                    "reranker_rank": candidate.reranker_rank,
                }
            )


def _read_labels(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = set(reader.fieldnames or [])
        missing = LABEL_FIELDS - fields
        unexpected = fields - set(CANDIDATE_REVIEW_FIELDS)
        if missing or unexpected:
            raise ValueError(
                f"label columns missing={sorted(missing)}, unexpected={sorted(unexpected)}"
            )
        rows = list(reader)
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, 2):
        key = (row["query_id"], row["chunk_id"])
        if key in seen:
            raise ValueError(f"duplicate label at line {index}: {key}")
        seen.add(key)
        if not row["annotator"].strip():
            raise ValueError(f"annotator is required at line {index}")
        result.append(
            {
                **row,
                **{
                    field: _boolean(row[field], index)
                    for field in (
                        "relevant",
                        "citation_supported",
                        "entity_correct",
                        "organism_correct",
                        "primary_experiment",
                        "contradiction",
                    )
                },
            }
        )
    return result


def _boolean(value: str, line: int) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError(f"manual boolean label required at line {line}, got {value!r}")
    return normalized in {"true", "1", "yes"}


def _reciprocal_rank(hits: list[LiteratureHit], relevant: set[str]) -> float:
    return next(
        (1 / index for index, hit in enumerate(hits, 1) if hit.chunk.chunk_id in relevant),
        0.0,
    )


def _ndcg(hits: list[LiteratureHit], relevant: set[str]) -> float | None:
    if not relevant:
        return None
    dcg = sum(
        1 / math.log2(index + 1)
        for index, hit in enumerate(hits, 1)
        if hit.chunk.chunk_id in relevant
    )
    ideal = sum(1 / math.log2(index + 1) for index in range(1, min(len(relevant), len(hits)) + 1))
    return dcg / ideal if ideal else 0.0


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rate(assessed: list[tuple[LiteratureHit, dict[str, Any]]], field: str) -> float | None:
    return _mean([float(row[field]) for _hit, row in assessed])


def _citation_recall(hits: list[LiteratureHit], labels: list[dict[str, Any]]) -> float | None:
    required = {(row["query_id"], row["chunk_id"]) for row in labels if row["citation_supported"]}
    retrieved = {(hit.query_id, hit.chunk.chunk_id) for hit in hits}
    return len(required & retrieved) / len(required) if required else None


def _pool_query_metrics(
    query_id: str,
    ranked: list[LiteratureCandidate],
    labels: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    relevant = {
        chunk_id
        for (label_query, chunk_id), row in labels.items()
        if label_query == query_id and row["relevant"]
    }
    contradictions = {
        chunk_id
        for (label_query, chunk_id), row in labels.items()
        if label_query == query_id and row["contradiction"]
    }
    row: dict[str, Any] = {
        "query_id": query_id,
        "candidate_count": len(ranked),
        "relevant_count": len(relevant),
        "mrr": next(
            (
                1 / index
                for index, item in enumerate(ranked, 1)
                if item.chunk.chunk_id in relevant
            ),
            0.0,
        ),
        "ndcg_at_10": _candidate_ndcg(ranked[:10], relevant),
    }
    for k in (1, 5, 10):
        selected = ranked[:k]
        matches = sum(item.chunk.chunk_id in relevant for item in selected)
        row[f"precision_at_{k}"] = matches / len(selected) if selected else 0.0
        row[f"recall_at_{k}"] = matches / len(relevant) if relevant else None
    row["contradiction_recall_at_10"] = (
        sum(item.chunk.chunk_id in contradictions for item in ranked[:10]) / len(contradictions)
        if contradictions
        else None
    )
    return row


def _candidate_ndcg(
    candidates: list[LiteratureCandidate], relevant: set[str]
) -> float | None:
    if not relevant:
        return None
    dcg = sum(
        1 / math.log2(index + 1)
        for index, item in enumerate(candidates, 1)
        if item.chunk.chunk_id in relevant
    )
    ideal = sum(
        1 / math.log2(index + 1)
        for index in range(1, min(len(relevant), len(candidates)) + 1)
    )
    return dcg / ideal if ideal else 0.0


def _aggregate_pool_metrics(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    keys = (
        "precision_at_1",
        "precision_at_5",
        "precision_at_10",
        "recall_at_1",
        "recall_at_5",
        "recall_at_10",
        "mrr",
        "ndcg_at_10",
        "contradiction_recall_at_10",
    )
    return {
        key: _mean([row[key] for row in rows if row.get(key) is not None]) for key in keys
    }


def _assess_acceptance(
    *,
    metrics: dict[str, float | None],
    label_count: int,
    labeled_queries: int,
    contradiction_count: int,
    pool_complete: bool,
    annotators: list[str],
    acceptance_path: Path | None,
    minimum_queries: int,
) -> dict[str, Any]:
    if acceptance_path is None:
        return {
            "status": (
                "EVALUATED" if labeled_queries >= minimum_queries else "INSUFFICIENT_MANUAL_LABELS"
            ),
            "minimum_queries": minimum_queries,
            "checks": [],
        }
    config = yaml.safe_load(acceptance_path.read_text(encoding="utf-8"))
    thresholds = config["acceptance_policy"]["thresholds"]
    required_queries = int(config["minimum_manually_labeled_queries"])
    checks = [
        _check("minimum_queries", labeled_queries, required_queries, ">="),
        _check("complete_candidate_pool", pool_complete, True, "=="),
        _check(
            "expert_annotation_provenance",
            not any(value in set(config.get("prohibited_annotators", [])) for value in annotators),
            True,
            "==",
        ),
        _check(
            "minimum_contradiction_labels",
            contradiction_count,
            int(config["minimum_contradiction_labels"]),
            ">=",
        ),
    ]
    for name, threshold in thresholds.items():
        checks.append(_check(name, metrics.get(name), float(threshold), ">="))
    status = "PASS" if all(row["passed"] for row in checks) else "FAIL"
    return {
        "status": status,
        "minimum_queries": required_queries,
        "label_count": label_count,
        "threshold_version": config["evaluation_version"],
        "checks": checks,
    }


def _check(name: str, observed: Any, threshold: Any, operator: str) -> dict[str, Any]:
    if operator == ">=":
        passed = observed is not None and observed >= threshold
    else:
        passed = observed == threshold
    return {
        "name": name,
        "observed": observed,
        "operator": operator,
        "threshold": threshold,
        "passed": passed,
    }


def _error_analysis(
    candidates: list[LiteratureCandidate],
    labels: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in sorted(
        candidates, key=lambda item: (item.query_id, item.reranker_rank, item.chunk.chunk_id)
    ):
        label = labels.get((candidate.query_id, candidate.chunk.chunk_id))
        if label is None:
            continue
        top_ten = candidate.reranker_rank <= 10
        categories: list[str] = []
        if top_ten and not label["relevant"]:
            categories.append("TOP10_IRRELEVANT")
        if label["relevant"] and not top_ten:
            categories.append("RELEVANT_MISSED_AT_10")
        if top_ten and not label["entity_correct"]:
            categories.append("TOP10_ENTITY_MISMATCH")
        if top_ten and not label["organism_correct"]:
            categories.append("TOP10_ORGANISM_MISMATCH")
        if top_ten and not label["primary_experiment"]:
            categories.append("TOP10_NOT_PRIMARY_EXPERIMENT")
        if label["contradiction"] and not top_ten:
            categories.append("CONTRADICTION_MISSED_AT_10")
        rows.append(
            {
                "query_id": candidate.query_id,
                "chunk_id": candidate.chunk.chunk_id,
                "pmid": candidate.chunk.pmid,
                "reranker_rank": candidate.reranker_rank,
                "relevant": label["relevant"],
                "contradiction": label["contradiction"],
                "entity_correct": label["entity_correct"],
                "organism_correct": label["organism_correct"],
                "primary_experiment": label["primary_experiment"],
                "error_categories": ";".join(categories),
                "title": candidate.chunk.title,
                "source_url": candidate.chunk.source_url,
            }
        )
    return rows
