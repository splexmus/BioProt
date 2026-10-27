from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, read_tsv, stable_hash, write_json
from dualrag.literature.io import write_jsonl
from dualrag.literature.query_builder import QUERY_BUILDER_VERSION, _and, _unique
from dualrag.literature.schemas import LiteratureQuery, SelectedHomolog

BENCHMARK_QUERY_BUILDER_VERSION = f"{QUERY_BUILDER_VERSION}-phase3-pool-v4"


def build_benchmark_literature_queries(
    *,
    dataset_dir: Path,
    phase3_run_dir: Path,
    output_dir: Path,
    split: str = "development",
    maximum_queries: int = 20,
    maximum_candidates: int = 5,
    maximum_homologs: int = 5,
    go_obo_path: Path | None = None,
    ec2go_path: Path | None = None,
) -> dict[str, Any]:
    if maximum_queries < 20:
        raise ValueError("Phase 4 exit benchmark requires at least 20 queries")
    dataset_path = dataset_dir / "queries.tsv"
    splits_path = dataset_dir / "splits.tsv"
    predictions_path = phase3_run_dir / "predictions.tsv"
    sequence_path = phase3_run_dir / "raw" / "sequence_evidence.tsv"
    reproducibility_path = phase3_run_dir / "reproducibility_manifest.json"
    required = (dataset_path, splits_path, predictions_path, sequence_path, reproducibility_path)
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"required Phase 3 artifact is missing: {path}")

    dataset = {row["accession"]: row for row in read_tsv(dataset_path)}
    split_accessions = sorted(
        row["accession"] for row in read_tsv(splits_path) if row["split"] == split
    )
    predictions = _group_predictions(read_tsv(predictions_path))
    eligible = [accession for accession in split_accessions if predictions.get(accession)]
    strata: dict[str, list[str]] = defaultdict(list)
    for accession in eligible:
        strata[_cross_modal_status(predictions[accession][:maximum_candidates])].append(accession)
    selected_accessions: list[str] = []
    for status in ("CONFLICT", "STRUCTURE_ONLY", "SEQUENCE_ONLY", "CONSENSUS"):
        for accession in strata.get(status, []):
            if len(selected_accessions) == maximum_queries:
                break
            selected_accessions.append(accession)
    if len(selected_accessions) < 20:
        raise ValueError(
            f"split {split!r} has only {len(selected_accessions)} queries with B4 predictions"
        )
    evidence = _group_sequence_evidence(read_tsv(sequence_path))
    go_names = _load_go_names(go_obo_path)
    ec_names = _load_ec_names(ec2go_path)
    reproducibility = json.loads(reproducibility_path.read_text(encoding="utf-8"))
    created_at = datetime.fromisoformat(str(reproducibility["created_at"]))
    run_id = stable_hash(
        {
            "phase3_run": file_sha256(reproducibility_path),
            "split": split,
            "accessions": selected_accessions,
        }
    )[:16]
    source_parameters_hash = stable_hash(reproducibility.get("configuration", {}))

    records: list[LiteratureQuery] = []
    for accession in selected_accessions:
        row = dataset[accession]
        ranked = predictions.get(accession, [])[:maximum_candidates]
        if not ranked:
            raise ValueError(f"no B4 ALL_MAPPINGS predictions for {accession}")
        candidate_ids = [item["identifier"] for item in ranked]
        candidate_labels = _unique(
            _controlled_label(identifier, go_names, ec_names) for identifier in candidate_ids
        )
        homologs = _select_homologs(evidence.get(accession, []), accession, maximum_homologs)
        status = _cross_modal_status(ranked)
        terms = _unique(
            [
                accession,
                row["protein_name"],
                row["organism"],
                *candidate_ids,
                *candidate_labels,
                *(homolog.accession for homolog in homologs),
            ]
        )
        variants = _benchmark_variants(
            accession=accession,
            protein_name=row["protein_name"],
            organism=row["organism"],
            candidate_ids=candidate_ids,
            candidate_labels=candidate_labels,
            homologs=homologs,
        )
        records.append(
            LiteratureQuery(
                query_id=accession,
                query_accession=accession,
                protein_name=row["protein_name"],
                organism=row["organism"],
                taxonomy_id=int(row["taxonomy_id"]),
                candidate_ids=candidate_ids,
                candidate_labels=candidate_labels,
                selected_homologs=homologs,
                alternative_hypotheses=[
                    (
                        f"{item['identifier']}: "
                        f"{_controlled_label(item['identifier'], go_names, ec_names)}"
                    )
                    for item in ranked[1:4]
                ],
                cross_modal_status=status,
                query_terms=terms,
                query_variants=variants,
                query_builder_version=BENCHMARK_QUERY_BUILDER_VERSION,
                source_biological_run_id=run_id,
                source_parameters_hash=source_parameters_hash,
                created_at=created_at,
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    query_path = output_dir / "literature_queries.jsonl"
    write_jsonl(query_path, records)
    manifest = {
        "schema_version": 1,
        "contract_id": "phase4-literature-v1",
        "builder_version": BENCHMARK_QUERY_BUILDER_VERSION,
        "created_at": created_at.isoformat(),
        "split": split,
        "query_count": len(records),
        "cross_modal_counts": {
            status: sum(record.cross_modal_status == status for record in records)
            for status in (
                "CONSENSUS",
                "PARTIAL_CONSENSUS",
                "SEQUENCE_ONLY",
                "STRUCTURE_ONLY",
                "CONFLICT",
                "INSUFFICIENT_EVIDENCE",
            )
        },
        "source_run_id": run_id,
        "source_parameters_hash": source_parameters_hash,
        "inputs": {str(path): file_sha256(path) for path in required},
        "controlled_label_sources": {
            "go_obo": file_sha256(go_obo_path) if go_obo_path else None,
            "ec2go": file_sha256(ec2go_path) if ec2go_path else None,
        },
        "output": {"path": str(query_path), "sha256": file_sha256(query_path)},
        "prohibited_inputs_not_accessed": [
            str(dataset_dir / "gold_labels.tsv"),
            "literature relevance labels",
            "held-out literature judgments",
        ],
    }
    write_json(output_dir / "literature_query_manifest.json", manifest)
    return manifest


def _group_predictions(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["baseline"] == "B4_DUAL_DETERMINISTIC" and row["ablation"] == "ALL_MAPPINGS":
            result[row["query_accession"]].append(row)
    for values in result.values():
        values.sort(key=lambda row: (int(row["rank"]), row["namespace"], row["identifier"]))
    return result


def _group_sequence_evidence(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        match = re.search(r"\|([A-Z0-9]+)\|", row["query_id"])
        accession = match.group(1) if match else row["query_id"]
        result[accession].append(row)
    return result


def _select_homologs(
    rows: list[dict[str, str]], query_accession: str, maximum: int
) -> list[SelectedHomolog]:
    ordered = sorted(
        rows,
        key=lambda row: (-float(row.get("normalized_score") or 0), row["target_id"]),
    )
    values: list[SelectedHomolog] = []
    seen: set[str] = set()
    for row in ordered:
        accession = row.get("source_accession") or row["target_id"]
        if not accession or accession == query_accession or accession in seen:
            continue
        seen.add(accession)
        values.append(
            SelectedHomolog(
                accession=accession,
                source_target_id=row["target_id"],
                sequence_identity=(
                    float(row["sequence_identity"]) if row["sequence_identity"] else None
                ),
                alignment_coverage=(
                    float(row["alignment_coverage"]) if row["alignment_coverage"] else None
                ),
                normalized_score=(
                    float(row["normalized_score"]) if row["normalized_score"] else None
                ),
                provenance=(
                    f"{row['tool']}@{row['tool_version']}|"
                    f"{row['database']}@{row['database_version']}"
                ),
            )
        )
        if len(values) == maximum:
            break
    return values


def _cross_modal_status(rows: list[dict[str, str]]) -> str:
    modalities = {value for row in rows for value in row["modalities"].split(";") if value}
    if modalities == {"sequence", "structure"}:
        if any(row["modalities"] == "sequence;structure" for row in rows):
            return "CONSENSUS"
        return "CONFLICT"
    if modalities == {"sequence"}:
        return "SEQUENCE_ONLY"
    if modalities == {"structure"}:
        return "STRUCTURE_ONLY"
    return "INSUFFICIENT_EVIDENCE"


def _benchmark_variants(
    *,
    accession: str,
    protein_name: str,
    organism: str,
    candidate_ids: list[str],
    candidate_labels: list[str],
    homologs: list[SelectedHomolog],
) -> list[str]:
    organism_aliases = _organism_aliases(organism)
    protein_aliases = _protein_name_aliases(protein_name)
    primary_organism = organism_aliases[0] if organism_aliases else organism
    variants = [
        _and(protein_name, organism),
        _and(protein_name, primary_organism),
        _and(accession, protein_name),
        _and(accession),
    ]
    for alias in protein_aliases[1:6]:
        variants.extend((_and(alias, primary_organism), _and(alias)))

    # A protein-name-only query is an intentionally late, bounded fallback. It fixes
    # zero-hit cases caused by exact strain strings while PubMed's per-query candidate
    # cap prevents generic names from creating an unbounded pool.
    variants.append(_and(protein_name))
    for organism_alias in organism_aliases[1:3]:
        variants.append(_and(protein_name, organism_alias))
    for label in candidate_labels[:3]:
        variants.extend((_and(protein_name, label, primary_organism), _and(protein_name, label)))
    for identifier in candidate_ids[:2]:
        variants.append(_and(protein_name, identifier))
    for homolog in homologs[:2]:
        variants.append(_and(homolog.accession, protein_name))
    return _unique(variants)[:20]


def _organism_aliases(organism: str) -> list[str]:
    """Return deterministic organism names without long strain qualifiers."""
    primary = organism.split(" (", 1)[0].strip()
    values = [primary]
    values.extend(
        match.strip()
        for match in re.findall(r"\(([^()]*)\)", organism)
        if match.strip() and not match.casefold().startswith("strain ")
    )
    values.append(organism)
    return _unique(values)


def _protein_name_aliases(protein_name: str) -> list[str]:
    """Derive conservative name aliases from the supplied Phase 3 protein name."""
    values = [protein_name]
    without_prefix = re.sub(r"^protein\s+", "", protein_name, flags=re.IGNORECASE).strip()
    values.append(without_prefix)
    final_token = without_prefix.rsplit(" ", 1)[-1]
    if (
        len(final_token) >= 3
        and re.search(r"[A-Za-z]", final_token)
        and (
            re.search(r"\d", final_token)
            or "-" in final_token
            or re.search(r"[a-z].*[A-Z]", final_token)
        )
    ):
        values.append(final_token)
    values.append(re.sub(r"\s+subunit\s+[A-Z0-9]+$", "", without_prefix).strip())
    values.append(re.sub(r"\s+[A-Z]$", "", without_prefix).strip())
    values.append(re.sub(r"\s+\d+$", "", without_prefix).strip())
    if "/" in without_prefix:
        values.append(without_prefix.rsplit(" ", 1)[-1])
    if ":" in without_prefix and " " in without_prefix:
        suffix = without_prefix.split(" ", 1)[1]
        values.append(suffix)
        values.append(re.sub(r"\s+subunit\s+[A-Z0-9]+$", "", suffix).strip())
    return _unique(values)


def _controlled_label(identifier: str, go_names: dict[str, str], ec_names: dict[str, str]) -> str:
    if identifier.startswith("GO:"):
        return go_names.get(identifier, identifier)
    if identifier.startswith("EC:"):
        return ec_names.get(identifier, identifier)
    return identifier


def _load_go_names(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    result: dict[str, str] = {}
    current_id: str | None = None
    current_name: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "[Term]":
            current_id = current_name = None
        elif line.startswith("id: GO:"):
            current_id = line.removeprefix("id: ")
        elif line.startswith("name: "):
            current_name = line.removeprefix("name: ")
        elif not line and current_id and current_name:
            result[current_id] = current_name
    return result


def _load_ec_names(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    result: dict[str, str] = {}
    pattern = re.compile(r"^(EC:[^ ]+) > GO:(.+?) ; GO:")
    for line in path.read_text(encoding="utf-8").splitlines():
        if match := pattern.match(line):
            result.setdefault(match.group(1), match.group(2))
    return result
