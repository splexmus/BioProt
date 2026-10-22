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
    backend: Literal["fixture", "local"] = "fixture"
    fixture_results: Path | None = None
    eggnog_data_dir: Path | None = None
    mmseqs_db: Path | None = None
    database_name: str
    database_version: str
    top_k: int = Field(default=10, ge=1)
    executable: str = "emapper.py"
    cpu: int = Field(default=1, ge=1)
    search_mode: Literal["diamond", "mmseqs"] = "diamond"
    extra_args: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def fixture_path_required(self) -> SequenceConfig:
        if self.backend == "fixture" and self.fixture_results is None:
            raise ValueError("sequence.fixture_results is required for fixture backend")
        if self.backend == "local" and self.eggnog_data_dir is None:
            raise ValueError("sequence.eggnog_data_dir is required for local backend")
        return self


class AlphaFoldApiConfig(BaseModel):
    enabled: bool = False
    base_url: str = "https://alphafold.ebi.ac.uk/api"
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=3, ge=0)
    backoff_seconds: float = Field(default=1.0, ge=0)
    structure_format: Literal["cif", "pdb"] = "cif"
    request_interval_seconds: float = Field(default=0.2, ge=0)


class StructureConfig(BaseModel):
    backend: Literal["fixture", "hybrid"] = "fixture"
    fixture_results: Path | None = None
    foldseek_db: Path | None = None
    alphafold_cache: Path
    alphafold_api: AlphaFoldApiConfig = Field(default_factory=AlphaFoldApiConfig)
    database_name: str
    database_version: str
    top_k: int = Field(default=10, ge=1)
    executable: str = "foldseek"
    threads: int = Field(default=1, ge=1)
    sensitivity: float = Field(default=7.5, gt=0)
    target_metadata: Path | None = None
    extra_args: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def fixture_path_required(self) -> StructureConfig:
        if self.backend == "fixture" and self.fixture_results is None:
            raise ValueError("structure.fixture_results is required for fixture backend")
        if self.backend == "hybrid" and self.foldseek_db is None:
            raise ValueError("structure.foldseek_db is required for hybrid backend")
        if self.backend == "hybrid" and not self.alphafold_api.enabled:
            raise ValueError("structure.alphafold_api must be enabled for hybrid backend")
        return self


class NormalizationConfig(BaseModel):
    sequence_version: str
    structure_version: str


class FusionConfig(BaseModel):
    enabled: bool = True
    version: str = "fixed-weight-v1"
    sequence_weight: float = Field(default=0.4, ge=0, le=1)
    structure_weight: float = Field(default=0.4, ge=0, le=1)
    agreement_weight: float = Field(default=0.2, ge=0, le=1)
    mapping_path: Path | None = None
    synonym_path: Path | None = None
    rerank_version: str = "evidence-quality-v1"
    base_score_weight: float = Field(default=0.8, ge=0, le=1)
    quality_weight: float = Field(default=0.2, ge=0, le=1)
    conflict_report_top_k: int = Field(default=5, ge=1)
    alternatives_top_k: int = Field(default=5, ge=1)
    ambiguity_margin: float = Field(default=0.05, ge=0, le=1)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> FusionConfig:
        total = self.sequence_weight + self.structure_weight + self.agreement_weight
        if abs(total - 1.0) > 1e-9:
            raise ValueError("fusion weights must sum to 1.0")
        rerank_total = self.base_score_weight + self.quality_weight
        if abs(rerank_total - 1.0) > 1e-9:
            raise ValueError("fusion rerank weights must sum to 1.0")
        return self


class DisabledLayerConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False


class AppConfig(BaseModel):
    project: ProjectConfig
    paths: PathsConfig
    sequence: SequenceConfig
    structure: StructureConfig
    normalization: NormalizationConfig
    fusion: FusionConfig = Field(default_factory=FusionConfig)
    literature: DisabledLayerConfig
    llm: DisabledLayerConfig

    @model_validator(mode="after")
    def forbid_future_layers(self) -> AppConfig:
        if self.literature.enabled or self.llm.enabled:
            raise ValueError("literature and LLM layers are outside the Phase 2 baseline")
        return self


_PATH_FIELDS = {
    "paths": {"data_root", "tmp_dir", "results_dir", "structures_dir"},
    "sequence": {"fixture_results", "eggnog_data_dir", "mmseqs_db"},
    "structure": {"fixture_results", "foldseek_db", "alphafold_cache", "target_metadata"},
    "fusion": {"mapping_path", "synonym_path"},
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

    if value := os.getenv("DUALRAG_ALPHAFOLD_API_URL"):
        structure_data = payload.setdefault("structure", {})
        if not isinstance(structure_data, dict):
            raise ValueError("configuration section 'structure' must be a mapping")
        api_data = structure_data.setdefault("alphafold_api", {})
        if not isinstance(api_data, dict):
            raise ValueError("configuration field 'structure.alphafold_api' must be a mapping")
        api_data["base_url"] = value
