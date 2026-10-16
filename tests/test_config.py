from pathlib import Path

from dualrag.config import load_config

ROOT = Path(__file__).parents[1]


def test_production_example_uses_hybrid_storage_boundary() -> None:
    config = load_config(ROOT / "config" / "config.example.yaml")
    assert config.sequence.backend == "local"
    assert config.sequence.eggnog_data_dir is not None
    assert config.structure.backend == "hybrid"
    assert config.structure.foldseek_db is not None
    assert config.structure.alphafold_api.enabled is True
    assert config.structure.alphafold_api.base_url == "https://alphafold.ebi.ac.uk/api"


def test_alphafold_api_url_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("DUALRAG_ALPHAFOLD_API_URL", "https://afdb.example.test/api")
    config = load_config(ROOT / "config" / "config.yaml")
    assert config.structure.alphafold_api.base_url == "https://afdb.example.test/api"


def test_legacy_profile_was_retargeted_to_ext4_mount() -> None:
    config = load_config(ROOT / "config" / "my-passport.yaml")
    assert config.paths.data_root == Path("/media/splexmus/4TB_HDD1/dualrag")
    assert config.sequence.database_version == "UNVERIFIED"
    assert config.structure.foldseek_db == Path(
        "/media/splexmus/4TB_HDD1/dualrag/databases/foldseek/pdb"
    )


def test_4tb_hdd_profile_uses_ext4_mount() -> None:
    config = load_config(ROOT / "config" / "4tb-hdd.yaml")
    assert config.paths.data_root == Path("/media/splexmus/4TB_HDD1/dualrag")
    assert config.sequence.database_version == "5.0.2"
    assert config.structure.database_version == (
        "PDB 2025-01-01 (Foldseek commit 1815f0d76d7b5807e63b13f9d446dcef43c1f3b1)"
    )
    assert config.structure.foldseek_db == Path(
        "/media/splexmus/4TB_HDD1/dualrag/databases/foldseek/pdb"
    )
