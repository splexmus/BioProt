from __future__ import annotations

import json
import os
import shutil
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import yaml

from dualrag.benchmark.dataset import (
    _capture_version,
    _read_cluster_tsv,
    _run,
    _sha256_file,
    build_leakage_outputs,
    is_eligible,
    parse_swissprot,
    select_balanced_entries,
)
from dualrag.benchmark.step3 import (
    Nomination,
    _cluster_command,
    _write_artifacts,
    _write_queries_fasta,
)
from dualrag.io import file_sha256, read_tsv, stable_hash, write_json


def build_fresh_validation_dataset(
    *,
    swissprot_dat: Path,
    swissprot_fasta: Path,
    exclude_dataset: Path | None = None,
    exclude_datasets: list[Path] | None = None,
    contract_path: Path,
    output_dir: Path,
    source_release: str,
    source_sha256: str,
    dataset_id: str = "phase6-fresh-validation-v1",
    size: int = 150,
    pool_size: int = 600,
    mmseqs_executable: str = "mmseqs",
) -> dict[str, object]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite validation dataset: {output_dir}")
    exclusion_sources = [*(exclude_datasets or [])]
    if exclude_dataset is not None:
        exclusion_sources.append(exclude_dataset)
    if not exclusion_sources:
        raise ValueError("at least one exclusion dataset is required")
    if _sha256_file(swissprot_dat) != source_sha256:
        raise ValueError("Swiss-Prot checksum does not match the declared release")
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    excluded_rows = [
        row
        for dataset in exclusion_sources
        for row in read_tsv(dataset / "queries.tsv")
    ]
    excluded_accessions = {row["accession"] for row in excluded_rows}
    excluded_checksums = {row["sequence_sha256"] for row in excluded_rows}
    minimum_length = int(contract["gold_standard"]["inclusion"]["minimum_length"])
    maximum_length = int(contract["gold_standard"]["inclusion"]["maximum_length"])
    seed = int(contract["random_seed"]) + 1000
    candidates = []
    target_checksums: dict[str, str] = {}
    for entry in parse_swissprot(swissprot_dat):
        target_checksums[entry.accession] = entry.sequence_sha256
        if (
            entry.accession not in excluded_accessions
            and entry.sequence_sha256 not in excluded_checksums
            and is_eligible(entry, minimum_length, maximum_length)
        ):
            candidates.append(entry)
    pool = select_balanced_entries(candidates, pool_size, seed)
    output_dir.mkdir(parents=True)
    combined = output_dir / "cluster-screen.fasta"
    with combined.open("w", encoding="utf-8") as handle:
        for row in excluded_rows:
            handle.write(f">excluded::{row['accession']}\n{row['canonical_sequence']}\n")
        for entry in pool:
            handle.write(f">candidate::{entry.accession}\n{entry.sequence}\n")
    prefix = output_dir / "cluster-screen"
    commands: list[str] = []
    _run(
        _cluster_command(
            mmseqs_executable,
            combined,
            prefix,
            output_dir / "tmp-cluster-screen",
        ),
        commands,
    )
    clusters = _read_cluster_tsv(Path(f"{prefix}_cluster.tsv"))
    independent_accessions = _independent_candidate_accessions(clusters)
    by_accession = {entry.accession: entry for entry in pool}
    independent = [by_accession[item] for item in independent_accessions if item in by_accession]
    selected = select_balanced_entries(independent, size, seed)
    if len(selected) != size:
        raise ValueError(
            f"requested {size} independent proteins but only {len(selected)} remained"
        )

    queries_fasta = output_dir / "queries.fasta"
    _write_queries_fasta(queries_fasta, selected)
    alignments = output_dir / "reference_alignments.tsv"
    search_command = [
        mmseqs_executable,
        "easy-search",
        str(queries_fasta),
        str(swissprot_fasta),
        str(alignments),
        str(output_dir / "tmp-reference-search"),
        "--format-output",
        "query,target,fident,qcov,tcov,evalue,bits",
        "--max-seqs",
        "1000",
        "-s",
        "7.5",
        "--cov-mode",
        "0",
        "-c",
        "0.70",
        "--threads",
        "1",
    ]
    _run(search_command, commands)
    prohibited, difficulty = build_leakage_outputs(
        alignments, selected, target_checksums, output_dir
    )
    nominations = [
        Nomination(entry.accession, "fresh-validation-selection", "reviewed", True)
        for entry in selected
    ]
    nominations_by_accession = defaultdict(list)
    for nomination in nominations:
        nominations_by_accession[nomination.accession].append(nomination)
    split_by_accession = {
        entry.accession: ("validation", entry.accession) for entry in selected
    }
    membership_rows = [
        {
            "cluster_representative": entry.accession,
            "accession": entry.accession,
            "split": "validation",
            "minimum_identity": "0.30",
            "minimum_query_coverage": "0.80",
            "minimum_target_coverage": "0.80",
            "seed": seed,
        }
        for entry in selected
    ]
    selected_by_accession = {entry.accession: entry for entry in selected}
    _write_artifacts(
        output_dir=output_dir,
        nominations=nominations,
        by_accession=nominations_by_accession,
        reviewed_accessions=set(selected_by_accession),
        exposed_accessions=set(),
        entries=selected_by_accession,
        reasons=dict.fromkeys(selected_by_accession, []),
        included=selected,
        split_by_accession=split_by_accession,
        membership_rows=membership_rows,
        prohibited=prohibited,
        difficulty=difficulty,
        source_release=source_release,
    )
    namespace_counts = Counter(
        label.namespace
        for entry in selected
        for label in entry.labels
        if label.admissible_for_primary
    )
    manifest: dict[str, object] = {
        "schema_version": 1,
        "dataset_id": dataset_id,
        "query_count": len(selected),
        "query_namespace_example_count": sum(
            len(
                {
                    label.namespace
                    for label in entry.labels
                    if label.admissible_for_primary
                }
            )
            for entry in selected
        ),
        "label_counts": dict(sorted(namespace_counts.items())),
        "excluded_datasets": [str(path) for path in exclusion_sources],
        "excluded_accession_count": len(excluded_accessions),
        "cluster_screen_pool_count": len(pool),
        "independent_pool_count": len(independent),
        "source_release": source_release,
        "source_sha256": source_sha256,
        "mmseqs_version": _capture_version(mmseqs_executable),
        "seed": seed,
        "claim_boundary": "procedurally separated prospective validation, not third-party blinding",
    }
    (output_dir / "fresh_validation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "commands.log").write_text("\n".join(commands) + "\n", encoding="utf-8")
    return manifest


def _independent_candidate_accessions(clusters: dict[str, list[str]]) -> list[str]:
    result: list[str] = []
    for members in clusters.values():
        if any(member.startswith("excluded::") for member in members):
            continue
        candidates = sorted(
            member.removeprefix("candidate::")
            for member in members
            if member.startswith("candidate::")
        )
        if candidates:
            result.append(candidates[0])
    return sorted(result)


def seal_fresh_validation_labels(
    *, source_dir: Path, pipeline_dir: Path, vault_dir: Path
) -> dict[str, object]:
    if pipeline_dir.exists() or vault_dir.exists():
        raise FileExistsError("pipeline or vault output already exists")
    gold = source_dir / "gold_labels.tsv"
    if not gold.is_file():
        raise FileNotFoundError(f"validation gold is missing: {gold}")
    pipeline_dir.mkdir(parents=True)
    vault_dir.mkdir(parents=True)
    for source in source_dir.iterdir():
        if source.is_file() and source.name != "gold_labels.tsv":
            shutil.copy2(source, pipeline_dir / source.name)
    shutil.copy2(gold, vault_dir / "validation_gold_labels.tsv")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "source_dataset": str(source_dir),
        "pipeline_dataset": str(pipeline_dir),
        "vault": str(vault_dir),
        "validation_gold_sha256": _sha256_file(gold),
        "pipeline_contains_gold": False,
        "seal_type": "PROCEDURAL_FILESYSTEM_SEPARATION",
        "historically_untouched": False,
        "claim_boundary": "builder accessed labels during cohort construction",
    }
    for directory in (pipeline_dir, vault_dir):
        (directory / "validation_label_seal_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    os.chmod(vault_dir, 0o700)
    for path in vault_dir.iterdir():
        if path.is_file():
            os.chmod(path, 0o600)
    return manifest


def freeze_fresh_validation_inputs(
    *,
    inputs: dict[str, Path],
    code_roots: list[Path],
    output_path: Path,
) -> dict[str, object]:
    """Record predictions and model inputs before validation gold is revealed."""
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite validation freeze: {output_path}")
    missing = [str(path) for path in inputs.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"freeze inputs are missing: {', '.join(missing)}")
    code_files = sorted(
        path
        for root in code_roots
        for path in root.rglob("*.py")
        if path.is_file()
    )
    code_hashes = {str(path): file_sha256(path) for path in code_files}
    manifest: dict[str, object] = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "PREDICTIONS_AND_MODELS_FROZEN_BEFORE_GOLD_REVEAL",
        "validation_gold_accessed": False,
        "test_gold_accessed": False,
        "inputs": {
            name: {"path": str(path), "sha256": file_sha256(path)}
            for name, path in sorted(inputs.items())
        },
        "code_tree_sha256": stable_hash(code_hashes),
        "code_file_count": len(code_hashes),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, manifest)
    return manifest
