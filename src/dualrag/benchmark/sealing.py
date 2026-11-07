from __future__ import annotations

import csv
import json
import os
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from dualrag.benchmark.dataset import _sha256_file, _write_tsv

BLINDED_COPY_FILES = (
    "queries.fasta",
    "queries.tsv",
    "domain_labels.tsv",
    "exposed_queries.tsv",
    "exclusion_ledger.tsv",
    "cluster_membership.tsv",
    "splits.tsv",
    "prohibited_targets.tsv",
    "difficulty_strata.tsv",
    "reference_alignments.tsv",
    "source_manifest.json",
)


def seal_test_labels(
    *, source_dir: Path, blinded_dir: Path, vault_dir: Path
) -> dict[str, object]:
    """Create a pipeline view without test gold and a separately permissioned test vault."""
    if blinded_dir.exists():
        raise FileExistsError(f"blinded output already exists: {blinded_dir}")
    if vault_dir.exists():
        raise FileExistsError(f"test-label vault already exists: {vault_dir}")
    gold_path = source_dir / "gold_labels.tsv"
    splits_path = source_dir / "splits.tsv"
    if not gold_path.is_file() or not splits_path.is_file():
        raise FileNotFoundError("source dataset requires gold_labels.tsv and splits.tsv")
    split_rows = _read_tsv(splits_path)
    split_by_accession = {row["accession"]: row["split"] for row in split_rows}
    gold_rows = _read_tsv(gold_path)
    if not gold_rows:
        raise ValueError("gold_labels.tsv contains no rows")
    fieldnames = list(gold_rows[0])
    for row in gold_rows:
        expected = split_by_accession.get(row["accession"])
        if expected is None:
            raise ValueError(f"gold accession absent from splits.tsv: {row['accession']}")
        if row.get("split") != expected:
            raise ValueError(f"gold split mismatch for {row['accession']}")
    test_rows = [row for row in gold_rows if row["split"] == "test"]
    pipeline_rows = [row for row in gold_rows if row["split"] != "test"]
    if not test_rows:
        raise ValueError("gold_labels.tsv contains no test rows")

    blinded_dir.mkdir(parents=True)
    vault_dir.mkdir(parents=True)
    for name in BLINDED_COPY_FILES:
        source = source_dir / name
        if not source.is_file():
            raise FileNotFoundError(f"source dataset artifact is missing: {source}")
        shutil.copy2(source, blinded_dir / name)
    _write_tsv(blinded_dir / "gold_labels.tsv", fieldnames, pipeline_rows)
    _write_tsv(vault_dir / "test_gold_labels.tsv", fieldnames, test_rows)

    test_accessions = sorted({row["accession"] for row in test_rows})
    pipeline_accessions = sorted({row["accession"] for row in pipeline_rows})
    test_gold_sha256 = _sha256_file(vault_dir / "test_gold_labels.tsv")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "seal_id": f"{source_dir.name}-test-gold-seal-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "source_dataset": str(source_dir),
        "source_gold_labels_sha256": _sha256_file(gold_path),
        "blinded_dataset": str(blinded_dir),
        "vault": str(vault_dir),
        "test_gold_labels_sha256": test_gold_sha256,
        "pipeline_gold_splits": ["development", "validation"],
        "pipeline_gold_label_row_count": len(pipeline_rows),
        "pipeline_gold_accession_count": len(pipeline_accessions),
        "sealed_test_gold_label_row_count": len(test_rows),
        "sealed_test_accession_count": len(test_accessions),
        "sealed_test_namespace_counts": dict(
            sorted(Counter(row["namespace"] for row in test_rows).items())
        ),
        "pipeline_contains_test_gold": False,
        "seal_type": "PROCEDURAL_FILESYSTEM_SEPARATION",
        "confirmatory_blinding_status": "NOT_HISTORICALLY_UNTOUCHED",
        "limitations": [
            "The full source gold file existed before this procedural seal.",
            "Filesystem permissions prevent accidental pipeline access, not access by the owner.",
            "Query accessions and protein names remain in queries.tsv for retrieval provenance.",
            "Freeze code, model, prompts, mappings, and thresholds before using sealed test gold.",
        ],
    }
    (blinded_dir / "test_label_seal_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (vault_dir / "test_label_seal_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_checksums(blinded_dir)
    _write_checksums(vault_dir)
    os.chmod(vault_dir, 0o700)
    for path in vault_dir.iterdir():
        if path.is_file():
            os.chmod(path, 0o600)
    return manifest


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_checksums(directory: Path) -> None:
    paths = sorted(
        path for path in directory.iterdir() if path.is_file() and path.name != "CHECKSUMS.sha256"
    )
    (directory / "CHECKSUMS.sha256").write_text(
        "\n".join(f"{_sha256_file(path)}  {path.name}" for path in paths) + "\n",
        encoding="utf-8",
    )

