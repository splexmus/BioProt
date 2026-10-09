from pathlib import Path

from dualrag.config import load_config
from dualrag.storage import initialize_storage

ROOT = Path(__file__).parents[1]


def test_initialize_storage_is_non_destructive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DUALRAG_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("DUALRAG_TMP", str(tmp_path / "data" / "tmp"))
    monkeypatch.setenv("DUALRAG_RESULTS", str(tmp_path / "data" / "results"))
    monkeypatch.setenv("EGGNOG_DATA_DIR", str(tmp_path / "data" / "databases" / "eggnog"))
    monkeypatch.setenv(
        "DUALRAG_FOLDSEEK_DB", str(tmp_path / "data" / "databases" / "foldseek" / "demo")
    )
    config = load_config(ROOT / "config" / "4tb-hdd.yaml")
    metadata = tmp_path / "data" / "databases" / "foldseek" / "demo_metadata.tsv"
    config = config.model_copy(
        update={"structure": config.structure.model_copy(update={"target_metadata": metadata})}
    )
    first = initialize_storage(config)
    assert metadata.read_text(encoding="utf-8").startswith("target_structure_id\t")
    manifest = Path(str(first["manifest_path"]))
    manifest.write_text("owner: user\n", encoding="utf-8")
    second = initialize_storage(config)
    assert second["manifest_created"] is False
    assert manifest.read_text(encoding="utf-8") == "owner: user\n"
