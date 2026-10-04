"""Presentation labels: internal codes -> human-readable text. No rules; unknown codes pass through unchanged."""

REASONS = {
    "unmatched": "Not matched to a tracked product",
    "ambiguous": "Ambiguous: matches more than one tracked product",
    "cross_border": "Cross-border reseller",
    "used_or_refurbished": "Used, refurbished or open-box",
    "unpriced": "No listed price",
    "non_inr": "Price not in INR",
    "indistinguishable_in_run": "Indistinguishable from another result in the same run",
    "outlier": "Price far from its peers in the same run (heuristic)",
    "orphan_raw": "Raw response without a run manifest",
    "integrity_failed": "Raw evidence failed its integrity check",
    "development_probe": "Development probe (not production evidence)",
}

COVERAGE_LEVELS = {
    "no_history": "No history",
    "limited_history": "Limited history",
    "sufficient_history": "Sufficient history",
}

HISTORY_STATUS = {
    "no_history": "No price history yet",
    "limited_history": "Limited price history",
    "sufficient_history": "Price history available",
}

RUN_SOURCES = {
    "manifest": "Scheduled or manual run",
    "manifest_less_probe": "Development probe (no run manifest)",
    "orphan": "Orphan raw response",
}

MATCH_OUTCOMES = {
    "matched": "Matched",
    "unmatched": "Unmatched",
    "ambiguous": "Ambiguous",
}

CLAIM_KINDS = {
    "current_lowest_listed": "Current lowest listed price",
    "seller_count": "Sellers observed",
    "current_spread": "Price spread today",
    "listed_discount": "Seller-displayed list price",
    "change_since": "Change since first observation",
    "observed_low": "Observed low",
    "observed_high": "Observed high",
    "observed_average": "Observed average",
    "excluded_count": "Excluded observations",
}

SEARCH_STATUS = {"succeeded": "Succeeded", "repeat": "Repeat (cached)", "failed": "Failed", "skipped": "Skipped"}


def _label(table: dict, code):
    return table.get(code, code) if code is not None else "—"


def reason(code: str) -> str:
    return _label(REASONS, code)


def coverage_level(code: str) -> str:
    return _label(COVERAGE_LEVELS, code)


def history_status(code: str) -> str:
    return _label(HISTORY_STATUS, code)


def claim_kind(code: str) -> str:
    return _label(CLAIM_KINDS, code)


def run_source(code: str) -> str:
    return _label(RUN_SOURCES, code)


def match_outcome(code: str) -> str:
    return _label(MATCH_OUTCOMES, code)
