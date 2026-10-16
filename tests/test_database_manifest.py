from pathlib import Path

import yaml

from dualrag.config import load_config

ROOT = Path(__file__).parents[1]


def test_finalized_database_manifest_matches_production_config() -> None:
    manifest = yaml.safe_load(
        (ROOT / "config/databases.4tb-hdd.yaml").read_text(encoding="utf-8")
    )
    config = load_config(ROOT / "config/4tb-hdd.yaml")

    assert manifest["schema_version"] == 1
    assert Path(manifest["data_root"]) == config.paths.data_root
    assert manifest["eggnog"]["version"] == config.sequence.database_version
    assert Path(manifest["eggnog"]["path"]) == config.sequence.eggnog_data_dir
    assert Path(manifest["foldseek_pdb"]["path"]) == config.structure.foldseek_db
    assert manifest["foldseek_pdb"]["foldseek_database_commit"] in (
        config.structure.database_version
    )
    assert Path(manifest["foldseek_target_metadata"]["path"]) == (
        config.structure.target_metadata
    )
    assert manifest["foldseek_target_metadata"]["target_count"] == 1_562_650
    assert manifest["alphafold_api"]["local_mirror"] is False
