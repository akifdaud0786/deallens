"""Inclusion rules: every reason an Observation is kept out of statistics. Nothing is ever dropped."""
from __future__ import annotations

import statistics
from typing import Any, Mapping, Optional

from deallens.config import Rules
from deallens.domain import MatchOutcome, Match, Reason

INR_MARKERS = {"INR", "₹"}


def is_cross_border(storefront: Optional[str], alternative_price: Optional[Mapping[str, Any]], rules: Rules) -> bool:
    currency = (alternative_price or {}).get("currency")
    if currency and currency not in INR_MARKERS:
        return True
    sf = (storefront or "").lower()
    return any(p in sf for p in rules.cross_border_storefront_patterns)


def row_reasons(*, match: Match, listed_price, price_raw, storefront, alternative_price, title,
                second_hand_condition, orphan: bool, repeated: bool, integrity_failed: bool,
                development_probe: bool, rules: Rules) -> tuple[Reason, ...]:
    reasons = []
    if match.outcome is MatchOutcome.UNMATCHED:
        reasons.append(Reason.UNMATCHED)
    elif match.outcome is MatchOutcome.AMBIGUOUS:
        reasons.append(Reason.AMBIGUOUS)
    if listed_price is None:
        reasons.append(Reason.UNPRICED)
    elif not (price_raw or "").strip().startswith("₹"):
        reasons.append(Reason.NON_INR)
    if is_cross_border(storefront, alternative_price, rules):
        reasons.append(Reason.CROSS_BORDER)
    t = (title or "").lower()
    if second_hand_condition or any(k in t for k in rules.used_keywords):
        reasons.append(Reason.USED_OR_REFURBISHED)
    if repeated:
        reasons.append(Reason.INDISTINGUISHABLE_IN_RUN)
    if orphan:
        reasons.append(Reason.ORPHAN_RAW)
    if integrity_failed:
        reasons.append(Reason.INTEGRITY_FAILED)
    if development_probe:
        reasons.append(Reason.DEVELOPMENT_PROBE)
    return tuple(reasons)


def outlier_flags(prices: list[float], rules: Rules) -> tuple[list[bool], str]:
    """Heuristic only (not proof of a wrong variant); not applied below the configured sample size."""
    if len(prices) < rules.outlier_min_sample:
        return [False] * len(prices), f"not applied: {len(prices)} < {rules.outlier_min_sample} observations"
    med = statistics.median(prices)
    return [abs(p - med) / med > rules.outlier_threshold for p in prices], f"median {med}, threshold {rules.outlier_threshold}"
