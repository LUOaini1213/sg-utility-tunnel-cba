"""Discount factors.

Base case: HM Treasury Green Book (2026 edition, updated 28 Oct 2026), real rates:
3.00% for years 1-30, 2.50% for years 31-75, 2.25% from year 76 (source S2).
"""
from __future__ import annotations

import numpy as np

GREEN_BOOK_2026 = ((30, 0.03), (75, 0.025), (10**9, 0.0225))


def rate_for_year(year: int, schedule=GREEN_BOOK_2026) -> float:
    for last_year, rate in schedule:
        if year <= last_year:
            return rate
    raise ValueError(year)


def factors(horizon: int, flat_rate: float | None = None) -> np.ndarray:
    """Discount factors for years 0..horizon (year 0 factor is 1)."""
    df = np.ones(horizon + 1)
    for t in range(1, horizon + 1):
        r = flat_rate if flat_rate is not None else rate_for_year(t)
        df[t] = df[t - 1] / (1.0 + r)
    return df
