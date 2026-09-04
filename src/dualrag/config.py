from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectConfig(BaseModel):
    name: str
    seed: int = 42


class PathsConfig(BaseModel):
    data_root: Path
    tmp_dir: Path
    results_dir: Path
    structures_dir: Path


class SequenceConfig(BaseModel):
    backend: Literal["fixture", "external"] = "fixture"
    fixture_results: Path | None = None
    eggnog_data_dir: Path | None = None
    mmseqs_db: Path | None = None
    database_name: str
    database_version: str
    top_k: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def fixture_path_required(self) -> SequenceConfig:
        if self.backend == "fixture" and self.fixture_results is None:
            raise ValueError("sequence.fixture_results is required for fixture backend")
        return self


class StructureConfig(BaseModel):
    backend: Literal["fixture", "external"] = "fixture"
    fixture_results: Path | None = None
    foldseek_db: Path | None = None
    alphafold_cache: Path
    database_name: str
    database_version: str
    top_k: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def fixture_path_required(self) -> StructureConfig:
        if self.backend == "fixture" and self.fixture_results is None:
            raise ValueError("structure.fixture_results is required for fixture backend")
        return self


class NormalizationConfig(BaseModel):
    sequence_version: str
    structure_version: str


class DisabledLayerConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False


class AppConfig(BaseModel):
    project: ProjectConfig
    paths: PathsConfig
    sequence: SequenceConfig
    structure: StructureConfig
    normalization: NormalizationConfig
    literature: DisabledLayerConfig
    llm: DisabledLayerConfig

    @model_validator(mode="after")
    def forbid_future_layers(self) -> AppConfig:
        if self.literature.enabled or self.llm.enabled:
            raise ValueError("literature and LLM layers are outside the Phase 1 proof of concept")
        return self


_PATH_FIELDS = {
    "paths": {"data_root", "tmp_dir", "results_dir", "structures_dir"},
    "sequence": {"fixture_results", "eggnog_data_dir", "mmseqs_db"},
    "structure": {"fixture_results", "foldseek_db", "alphafold_cache"},
}


def load_config(path: Path) -> AppConfig:
    config_path = path.resolve()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("configuration root must be a mapping")
    _apply_environment(payload)
    for section, keys in _PATH_FIELDS.items():
        for key in keys:
            value = payload.get(section, {}).get(key)
            if value and not Path(value).is_absolute():
                payload[section][key] = str((config_path.parent / value).resolve())
    return AppConfig.model_validate(payload)


def _apply_environment(payload: dict[str, object]) -> None:
    mapping = {
        "DUALRAG_DATA_ROOT": ("paths", "data_root"),
        "DUALRAG_TMP": ("paths", "tmp_dir"),
        "DUALRAG_RESULTS": ("paths", "results_dir"),
        "EGGNOG_DATA_DIR": ("sequence", "eggnog_data_dir"),
        "DUALRAG_FOLDSEEK_DB": ("structure", "foldseek_db"),
    }
    for env_name, (section, key) in mapping.items():
        if value := os.getenv(env_name):
            section_data = payload.setdefault(section, {})
            if not isinstance(section_data, dict):
                raise ValueError(f"configuration section {section!r} must be a mapping")
            section_data[key] = value
