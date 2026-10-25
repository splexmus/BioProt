from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

EXTERNAL2GO_RE = re.compile(r"^(\S+).* > GO:.* ; (GO:\d{7})$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build benchmark-independent Phase 3 mapping resources."
    )
    parser.add_argument("--interpro2go", type=Path, required=True)
    parser.add_argument("--ec2go", type=Path, required=True)
    parser.add_argument("--go-obo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def external2go_rows(path: Path, mapping_type: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = EXTERNAL2GO_RE.match(line)
        if not match or line.startswith("!"):
            continue
        source, target = match.groups()
        rows.append(
            {
                "mapping_type": mapping_type,
                "source_id": source,
                "target_id": target,
                "relation": "SAFE_FUNCTION_PROJECTION",
                "source": path.name,
            }
        )
    return rows


def go_synonyms(path: Path) -> tuple[list[dict[str, str]], str]:
    version = "unknown"
    current: dict[str, object] = {}
    terms: list[dict[str, object]] = []
    in_term = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("data-version:"):
            version = line.split(":", 1)[1].strip()
        if line == "[Term]":
            if current:
                terms.append(current)
            current = {"synonyms": []}
            in_term = True
            continue
        if line.startswith("["):
            if current:
                terms.append(current)
            current = {}
            in_term = False
            continue
        if not in_term or not line:
            continue
        key, separator, value = line.partition(": ")
        if not separator:
            continue
        if key == "synonym":
            match = re.match(r'^"(.+)" EXACT ', value)
            if match:
                current.setdefault("synonyms", []).append(match.group(1))
        elif key in {"id", "name", "namespace", "is_obsolete"}:
            current[key] = value
    if current:
        terms.append(current)

    proposed: dict[str, set[str]] = {}
    for term in terms:
        if term.get("namespace") != "molecular_function" or term.get("is_obsolete") == "true":
            continue
        identifier = str(term.get("id", ""))
        if not identifier or identifier == "GO:0003674":
            continue
        values = [str(term.get("name", "")), *[str(item) for item in term.get("synonyms", [])]]
        for value in values:
            normalized = normalize_label(value)
            if normalized:
                proposed.setdefault(normalized, set()).add(identifier)
    rows: list[dict[str, str]] = []
    for normalized, identifiers in sorted(proposed.items()):
        if len(identifiers) != 1:
            continue
        rows.append(
            {
                "normalized_label": normalized,
                "canonical_candidate_id": next(iter(identifiers)),
                "source": "Gene Ontology molecular-function name or EXACT synonym",
                "source_version": version,
            }
        )
    return rows, version


def normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    projections = external2go_rows(args.interpro2go, "INTERPRO2GO")
    projections.extend(external2go_rows(args.ec2go, "EC2GO"))
    synonyms, go_version = go_synonyms(args.go_obo)
    write_tsv(
        args.output / "mapping_projections.tsv",
        projections,
        ["mapping_type", "source_id", "target_id", "relation", "source"],
    )
    write_tsv(
        args.output / "synonyms.tsv",
        synonyms,
        ["normalized_label", "canonical_candidate_id", "source", "source_version"],
    )
    inputs = [args.interpro2go, args.ec2go, args.go_obo]
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "go_version": go_version,
        "projection_count": len(projections),
        "synonym_count": len(synonyms),
        "inputs": [
            {"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size}
            for path in inputs
        ],
        "limitations": [
            "InterPro2GO and EC2GO are safe annotation projections, not identifier equivalence.",
            "GO names and EXACT synonyms affect free-text consolidation only.",
            "Mapping-derived predictions remain separate from experimental gold provenance.",
        ],
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
