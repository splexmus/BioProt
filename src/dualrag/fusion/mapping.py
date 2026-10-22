from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from dualrag.fusion.candidates import canonical_candidate_id
from dualrag.io import file_sha256
from dualrag.models import CandidateContribution, CandidateKind


class MappingRelation(StrEnum):
    EXACT = "EXACT"
    BROADER = "BROADER"
    NARROWER = "NARROWER"
    RELATED = "RELATED"


@dataclass(frozen=True)
class CandidateMapping:
    source_candidate_id: str
    canonical_candidate_id: str
    relation: MappingRelation
    source: str
    source_version: str

    @property
    def provenance(self) -> str:
        return f"{self.source}@{self.source_version}:{self.relation.value}"


@dataclass(frozen=True)
class MappingBundle:
    mappings: tuple[CandidateMapping, ...] = ()
    inputs: tuple[dict[str, str], ...] = ()


def load_mapping_bundle(mapping_path: Path | None, synonym_path: Path | None) -> MappingBundle:
    mappings: list[CandidateMapping] = []
    inputs: list[dict[str, str]] = []
    if mapping_path:
        mappings.extend(_read_mappings(mapping_path))
        inputs.append(_input_record("mapping", mapping_path))
    if synonym_path:
        mappings.extend(_read_synonyms(synonym_path))
        inputs.append(_input_record("synonym", synonym_path))
    _validate_exact_mappings(mappings)
    return MappingBundle(tuple(mappings), tuple(inputs))


def apply_exact_mappings(
    contributions: list[CandidateContribution], bundle: MappingBundle
) -> tuple[list[CandidateContribution], int]:
    exact: dict[str, list[CandidateMapping]] = defaultdict(list)
    for item in bundle.mappings:
        if item.relation is MappingRelation.EXACT:
            exact[item.source_candidate_id].append(item)
    mapped: list[CandidateContribution] = []
    mapped_count = 0
    for contribution in contributions:
        current = contribution.candidate_id
        provenance: list[str] = []
        seen: set[str] = set()
        while current in exact:
            if current in seen:
                raise ValueError(f"cyclic exact candidate mapping involving {current}")
            seen.add(current)
            rules = exact[current]
            current = rules[0].canonical_candidate_id
            provenance.extend(rule.provenance for rule in rules)
        if current != contribution.candidate_id:
            mapped_count += 1
        mapped.append(
            replace(
                contribution,
                candidate_id=current,
                candidate_kind=_kind_from_id(current),
                mapping_provenance=";".join(provenance),
            )
        )
    return mapped, mapped_count


def compatibility_pairs(bundle: MappingBundle) -> dict[frozenset[str], list[str]]:
    pairs: dict[frozenset[str], list[str]] = {}
    for item in bundle.mappings:
        if item.relation is MappingRelation.EXACT:
            continue
        key = frozenset((item.source_candidate_id, item.canonical_candidate_id))
        pairs.setdefault(key, []).append(item.provenance)
    return pairs


def _read_mappings(path: Path) -> list[CandidateMapping]:
    rows = _rows(
        path,
        {"source_candidate_id", "canonical_candidate_id", "relation", "source", "source_version"},
    )
    return [
        CandidateMapping(
            row["source_candidate_id"].strip(),
            row["canonical_candidate_id"].strip(),
            MappingRelation(row["relation"].strip().upper()),
            row["source"].strip(),
            row["source_version"].strip(),
        )
        for row in rows
    ]


def _read_synonyms(path: Path) -> list[CandidateMapping]:
    rows = _rows(path, {"normalized_label", "canonical_candidate_id", "source", "source_version"})
    return [
        CandidateMapping(
            canonical_candidate_id(CandidateKind.LABEL, row["normalized_label"]),
            row["canonical_candidate_id"].strip(),
            MappingRelation.EXACT,
            row["source"].strip(),
            row["source_version"].strip(),
        )
        for row in rows
    ]


def _rows(path: Path, required: set[str]) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"fusion mapping input does not exist: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = set(reader.fieldnames or [])
        if missing := required - fields:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        rows = list(reader)
    for number, row in enumerate(rows, start=2):
        if any(not row.get(key, "").strip() for key in required):
            raise ValueError(f"{path}:{number} has an empty required field")
    return rows


def _validate_exact_mappings(mappings: list[CandidateMapping]) -> None:
    targets: dict[str, str] = {}
    for item in mappings:
        if item.relation is not MappingRelation.EXACT:
            continue
        prior = targets.setdefault(item.source_candidate_id, item.canonical_candidate_id)
        if prior != item.canonical_candidate_id:
            raise ValueError(f"conflicting exact mappings for {item.source_candidate_id}")
    for start in targets:
        current = start
        seen: set[str] = set()
        while current in targets:
            if current in seen:
                raise ValueError(f"cyclic exact candidate mapping involving {current}")
            seen.add(current)
            current = targets[current]


def _kind_from_id(candidate_id: str) -> CandidateKind:
    prefix = candidate_id.split(":", 1)[0]
    aliases = {"OG": CandidateKind.ORTHOLOGOUS_GROUP}
    if prefix in aliases:
        return aliases[prefix]
    try:
        return CandidateKind(prefix)
    except ValueError as error:
        raise ValueError(f"unsupported canonical candidate namespace: {candidate_id}") from error


def _input_record(kind: str, path: Path) -> dict[str, str]:
    return {"kind": kind, "path": str(path), "sha256": file_sha256(path)}
