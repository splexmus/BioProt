#!/usr/bin/env python3
"""Download official InterPro/Pfam snapshots and build full exact ID mappings."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

INTERPRO_XML_URL = (
    "https://ftp.ebi.ac.uk/pub/databases/interpro/releases/111.0/interpro.xml.gz"
)
INTERPRO_RELEASE_URL = (
    "https://ftp.ebi.ac.uk/pub/databases/interpro/releases/111.0/release_notes.txt"
)
PFAM_CLANS_URL = (
    "https://ftp.ebi.ac.uk/pub/databases/Pfam/releases/Pfam39.0/Pfam-A.clans.tsv.gz"
)
USER_AGENT = "BioProt-InterPro-mapping-builder/1.0 (+research reproducibility)"
MAPPING_FIELDS = [
    "source_candidate_id",
    "canonical_candidate_id",
    "relation",
    "source",
    "source_version",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _download(url: str, destination: Path) -> None:
    part = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, part.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        part.replace(destination)
    except Exception:
        part.unlink(missing_ok=True)
        raise


def _pfam_names(path: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) != 5:
                raise ValueError(f"unexpected Pfam-A.clans row with {len(row)} fields")
            accession, _clan, _clan_name, short_name, _description = row
            names[accession] = short_name
    if not names:
        raise ValueError(f"no Pfam families found in {path}")
    return names


def _interpro_integrations(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    integrations: dict[str, str] = {}
    versions: dict[str, str] = {}
    with gzip.open(path, "rb") as handle:
        for _event, element in ET.iterparse(handle, events=("end",)):
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "dbinfo":
                versions[element.attrib.get("dbname", "").upper()] = element.attrib.get(
                    "version", "unknown"
                )
            if tag != "interpro":
                continue
            interpro_id = element.attrib.get("id", "")
            for member_list in element:
                if member_list.tag.rsplit("}", 1)[-1] != "member_list":
                    continue
                for member in member_list:
                    if (
                        member.tag.rsplit("}", 1)[-1] != "db_xref"
                        or member.attrib.get("db", "").upper() != "PFAM"
                    ):
                        continue
                    accession = member.attrib.get("dbkey", "")
                    prior = integrations.setdefault(accession, interpro_id)
                    if prior != interpro_id:
                        raise ValueError(
                            f"Pfam accession {accession} maps to both {prior} and {interpro_id}"
                        )
            element.clear()
    if not integrations:
        raise ValueError(f"no Pfam-to-InterPro integrations found in {path}")
    return integrations, versions


def _mapping_rows(
    integrations: dict[str, str], names: dict[str, str], source_version: str
) -> tuple[list[dict[str, str]], list[str]]:
    proposed: dict[str, set[str]] = defaultdict(set)
    for accession, interpro_id in integrations.items():
        proposed[f"PFAM:{accession}"].add(f"INTERPRO:{interpro_id}")
        if name := names.get(accession):
            proposed[f"PFAM:{name}"].add(f"INTERPRO:{interpro_id}")
    ambiguous = sorted(source for source, targets in proposed.items() if len(targets) != 1)
    rows = [
        {
            "source_candidate_id": source,
            "canonical_candidate_id": next(iter(targets)),
            "relation": "EXACT",
            "source": "InterPro/Pfam official integration",
            "source_version": source_version,
        }
        for source, targets in sorted(proposed.items())
        if len(targets) == 1
    ]
    return rows, ambiguous


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


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty output directory: {output}")
    sources = output / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    resources = {
        "interpro_xml": (INTERPRO_XML_URL, sources / "interpro.xml.gz"),
        "interpro_release_notes": (
            INTERPRO_RELEASE_URL,
            sources / "interpro-release-notes.txt",
        ),
        "pfam_clans": (PFAM_CLANS_URL, sources / "Pfam-A.clans.tsv.gz"),
    }
    for url, destination in resources.values():
        _download(url, destination)

    integrations, versions = _interpro_integrations(resources["interpro_xml"][1])
    pfam_names = _pfam_names(resources["pfam_clans"][1])
    interpro_version = versions.get("INTERPRO", "unknown")
    pfam_version = versions.get("PFAM", "unknown")
    source_version = f"InterPro {interpro_version}; Pfam {pfam_version}"
    rows, ambiguous = _mapping_rows(integrations, pfam_names, source_version)
    with (output / "mappings.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=MAPPING_FIELDS,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "interpro_release": interpro_version,
        "pfam_release": pfam_version,
        "integrated_pfam_accession_count": len(integrations),
        "mapping_row_count": len(rows),
        "ambiguous_name_count": len(ambiguous),
        "ambiguous_names": ambiguous,
        "resources": {
            name: {
                "url": url,
                "path": str(path.relative_to(output)),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for name, (url, path) in resources.items()
        },
        "limitations": [
            "EXACT means a Pfam signature is officially integrated into an InterPro entry.",
            "Domain identity does not establish complete-protein function identity.",
            "Ambiguous Pfam short names are excluded; accession mappings remain authoritative.",
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "README.md").write_text(
        f"""# BioProt InterPro/Pfam mapping bundle

Official, release-pinned exact mappings built from InterPro {interpro_version} and
Pfam {pfam_version}. `mappings.tsv` contains {len(rows):,} accession/name mappings for
{len(integrations):,} integrated Pfam signatures. These mappings support domain-level
partial consensus; they do not prove complete-protein function equivalence.
""",
        encoding="utf-8",
    )
    _write_checksums(output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
