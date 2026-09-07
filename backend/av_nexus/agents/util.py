"""Shared heuristic helpers for reference agents.

Formulas here are transparent rules-of-thumb, documented as such. They never
impersonate external research; agents lower confidence when inputs are sparse.
"""

from __future__ import annotations


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def weighted_100(factors: list[tuple[float, float]]) -> float:
    """weighted average of (value, weight) pairs, weights sum to 1."""
    total = sum(w for _, w in factors)
    if total <= 0:
        return 0.0
    return clamp(sum(v * w for v, w in factors) / total)


def confidence_from_sources(mode_sources: int, required: int = 2) -> float:
    """Confidence rises with distinct sources; capped below 1 when no external
    sources exist."""
    return clamp(0.35 + 0.2 * mode_sources, 0.0, 0.9)


def as_number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def get_input(ctx_inputs: dict[str, object], key: str, default: object = None) -> object:
    return ctx_inputs.get(key, default)
