from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dualrag.io import file_sha256, write_json
from dualrag.literature.io import read_jsonl
from dualrag.literature.schemas import LiteratureChunk

INDEX_VERSION = "sqlite-char3-v1"


def build_literature_index(
    *, chunks_path: Path, index_path: Path, replace: bool = False
) -> dict[str, Any]:
    """Build an atomic, persistent chunk/vector index without changing source artifacts."""
    if index_path.exists() and not replace:
        raise FileExistsError(f"index already exists: {index_path}; pass --replace to rebuild")
    chunks = read_jsonl(chunks_path, LiteratureChunk)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = index_path.with_name(f".{index_path.name}.tmp-{os.getpid()}")
    if temporary.exists():
        temporary.unlink()
    try:
        with sqlite3.connect(temporary) as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = DELETE;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE chunks (
                    chunk_id TEXT PRIMARY KEY,
                    pmid TEXT,
                    payload_json TEXT NOT NULL,
                    vector_json TEXT NOT NULL
                );
                CREATE INDEX chunks_pmid_idx ON chunks(pmid);
                """
            )
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                [
                    ("index_version", INDEX_VERSION),
                    ("source_sha256", file_sha256(chunks_path)),
                    ("chunk_count", str(len(chunks))),
                ],
            )
            connection.executemany(
                "INSERT INTO chunks(chunk_id, pmid, payload_json, vector_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    (
                        chunk.chunk_id,
                        chunk.pmid,
                        chunk.model_dump_json(),
                        json.dumps(_chargram_counts(chunk.text), sort_keys=True),
                    )
                    for chunk in chunks
                ),
            )
        os.replace(temporary, index_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    now = datetime.now(UTC)
    manifest = {
        "schema_version": 1,
        "index_version": INDEX_VERSION,
        "created_at": now.isoformat(),
        "chunk_count": len(chunks),
        "vector_feature": "case-folded character trigrams with exact cosine search",
        "source": {"path": str(chunks_path), "sha256": file_sha256(chunks_path)},
        "index": {"path": str(index_path), "sha256": file_sha256(index_path)},
        "scientific_warning": (
            "This deterministic baseline is not a semantic protein-language embedding and "
            "must be evaluated before replacing the frozen Phase 4 retriever."
        ),
    }
    write_json(index_path.with_suffix(index_path.suffix + ".manifest.json"), manifest)
    return manifest


def read_literature_index(
    index_path: Path, *, allowed_pmids: set[str] | None = None
) -> tuple[list[LiteratureChunk], dict[str, Counter[str]], dict[str, str]]:
    """Read validated chunks and their stored vectors from a local index."""
    if not index_path.is_file():
        raise FileNotFoundError(index_path)
    with sqlite3.connect(f"file:{index_path}?mode=ro", uri=True) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if metadata.get("index_version") != INDEX_VERSION:
            raise ValueError(
                f"unsupported literature index version: {metadata.get('index_version')!r}"
            )
        if allowed_pmids is None:
            rows = connection.execute("SELECT payload_json, vector_json FROM chunks")
        elif not allowed_pmids:
            return [], {}, metadata
        else:
            placeholders = ",".join("?" for _ in allowed_pmids)
            rows = connection.execute(
                f"SELECT payload_json, vector_json FROM chunks WHERE pmid IN ({placeholders})",
                sorted(allowed_pmids),
            )
        chunks: list[LiteratureChunk] = []
        vectors: dict[str, Counter[str]] = {}
        for payload_json, vector_json in rows:
            chunk = LiteratureChunk.model_validate_json(payload_json)
            chunks.append(chunk)
            vectors[chunk.chunk_id] = Counter(json.loads(vector_json))
    return chunks, vectors, metadata


def _chargram_counts(text: str) -> Counter[str]:
    import re

    value = re.sub(r"\s+", " ", text.casefold())
    return Counter(value[index : index + 3] for index in range(max(len(value) - 2, 0)))
