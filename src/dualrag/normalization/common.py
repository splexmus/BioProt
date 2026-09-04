from __future__ import annotations

import math


def clamp01(value: float | None) -> float:
    return min(1.0, max(0.0, value or 0.0))


def evalue_strength(value: float | None, cap: float = 200.0) -> float:
    if value is None:
        return 0.0
    if value <= 0:
        return 1.0
    return min(cap, max(0.0, -math.log10(value))) / cap


def saturating(value: float | None, scale: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return 1.0 - math.exp(-value / scale)
