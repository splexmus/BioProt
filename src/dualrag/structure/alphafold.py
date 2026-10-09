from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

from dualrag.config import AlphaFoldApiConfig
from dualrag.io import file_sha256
from dualrag.models import ProteinQuery

_UNIPROT = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9])|A0A[A-Z0-9]{7})(?:-\d+)?$"
)


@dataclass(frozen=True)
class AcquisitionRecord:
    query_id: str
    requested_uniprot_accession: str | None
    resolution_method: str
    api_base_url: str
    request_url: str | None
    http_status: int | None
    alphafold_entry_id: str | None
    model_version: str | None
    structure_format: str
    source_structure_url: str | None
    retrieved_at: str
    sha256: str | None
    cache_path: str | None
    status: str
    sequence_compatible: bool | None

    def to_row(self) -> dict[str, object]:
        return asdict(self)


def resolve_accession(query: ProteinQuery) -> tuple[str | None, str]:
    token = query.query_id.split()[0]
    pipe = re.match(r"^(?:sp|tr)\|([^|]+)\|", token)
    if pipe and _UNIPROT.fullmatch(pipe.group(1)):
        return pipe.group(1), "fasta_uniprot_pipe"
    if _UNIPROT.fullmatch(token):
        return token, "validated_query_id"
    return None, "unresolved"


