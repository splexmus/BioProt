#!/usr/bin/env python3
"""Build an auditable, portable Phase 2 mapping bundle from official sources."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import shutil
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PFAM_CLANS_URL = "https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam38.2/Pfam-A.clans.tsv.gz"
INTERPRO_RELEASE_URL = (
    "https://ftp.ebi.ac.uk/pub/databases/interpro/current_release/release_notes.txt"
)
INTERPRO_ENTRY_URL = "https://www.ebi.ac.uk/interpro/api/entry/pfam/{accession}/"
UNIPROT_ENTRY_URL = "https://rest.uniprot.org/uniprotkb/{accession}.json"
USER_AGENT = "DualRAG-phase2-mapping-builder/0.2 (+research reproducibility)"


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to mix files into non-empty output directory: {output}")
    sources = output / "sources"
    output.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)

    release_notes = sources / "interpro-release-notes.txt"
    clans_path = sources / "Pfam-A.clans.tsv.gz"
    _download(INTERPRO_RELEASE_URL, release_notes)
    _download(PFAM_CLANS_URL, clans_path)
    candidate_snapshot = sources / "observed-function_candidates.tsv"
    reviewed_manifest_snapshot = sources / "phase1-characterized_manifest.tsv"
    shutil.copyfile(args.candidates, candidate_snapshot)
    shutil.copyfile(args.uniprot_manifest, reviewed_manifest_snapshot)
    interpro_version, pfam_version = _release_versions(release_notes)

    observed = _observed_pfam_candidates(args.candidates)
    pfam_by_name, pfam_names = _load_pfam_names(clans_path)
    mapping_rows: list[dict[str, str]] = []
    mapping_records: list[dict[str, str]] = []
    for observed_name in sorted(observed):
        accessions = pfam_by_name.get(observed_name, [])
        if len(accessions) != 1:
            raise ValueError(
                f"observed Pfam name {observed_name!r} resolved to {accessions}; "
                "exactly one official Pfam 38.2 accession is required"
            )
        accession = accessions[0]
        record_path = sources / f"interpro-{accession}.json"
        _download(INTERPRO_ENTRY_URL.format(accession=accession), record_path)
        record = json.loads(record_path.read_text(encoding="utf-8"))
        metadata = record.get("metadata", {})
        integrated = metadata.get("integrated")
        if metadata.get("accession") != accession or not integrated:
            raise ValueError(f"{accession} has no verified integrated InterPro entry")
        version = f"InterPro {interpro_version}; Pfam {pfam_version}"
        for source_id in (f"PFAM:{observed_name}", f"PFAM:{accession}"):
            mapping_rows.append(
                {
                    "source_candidate_id": source_id,
                    "canonical_candidate_id": f"INTERPRO:{integrated}",
                    "relation": "EXACT",
                    "source": "InterPro/Pfam official integration",
                    "source_version": version,
                }
            )
        mapping_records.append(
            {
                "observed_candidate": f"PFAM:{observed_name}",
                "pfam_accession": accession,
                "pfam_name": pfam_names[accession],
                "interpro_accession": integrated,
                "verification_url": INTERPRO_ENTRY_URL.format(accession=accession),
            }
        )
    _write_tsv(
        output / "mappings.tsv",
        mapping_rows,
        [
            "source_candidate_id",
            "canonical_candidate_id",
            "relation",
            "source",
            "source_version",
        ],
    )

    manifest_rows = _read_tsv(args.uniprot_manifest)
    synonyms, synonym_review, excluded = _build_synonyms(manifest_rows, sources)
    _write_tsv(
        output / "synonyms.tsv",
        synonyms,
        ["normalized_label", "canonical_candidate_id", "source", "source_version"],
    )
    _write_tsv(
        output / "synonym_review.tsv",
        synonym_review,
        ["accession", "normalized_label", "canonical_candidate_id", "decision", "reason"],
    )

    config_text = (
        "fusion:\n"
        "  mapping_path: <BUNDLE_DIR>/mappings.tsv\n"
        "  synonym_path: <BUNDLE_DIR>/synonyms.tsv\n"
        "  # Replace <BUNDLE_DIR> with the absolute path after copying the bundle.\n"
    )
    (output / "fusion-config-snippet.yaml").write_text(config_text, encoding="utf-8")

    source_files = sorted(path for path in sources.iterdir() if path.is_file())
    source_manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "interpro_release": interpro_version,
        "pfam_release": pfam_version,
        "uniprot_release": sorted({row["source_release"] for row in manifest_rows}),
        "source_urls": {
            "pfam_name_table": PFAM_CLANS_URL,
            "interpro_release_notes": INTERPRO_RELEASE_URL,
            "interpro_entry_template": INTERPRO_ENTRY_URL,
            "uniprot_entry_template": UNIPROT_ENTRY_URL,
        },
        "observed_candidate_source": {
            "path": f"sources/{candidate_snapshot.name}",
            "sha256": _sha256(candidate_snapshot),
        },
        "reviewed_entry_manifest": {
            "path": f"sources/{reviewed_manifest_snapshot.name}",
            "sha256": _sha256(reviewed_manifest_snapshot),
        },
        "mapping_records": mapping_records,
        "source_files": [
            {"path": f"sources/{path.name}", "sha256": _sha256(path)} for path in source_files
        ],
        "excluded_synonym_count": len(excluded),
        "limitations": [
            "The mapping scope is the Pfam candidates observed in the characterized smoke run.",
            "EXACT denotes an official Pfam signature integrated into an InterPro entry.",
            "Synonyms contain only non-identical full alternative names from reviewed entries.",
            "Because reviewed entries were selected from the smoke set, synonyms "
            "must not be used as independent benchmark labels.",
        ],
    }
    (output / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "README.md").write_text(
        _readme(interpro_version, pfam_version, len(mapping_rows), len(synonyms)),
        encoding="utf-8",
    )
    _write_checksums(output)
    print(
        f"built {output}: {len(mapping_rows)} mappings, {len(synonyms)} synonyms, "
        f"{len(source_files)} source snapshots"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--uniprot-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with (
        urllib.request.urlopen(request, timeout=60) as response,
        destination.open("wb") as handle,
    ):
        shutil.copyfileobj(response, handle)


def _release_versions(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    interpro = re.search(r"Release ([0-9.]+),", text)
    pfam = re.search(r"^\s*Pfam\s+([0-9.]+)\s+", text, re.MULTILINE)
    if not interpro or not pfam:
        raise ValueError("could not parse InterPro/Pfam versions from release notes")
    return interpro.group(1), pfam.group(1)


def _observed_pfam_candidates(path: Path) -> set[str]:
    rows = _read_tsv(path)
    values = {
        row["candidate_id"].split(":", 1)[1] for row in rows if row.get("candidate_kind") == "PFAM"
    }
    if not values:
        raise ValueError(f"no PFAM candidates found in {path}")
    return values


def _load_pfam_names(path: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    by_name: dict[str, list[str]] = defaultdict(list)
    names: dict[str, str] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) != 5:
                raise ValueError(f"unexpected Pfam-A.clans row with {len(row)} fields")
            accession, _clan, _clan_name, short_name, description = row
            by_name[short_name].append(accession)
            names[accession] = description
    return by_name, names


def _build_synonyms(
    manifest_rows: list[dict[str, str]], sources: Path
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    proposed: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    review: list[dict[str, str]] = []
    excluded: list[str] = []
    for row in manifest_rows:
        accession = row["accession"]
        release = row["source_release"]
        destination = sources / f"uniprot-{accession}.json"
        _download(UNIPROT_ENTRY_URL.format(accession=accession), destination)
        record = json.loads(destination.read_text(encoding="utf-8"))
        if record.get("primaryAccession") != accession:
            raise ValueError(f"UniProt response accession mismatch for {accession}")
        description = record.get("proteinDescription", {})
        recommended = _full_name(description.get("recommendedName"))
        if not recommended:
            continue
        canonical = f"LABEL:{_normalize_label(recommended).replace(' ', '_')}"
        for alternative in description.get("alternativeNames", []):
            name = _full_name(alternative)
            if not name:
                continue
            normalized = _normalize_label(name)
            if normalized == _normalize_label(recommended):
                continue
            if len(normalized) < 8:
                excluded.append(normalized)
                review.append(
                    {
                        "accession": accession,
                        "normalized_label": normalized,
                        "canonical_candidate_id": canonical,
                        "decision": "EXCLUDED",
                        "reason": "alias is too short for safe global label matching",
                    }
                )
                continue
            proposed[normalized].append((canonical, accession, release))

    synonyms: list[dict[str, str]] = []
    for normalized, targets in sorted(proposed.items()):
        canonical_ids = {item[0] for item in targets}
        if len(canonical_ids) != 1:
            excluded.append(normalized)
            for canonical, accession, _release in targets:
                review.append(
                    {
                        "accession": accession,
                        "normalized_label": normalized,
                        "canonical_candidate_id": canonical,
                        "decision": "EXCLUDED",
                        "reason": "alias maps to more than one canonical label in this bundle",
                    }
                )
            continue
        canonical, accession, release = targets[0]
        synonyms.append(
            {
                "normalized_label": normalized,
                "canonical_candidate_id": canonical,
                "source": f"UniProtKB/Swiss-Prot {accession} full alternative name",
                "source_version": release,
            }
        )
        review.append(
            {
                "accession": accession,
                "normalized_label": normalized,
                "canonical_candidate_id": canonical,
                "decision": "ACCEPTED",
                "reason": "non-identical full alternative name in reviewed UniProtKB entry",
            }
        )
    return synonyms, review, excluded


def _full_name(name_block: Any) -> str | None:
    if not isinstance(name_block, dict):
        return None
    full_name = name_block.get("fullName")
    if isinstance(full_name, dict) and isinstance(full_name.get("value"), str):
        return full_name["value"].strip()
    return None


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_checksums(output: Path) -> None:
    checksum_path = output / "CHECKSUMS.sha256"
    files = sorted(path for path in output.rglob("*") if path.is_file() and path != checksum_path)
    checksum_path.write_text(
        "".join(f"{_sha256(path)}  {path.relative_to(output)}\n" for path in files),
        encoding="utf-8",
    )


def _readme(interpro: str, pfam: str, mapping_count: int, synonym_count: int) -> str:
    return f"""# DualRAG Phase 2 mapping bundle

Built from InterPro {interpro}, Pfam {pfam}, and reviewed UniProtKB/Swiss-Prot records.

- `mappings.tsv`: {mapping_count} source-ID rows covering name and accession forms.
- `synonyms.tsv`: {synonym_count} source-curated full-name aliases.
- `synonym_review.tsv`: accepted and excluded synonym decisions.
- `source_manifest.json`: versions, URLs, source checksums, and limitations.
- `sources/`: exact official source snapshots used by the builder.
- `fusion-config-snippet.yaml`: configuration keys to copy into a run profile.

`EXACT` means the Pfam member signature is officially integrated into the stated
InterPro entry. It does not imply that all parent/child ontology concepts are identical.

The synonym subset was derived from the selected characterized proteins and must not be
treated as independent benchmark truth. It is suitable for smoke/integration testing;
build a benchmark-independent synonym release before Phase 3 evaluation.
"""


if __name__ == "__main__":
    raise SystemExit(main())
