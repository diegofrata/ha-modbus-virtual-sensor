"""Pure aggregation helpers — no Home Assistant imports, so they're unit-testable."""
from __future__ import annotations

from collections.abc import Iterable


def aggregate(values: Iterable[float], method: str = "mean") -> float | None:
    """Combine readings into one. None/invalid entries are ignored.

    Returns None if there is nothing to aggregate (e.g. every source sensor is
    currently unavailable) so the caller can decide to hold the last value.
    """
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    if method == "max":
        return max(vals)
    if method == "min":
        return min(vals)
    if method == "median":
        ordered = sorted(vals)
        n = len(ordered)
        mid = n // 2
        if n % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2
    # default: arithmetic mean
    return sum(vals) / len(vals)
