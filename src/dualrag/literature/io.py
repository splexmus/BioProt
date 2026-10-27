from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def read_jsonl(path: Path, model: type[T]) -> list[T]:
    records: list[T] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    records.append(model.model_validate_json(line))
                except ValueError as exc:
                    raise ValueError(f"invalid {path}:{line_number}: {exc}") from exc
    return records


def write_jsonl(path: Path, records: Iterable[BaseModel | dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            value = record.model_dump(mode="json") if isinstance(record, BaseModel) else record
            handle.write(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n")