def acquire_models(
    queries: list[ProteinQuery],
    cache_dir: Path,
    raw_dir: Path,
    config: AlphaFoldApiConfig,
    session: requests.Session | None = None,
) -> tuple[dict[str, Path], list[AcquisitionRecord]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    models: dict[str, Path] = {}
    records: list[AcquisitionRecord] = []
    for index, query in enumerate(queries):
        accession, method = resolve_accession(query)
        if accession is None:
            records.append(_unresolved(query, method, config))
            continue
        model, record = _acquire_one(query, accession, method, cache_dir, raw_dir, config, client)
        records.append(record)
        if model is not None:
            models[query.query_id] = model
        if index + 1 < len(queries) and config.request_interval_seconds:
            time.sleep(config.request_interval_seconds)
    return models, records


def _acquire_one(
    query: ProteinQuery,
    accession: str,
    method: str,
    cache_dir: Path,
    raw_dir: Path,
    config: AlphaFoldApiConfig,
    session: requests.Session,
) -> tuple[Path | None, AcquisitionRecord]:
    suffix = ".cif" if config.structure_format == "cif" else ".pdb"
    model_path = cache_dir / f"{accession}{suffix}"
    cache_metadata = cache_dir / f"{accession}.metadata.json"
    request_url = f"{config.base_url.rstrip('/')}/prediction/{accession}"
    retrieved_at = datetime.now(UTC).isoformat()
    if model_path.is_file() and cache_metadata.is_file():
        payload = json.loads(cache_metadata.read_text(encoding="utf-8"))
        shutil.copyfile(cache_metadata, raw_dir / f"{_safe_file_id(query.query_id)}.metadata.json")
        entry = _first_entry(payload)
        compatible = _sequence_compatible(query.sequence, entry)
        if compatible is False:
            raise ValueError(f"cached AlphaFold sequence does not match query {query.query_id}")
        return model_path, _record(
            query, accession, method, config, request_url, None, entry, model_path,
            "CACHED", retrieved_at, compatible
        )

    response = _get_with_retries(session, request_url, config)
    if response is None:
        return None, _error_record(
            query, accession, method, config, request_url, None, retrieved_at
        )
    if response.status_code == 404:
        return None, _status_record(
            query, accession, method, config, request_url, 404, "NOT_FOUND", retrieved_at
        )
    if response.status_code != 200:
        return None, _error_record(
            query, accession, method, config, request_url, response.status_code, retrieved_at
        )
    payload = response.json()
    (raw_dir / f"{_safe_file_id(query.query_id)}.metadata.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    entry = _first_entry(payload)
    returned_accession = entry.get("uniprotAccession")
    if returned_accession and returned_accession != accession:
        raise ValueError(f"AlphaFold returned {returned_accession!r} for requested {accession!r}")
    compatible = _sequence_compatible(query.sequence, entry)
    if compatible is False:
        raise ValueError(f"AlphaFold sequence does not match query {query.query_id}")
    structure_url = _structure_url(entry, config.structure_format)
    structure_response = _get_with_retries(session, structure_url, config)
    if structure_response is None or structure_response.status_code != 200:
        status = structure_response.status_code if structure_response is not None else None
        return None, _entry_error_record(
            query, accession, method, config, request_url, status, retrieved_at, entry
        )
    temporary = model_path.with_suffix(model_path.suffix + ".part")
    temporary.write_bytes(structure_response.content)
    temporary.replace(model_path)
    cache_metadata.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return model_path, _record(
        query, accession, method, config, request_url, 200, entry, model_path,
        "DOWNLOADED", retrieved_at, compatible
    )


def _first_entry(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    if isinstance(payload, dict):
        return payload
    raise ValueError("AlphaFold metadata response contains no entry")


def _structure_url(entry: dict[str, Any], structure_format: str) -> str:
    key = "cifUrl" if structure_format == "cif" else "pdbUrl"
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"AlphaFold metadata is missing {key}")
    return value


def _sequence_compatible(sequence: str, entry: dict[str, Any]) -> bool | None:
    returned = entry.get("uniprotSequence")
    if not isinstance(returned, str) or not returned:
        return None
    return returned.upper() == sequence.upper()


def _safe_file_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", value)
    return f"query_{safe}" if safe in {"", ".", ".."} else safe


def _get_with_retries(
    session: requests.Session, url: str, config: AlphaFoldApiConfig
) -> requests.Response | None:
    response: requests.Response | None = None
    for attempt in range(config.max_retries + 1):
        try:
            response = session.get(url, timeout=config.timeout_seconds)
        except requests.RequestException:
            response = None
        else:
            if response.status_code != 429 and response.status_code < 500:
                return response
        if attempt < config.max_retries and config.backoff_seconds:
            time.sleep(config.backoff_seconds * (2**attempt))
    return response


def _record(
    query: ProteinQuery, accession: str, method: str, config: AlphaFoldApiConfig,
    request_url: str, http_status: int | None, entry: dict[str, Any], model_path: Path,
    status: str, retrieved_at: str, compatible: bool | None,
) -> AcquisitionRecord:
    return AcquisitionRecord(
        query.query_id, accession, method, config.base_url, request_url, http_status,
        entry.get("entryId"),
        str(entry.get("latestVersion")) if entry.get("latestVersion") else None,
        config.structure_format, _structure_url(entry, config.structure_format), retrieved_at,
        file_sha256(model_path), str(model_path), status, compatible,
    )


def _unresolved(query: ProteinQuery, method: str, config: AlphaFoldApiConfig) -> AcquisitionRecord:
    return AcquisitionRecord(
        query.query_id, None, method, config.base_url, None, None, None, None,
        config.structure_format, None, datetime.now(UTC).isoformat(), None, None,
        "ACCESSION_UNRESOLVED", None,
    )


def _status_record(
    query: ProteinQuery, accession: str, method: str, config: AlphaFoldApiConfig,
    request_url: str, http_status: int | None, status: str, retrieved_at: str,
) -> AcquisitionRecord:
    return AcquisitionRecord(
        query.query_id, accession, method, config.base_url, request_url, http_status, None, None,
        config.structure_format, None, retrieved_at, None, None, status, None,
    )


def _error_record(
    query: ProteinQuery, accession: str, method: str, config: AlphaFoldApiConfig,
    request_url: str, http_status: int | None, retrieved_at: str,
) -> AcquisitionRecord:
    return _status_record(
        query, accession, method, config, request_url, http_status, "HTTP_ERROR", retrieved_at
    )


def _entry_error_record(
    query: ProteinQuery,
    accession: str,
    method: str,
    config: AlphaFoldApiConfig,
    request_url: str,
    http_status: int | None,
    retrieved_at: str,
    entry: dict[str, Any],
) -> AcquisitionRecord:
    return AcquisitionRecord(
        query.query_id,
        accession,
        method,
        config.base_url,
        request_url,
        http_status,
        entry.get("entryId"),
        str(entry.get("latestVersion")) if entry.get("latestVersion") else None,
        config.structure_format,
        _structure_url(entry, config.structure_format),
        retrieved_at,
        None,
        None,
        "HTTP_ERROR",
        _sequence_compatible(query.sequence, entry),
    )
