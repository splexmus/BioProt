from __future__ import annotations


def optional_float(value: str | None) -> float | None:
    return float(value) if value not in (None, "") else None


def optional_int(value: str | None) -> int | None:
    return int(value) if value not in (None, "") else None


def optional_bool(value: str | None) -> bool | None:
    if value in (None, ""):
        return None
    normalized = value.casefold()
    if normalized not in {"true", "false"}:
        raise ValueError(f"expected true/false, got {value!r}")
    return normalized == "true"


def terms(value: str | None) -> list[str]:
    return sorted({item.strip() for item in (value or "").split(";") if item.strip()})
