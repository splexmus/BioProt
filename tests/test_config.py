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
