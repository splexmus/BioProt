from __future__ import annotations

import platform
import shlex
import sys
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime
from pathlib import Path

import yaml

from dualrag import __version__
from dualrag.config import AppConfig
from dualrag.fasta import read_fasta
from dualrag.fusion.merge import merge_evidence
from dualrag.fusion.scoring import CONFLICT_FIELDS, fuse_candidates
from dualrag.io import file_sha256, stable_hash, write_json, write_tsv
from dualrag.models import FunctionCandidate, SequenceEvidence, StructureEvidence
from dualrag.normalization.sequence import normalize as normalize_sequence
from dualrag.normalization.structure import normalize as normalize_structure
from dualrag.sequence.eggnog import retrieve as retrieve_sequence_eggnog
from dualrag.sequence.fixture import retrieve as retrieve_sequence_fixture
from dualrag.structure.alphafold import AcquisitionRecord, acquire_models
from dualrag.structure.fixture import retrieve as retrieve_structure_fixture
from dualrag.structure.foldseek import retrieve as retrieve_structure_foldseek


def run_pipeline(config: AppConfig, input_path: Path, output_dir: Path) -> dict[str, object]:
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    queries = read_fasta(input_path)
    config_dump = config.model_dump(mode="json")
    parameters_hash = stable_hash(config_dump)
    run_id = stable_hash({"input_sha256": file_sha256(input_path), "config": config_dump})[:16]

    commands: list[str] = []
    acquisition_records: list[AcquisitionRecord] = []
    if config.sequence.backend == "fixture":
        assert config.sequence.fixture_results is not None
        sequence_raw = raw_dir / "sequence_hits.tsv"
        sequence_hits = retrieve_sequence_fixture(
            queries, config.sequence.fixture_results, sequence_raw, config.sequence.top_k
        )
        commands.append(
            f"fixture-sequence --input {input_path} --source {config.sequence.fixture_results}"
        )
        _validate_database_provenance(
            "sequence",
            [(hit.database, hit.database_version) for hit in sequence_hits],
            config.sequence.database_name,
            config.sequence.database_version,
        )
    else:
        _validate_external_config(config.sequence.database_version, "sequence.database_version")
        assert config.sequence.eggnog_data_dir is not None
        if not config.sequence.eggnog_data_dir.is_dir():
            raise FileNotFoundError(
                f"eggNOG data directory does not exist: {config.sequence.eggnog_data_dir}"
            )
        sequence_hits, command = retrieve_sequence_eggnog(
            queries, input_path, raw_dir / "eggnog", config.sequence
        )
        commands.append(shlex.join(command))

    if config.structure.backend == "fixture":
        assert config.structure.fixture_results is not None
        structure_raw = raw_dir / "structure_hits.tsv"
        structure_hits = retrieve_structure_fixture(
            queries, config.structure.fixture_results, structure_raw, config.structure.top_k
        )
        commands.append(
            f"fixture-structure --input {input_path} --source {config.structure.fixture_results}"
        )
        _validate_database_provenance(
            "structure",
            [(hit.database, hit.database_version) for hit in structure_hits],
            config.structure.database_name,
            config.structure.database_version,
        )
    else:
        _validate_external_config(config.structure.database_version, "structure.database_version")
        models, acquisition_records = acquire_models(
            queries,
            config.structure.alphafold_cache,
            raw_dir / "alphafold",
            config.structure.alphafold_api,
        )
        structure_hits, command = retrieve_structure_foldseek(
            queries, models, raw_dir / "foldseek", config.paths.tmp_dir / run_id, config.structure
        )
        if command:
            commands.append(shlex.join(command))
    for hit in sequence_hits:
        hit.parameters_hash = parameters_hash
        hit.run_id = run_id
        normalize_sequence(hit, config.normalization.sequence_version)
    for hit in structure_hits:
        hit.parameters_hash = parameters_hash
        hit.run_id = run_id
        normalize_structure(hit, config.normalization.structure_version)

    sequence_rows = [hit.to_row() for hit in sequence_hits]
    structure_rows = [hit.to_row() for hit in structure_hits]
    merged_rows = merge_evidence(queries, sequence_hits, structure_hits)
    fusion_result = (
        fuse_candidates(
            queries,
            sequence_hits,
            structure_hits,
            config.fusion,
            run_id=run_id,
            parameters_hash=parameters_hash,
        )
        if config.fusion.enabled
        else None
    )
    write_tsv(
        output_dir / "queries.tsv", [query.to_row() for query in queries], list(queries[0].to_row())
    )
    write_tsv(
        output_dir / "sequence_results.tsv",
        sequence_rows,
        _fields(sequence_rows, SequenceEvidence),
    )
    write_tsv(
        output_dir / "structure_results.tsv",
        structure_rows,
        _fields(structure_rows, StructureEvidence),
    )
    write_tsv(output_dir / "merged_results.tsv", merged_rows, _fields(merged_rows))
    if fusion_result is not None:
        candidate_rows = [candidate.to_row() for candidate in fusion_result.candidates]
        write_tsv(
            output_dir / "function_candidates.tsv",
            candidate_rows,
            _fields(candidate_rows, FunctionCandidate),
        )
        write_tsv(
            output_dir / "fusion_summary.tsv",
            fusion_result.summaries,
            _fields(fusion_result.summaries),
        )
        write_tsv(
            output_dir / "conflicts.tsv",
            fusion_result.conflicts,
            CONFLICT_FIELDS,
        )
    if config.structure.backend == "hybrid":
        write_tsv(
            output_dir / "alphafold_acquisition.tsv",
            [record.to_row() for record in acquisition_records],
            [item.name for item in dataclass_fields(AcquisitionRecord)],
        )
    (output_dir / "config.snapshot.yaml").write_text(
        yaml.safe_dump(config_dump, sort_keys=True), encoding="utf-8"
    )
    (output_dir / "commands.log").write_text("\n".join(commands) + "\n", encoding="utf-8")
    metadata: dict[str, object] = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "package_version": __version__,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "input_path": str(input_path),
        "input_sha256": file_sha256(input_path),
        "parameters_hash": parameters_hash,
        "sequence_backend": config.sequence.backend,
        "structure_backend": config.structure.backend,
        "synthetic_fixture_data": (
            config.sequence.backend == "fixture" or config.structure.backend == "fixture"
        ),
        "query_count": len(queries),
        "sequence_hit_count": len(sequence_hits),
        "structure_hit_count": len(structure_hits),
        "merged_row_count": len(merged_rows),
        "function_candidate_count": (
            len(fusion_result.candidates) if fusion_result is not None else 0
        ),
        "fusion_summary_count": (
            len(fusion_result.summaries) if fusion_result is not None else 0
        ),
        "conflict_count": len(fusion_result.conflicts) if fusion_result is not None else 0,
        "fusion_version": config.fusion.version if config.fusion.enabled else None,
        "fusion_statuses": (
            [row["cross_modal_status"] for row in fusion_result.summaries]
            if fusion_result is not None
            else []
        ),
        "alphafold_acquisition_statuses": [record.status for record in acquisition_records],
    }
    write_json(output_dir / "run_metadata.json", metadata)
    return metadata


def _fields(rows: list[dict[str, object]], fallback: type[object] | None = None) -> list[str]:
    if not rows:
        if fallback is None:
            raise ValueError("cannot derive a TSV schema from zero rows")
        return [item.name for item in dataclass_fields(fallback)]
    field_names: list[str] = []
    for row in rows:
        for key in row:
            if key not in field_names:
                field_names.append(key)
    return field_names


def _validate_database_provenance(
    modality: str,
    observed: list[tuple[str, str]],
    expected_name: str,
    expected_version: str,
) -> None:
    mismatches = sorted({item for item in observed if item != (expected_name, expected_version)})
    if mismatches:
        raise ValueError(
            f"{modality} fixture provenance does not match config: "
            f"expected {(expected_name, expected_version)!r}, observed {mismatches!r}"
        )


def _validate_external_config(value: str, field: str) -> None:
    if not value.strip() or value.startswith("REQUIRED_") or value == "UNVERIFIED":
        raise ValueError(f"{field} must contain a verified database version before external runs")
