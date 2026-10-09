from __future__ import annotations

import shutil
from datetime import UTC, datetime

import yaml

from dualrag.config import AppConfig


def initialize_storage(config: AppConfig) -> dict[str, object]:
    """Create the external-data layout without downloading or overwriting databases."""
    root = config.paths.data_root.resolve()
    directories = [
        root / "databases" / "eggnog",
        root / "databases" / "foldseek",
        root / "databases" / "metadata",
        root / "structures" / "alphafold",
        root / "datasets" / "raw",
        root / "datasets" / "curated",
        root / "datasets" / "manifests",
        root / "experiments",
        config.paths.tmp_dir.resolve(),
        config.paths.results_dir.resolve(),
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    target_metadata_created = False
    if (
        config.structure.target_metadata is not None
        and not config.structure.target_metadata.exists()
    ):
        config.structure.target_metadata.parent.mkdir(parents=True, exist_ok=True)
        config.structure.target_metadata.write_text(
            "target_structure_id\ttarget_uniprot_id\tprotein_name\tinterpro_ids\t"
            "supfam_ids\tstructure_source\texperimental_structure\tsource_accession\n",
            encoding="utf-8",
        )
        target_metadata_created = True

    usage = shutil.disk_usage(root)
    manifest_path = root / "databases" / "metadata" / "databases.yaml"
    created_manifest = False
    if not manifest_path.exists():
        payload = {
            "eggnog": {
                "version": None,
                "downloaded_at": None,
                "path": str(config.sequence.eggnog_data_dir),
                "notes": "Populate with a version compatible with the configured executable",
            },
            "foldseek": {
                "version": None,
                "downloaded_at": None,
                "path": str(config.structure.foldseek_db),
                "notes": "Populate with the configured, versioned Foldseek target database",
            },
            "alphafold_api": {
                "base_url": config.structure.alphafold_api.base_url,
                "accessed_at": None,
                "notes": "Remote query models only; bounded local cache",
            },
        }
        manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        created_manifest = True
    return {
        "data_root": str(root),
        "capacity_bytes": usage.total,
        "free_bytes": usage.free,
        "initialized_at": datetime.now(UTC).isoformat(),
        "manifest_path": str(manifest_path),
        "manifest_created": created_manifest,
        "target_metadata_created": target_metadata_created,
    }
