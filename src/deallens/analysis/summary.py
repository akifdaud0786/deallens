"""Deterministic template summary. Always available; restates Claims only and cites their ids."""
from __future__ import annotations

from deallens.domain import Claim, Coverage, CoverageLevel


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def render_template(cov: Coverage, claims: tuple[Claim, ...]) -> str:
    if not cov.valid_observations:
        return "No valid observations yet for this product under the current Query Plan. No price history yet."
    days = len(cov.observed_days)
    head = (f"Based on the observations collected by DealLens ({_n(cov.valid_observations, 'valid observation')}, "
            f"{_n(len(cov.runs), 'run')}, {_n(days, 'observed calendar day')}, "
            f"{_n(cov.independent_seller_count, 'independent seller')}):")
    body = " ".join(f"{c.text} [{c.claim_id}]" for c in claims)
    tail = {CoverageLevel.NO_HISTORY: "No price history yet.",
            CoverageLevel.LIMITED_HISTORY: f"Limited history ({_n(days, 'observed calendar day')}).",
            CoverageLevel.SUFFICIENT_HISTORY: ""}[cov.level]
    return " ".join(part for part in (head, body, tail) if part)
