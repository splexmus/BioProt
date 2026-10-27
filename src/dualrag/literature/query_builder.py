from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, read_tsv, stable_hash, write_json
from dualrag.literature.schemas import LiteratureQuery, SelectedHomolog
from dualrag.models import ProteinQuery
from dualrag.structure.alphafold import resolve_accession

QUERY_BUILDER_VERSION = "deterministic-literature-query-v1"
QUERY_FILENAME = "literature_queries.jsonl"
MANIFEST_FILENAME = "literature_query_manifest.json"
CONTEXT_FIELDS = {
    "query_id",
    "query_accession",
    "protein_name",
    "organism",
    "taxonomy_id",
}
REQUIRED_RUN_FILES = (
    "queries.tsv",
    "function_candidates.tsv",
    "fusion_summary.tsv",
    "alternatives.tsv",
    "sequence_results.tsv",
    "run_metadata.json",
)


def build_literature_queries(
    *,
    run_dir: Path,
    output_dir: Path,
    context_path: Path | None = None,
    max_candidates: int = 5,
    max_homologs: int = 5,
    max_alternatives: int = 3,
) -> dict[str, object]:
    """Build deterministic, leakage-safe literature queries from pipeline artifacts."""
    for name in REQUIRED_RUN_FILES:
        path = run_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"required pipeline artifact is missing: {path}")
    for name, value in (
        ("max_candidates", max_candidates),
        ("max_homologs", max_homologs),
        ("max_alternatives", max_alternatives),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    if max_candidates == 0:
        raise ValueError("max_candidates must be at least 1")

    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    created_at = datetime.fromisoformat(str(metadata["created_at"]))
    run_id = str(metadata["run_id"])
    parameters_hash = str(metadata["parameters_hash"])
    context = _load_context(context_path)
    queries = read_tsv(run_dir / "queries.tsv")
    query_ids = {row["query_id"] for row in queries}
    unused_context = sorted(set(context) - query_ids)
    if unused_context:
        raise ValueError(f"query context contains unknown query IDs: {unused_context[:5]}")
    candidates = _group_rows(read_tsv(run_dir / "function_candidates.tsv"))
    summaries = _single_rows(read_tsv(run_dir / "fusion_summary.tsv"), "fusion summary")
    alternatives = _group_rows(read_tsv(run_dir / "alternatives.tsv"))
    sequence_hits = _group_rows(read_tsv(run_dir / "sequence_results.tsv"))

    records: list[LiteratureQuery] = []
    for query_row in queries:
        query_id = query_row["query_id"]
        query_context = context.get(query_id, {})
        context_accession = query_context.get("query_accession") or None
        accession = (
            _validate_context_accession(context_accession)
            if context_accession
            else _resolve_query_accession(query_row)
        )
        protein_name = query_context.get("protein_name") or None
        organism = query_context.get("organism") or None
        taxonomy_id = _optional_int(query_context.get("taxonomy_id"))
        if accession is None and protein_name is None:
            raise ValueError(
                f"query {query_id!r} requires query_accession or protein_name in context"
            )
        selected_candidates = _select_candidates(candidates.get(query_id, []), max_candidates)
        selected_homologs = _select_homologs(
            sequence_hits.get(query_id, []), accession, max_homologs
        )
        alternative_hypotheses = _select_alternatives(
            alternatives.get(query_id, []), selected_candidates, max_alternatives
        )
        terms = _query_terms(
            accession=accession,
            protein_name=protein_name,
            organism=organism,
            candidates=selected_candidates,
            homologs=selected_homologs,
        )
        variants = _query_variants(
            accession=accession,
            protein_name=protein_name,
            organism=organism,
            candidates=selected_candidates,
            homologs=selected_homologs,
            alternatives=alternative_hypotheses,
        )
        summary = summaries.get(query_id)
        if summary is None:
            raise ValueError(f"fusion summary is missing query {query_id!r}")
        records.append(
            LiteratureQuery(
                query_id=query_id,
                query_accession=accession,
                protein_name=protein_name,
                organism=organism,
                taxonomy_id=taxonomy_id,
                candidate_ids=[item["candidate_id"] for item in selected_candidates],
                candidate_labels=_candidate_labels(selected_candidates),
                selected_homologs=selected_homologs,
                alternative_hypotheses=alternative_hypotheses,
                cross_modal_status=summary["cross_modal_status"],
                query_terms=terms,
                query_variants=variants,
                query_builder_version=QUERY_BUILDER_VERSION,
                source_biological_run_id=run_id,
                source_parameters_hash=parameters_hash,
                created_at=created_at,
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    query_path = output_dir / QUERY_FILENAME
    query_path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n" for record in records
        ),
        encoding="utf-8",
    )
    inputs = {name: file_sha256(run_dir / name) for name in REQUIRED_RUN_FILES}
    if context_path is not None:
        inputs["query_context"] = file_sha256(context_path)
    parameters = {
        "builder_version": QUERY_BUILDER_VERSION,
        "max_candidates": max_candidates,
        "max_homologs": max_homologs,
        "max_alternatives": max_alternatives,
    }
    manifest: dict[str, object] = {
        "schema_version": 1,
        "contract_id": "phase4-literature-v1",
        "created_at": created_at.isoformat(),
        "source_run_id": run_id,
        "source_parameters_hash": parameters_hash,
        "query_count": len(records),
        "queries_with_accession": sum(record.query_accession is not None for record in records),
        "queries_with_organism": sum(record.organism is not None for record in records),
        "builder_parameters": parameters,
        "builder_parameters_hash": stable_hash(parameters),
        "inputs": inputs,
        "output": {"path": str(query_path), "sha256": file_sha256(query_path)},
        "prohibited_inputs_not_accessed": [
            "benchmark_gold_labels",
            "held_out_answers",
            "evaluation_annotations",
            "manual_literature_relevance_labels",
        ],
        "limitations": [
            "Organism and taxonomy are emitted only when supplied by query_context.tsv.",
            "Selected homologs come only from sequence_results.tsv; structural matches "
            "are not relabelled as homologs.",
            "Query variants are source-neutral; PubMed field translation belongs to Phase 4.3.",
        ],
    }
    write_json(output_dir / MANIFEST_FILENAME, manifest)
    return manifest


def _load_context(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    if not path.is_file():
        raise FileNotFoundError(f"query context is missing: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = set(reader.fieldnames or [])
        if fields != CONTEXT_FIELDS:
            unexpected = sorted(fields - CONTEXT_FIELDS)
            missing = sorted(CONTEXT_FIELDS - fields)
            raise ValueError(
                f"query context columns must be exactly {sorted(CONTEXT_FIELDS)}; "
                f"unexpected={unexpected}, missing={missing}"
            )
        rows = list(reader)
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        query_id = row["query_id"].strip()
        if not query_id:
            raise ValueError("query context contains an empty query_id")
        if query_id in result:
            raise ValueError(f"duplicate query context row: {query_id}")
        result[query_id] = row
    return result


def _group_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["query_id"]].append(row)
    return grouped


def _single_rows(rows: list[dict[str, str]], label: str) -> dict[str, dict[str, str]]:
    grouped = _group_rows(rows)
    duplicates = sorted(query_id for query_id, values in grouped.items() if len(values) != 1)
    if duplicates:
        raise ValueError(f"{label} requires one row per query: {duplicates[:5]}")
    return {query_id: values[0] for query_id, values in grouped.items()}


def _resolve_query_accession(row: dict[str, str]) -> str | None:
    accession, _method = resolve_accession(
        ProteinQuery(
            query_id=row["query_id"],
            sequence=row["sequence"],
            description=row.get("description") or None,
        )
    )
    return accession


def _validate_context_accession(value: str) -> str:
    accession, _method = resolve_accession(ProteinQuery(query_id=value, sequence="A"))
    if accession != value:
        raise ValueError(f"invalid UniProt query_accession in context: {value!r}")
    return value


def _select_candidates(rows: list[dict[str, str]], maximum: int) -> list[dict[str, str]]:
    selected = [row for row in rows if _bool(row.get("informative"))]
    selected.sort(key=lambda row: (_int(row.get("rank"), 10**9), row["candidate_id"]))
    return selected[:maximum]


def _candidate_labels(candidates: list[dict[str, str]]) -> list[str]:
    return _unique(
        label
        for candidate in candidates
        for label in candidate.get("candidate_labels", "").split(";")
        if label
    )


def _select_homologs(
    rows: list[dict[str, str]], query_accession: str | None, maximum: int
) -> list[SelectedHomolog]:
    if maximum == 0:
        return []
    ordered = sorted(
        rows,
        key=lambda row: (
            -_float(row.get("normalized_score"), 0.0),
            row.get("source_accession") or row.get("target_id") or "",
        ),
    )
    selected: list[SelectedHomolog] = []
    seen: set[str] = set()
    for row in ordered:
        accession = (row.get("source_accession") or row.get("target_id") or "").strip()
        if not accession or accession == query_accession or accession in seen:
            continue
        seen.add(accession)
        selected.append(
            SelectedHomolog(
                accession=accession,
                source_target_id=row.get("target_id") or accession,
                sequence_identity=_optional_float(row.get("sequence_identity")),
                alignment_coverage=_optional_float(row.get("alignment_coverage")),
                normalized_score=_optional_float(row.get("normalized_score")),
                provenance=(
                    f"{row.get('tool', 'unknown')}@{row.get('tool_version', 'unknown')}|"
                    f"{row.get('database', 'unknown')}@{row.get('database_version', 'unknown')}"
                ),
            )
        )
        if len(selected) == maximum:
            break
    return selected


def _select_alternatives(
    rows: list[dict[str, str]], candidates: list[dict[str, str]], maximum: int
) -> list[str]:
    if maximum == 0:
        return []
    selected_ids = {row["candidate_id"] for row in candidates[:1]}
    ordered = sorted(rows, key=lambda row: (_int(row.get("rank"), 10**9), row["candidate_id"]))
    values: list[str] = []
    for row in ordered:
        if row["candidate_id"] in selected_ids:
            continue
        label = next((item for item in row.get("candidate_labels", "").split(";") if item), "")
        values.append(f"{row['candidate_id']}: {label}" if label else row["candidate_id"])
        if len(values) == maximum:
            break
    return values


def _query_terms(
    *,
    accession: str | None,
    protein_name: str | None,
    organism: str | None,
    candidates: list[dict[str, str]],
    homologs: list[SelectedHomolog],
) -> list[str]:
    return _unique(
        [
            accession,
            protein_name,
            organism,
            *(item["candidate_id"] for item in candidates),
            *_candidate_labels(candidates),
            *(item.accession for item in homologs),
        ]
    )


def _query_variants(
    *,
    accession: str | None,
    protein_name: str | None,
    organism: str | None,
    candidates: list[dict[str, str]],
    homologs: list[SelectedHomolog],
    alternatives: list[str],
) -> list[str]:
    identities = [value for value in (accession, protein_name) if value]
    variants: list[str] = []
    if not identities:
        return variants
    primary_identity = identities[0]
    labels = _candidate_labels(candidates)
    for candidate in candidates:
        candidate_labels = [
            value for value in candidate.get("candidate_labels", "").split(";") if value
        ]
        if candidate_labels:
            variants.append(_and(primary_identity, candidate_labels[0], organism))
        variants.append(_and(primary_identity, candidate["candidate_id"], organism))
    if protein_name and accession and labels:
        variants.append(_and(protein_name, labels[0], organism))
    for homolog in homologs[:2]:
        if labels:
            variants.append(_and(homolog.accession, labels[0]))
    for alternative in alternatives:
        _separator, _found, label = alternative.rpartition(": ")
        variants.append(_and(primary_identity, label or alternative))
    if not variants:
        variants.append(_and(primary_identity, organism))
    return _unique(variants)[:12]


def _and(*values: str | None) -> str:
    return " AND ".join(_quote(value) for value in values if value)


def _quote(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip()).replace('"', '\\"')
    return f'"{normalized}"'


def _unique(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if raw is None:
            continue
        value = str(raw).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _bool(value: str | None) -> bool:
    return bool(value and value.casefold() in {"true", "1", "yes"})


def _int(value: str | None, default: int) -> int:
    return int(value) if value else default


def _float(value: str | None, default: float) -> float:
    return float(value) if value else default


def _optional_float(value: str | None) -> float | None:
    return float(value) if value else None


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None
