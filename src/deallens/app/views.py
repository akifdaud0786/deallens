"""View models for the DealLens UI: pure transforms of ProjectionReader outputs.

Everything numeric or analytical here was already decided by market/analysis and stored in the projection.
This module only selects fields, formats them (text.inr) and attaches labels. No Streamlit import.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from deallens.app import labels
from deallens.text import inr

DASH = "—"
NO_HISTORY_MESSAGE = "No price history yet."


def _money(value) -> str:
    return inr(value) if value is not None else DASH


# ---------- page ----------

@dataclass(frozen=True)
class PageState:
    status: str                      # missing | empty | ready (from public.projection_status)
    show_products: bool
    message: Optional[str]
    as_of: Optional[str]                  # when the analysis/projection was built
    warnings: tuple[str, ...]
    latest_observation_at: Optional[str] = None   # most recent observation in the projection


def page_state(status: str, info: Optional[dict]) -> PageState:
    info = info or {}
    missing = info.get("missing_probes") or []
    warnings = ()
    if missing:
        warnings = (f"{len(missing)} registered probe file{'s are' if len(missing) != 1 else ' is'} missing from this "
                    f"checkout: {', '.join(missing)}. Observations from them are not shown.",)
    if status == "missing":
        return PageState(status, False, "No DealLens projection has been built yet. Run `deallens rebuild` to create one.",
                         None, ())
    if status == "empty":
        return PageState(status, False, "No observations collected yet.", info.get("as_of"), warnings,
                         info.get("latest_observation_at"))
    return PageState(status, True, None, info.get("as_of"), warnings, info.get("latest_observation_at"))


# ---------- market snapshot ----------

@dataclass(frozen=True)
class Card:
    product_key: str
    model_key: str
    display_name: str
    status: str
    lowest_listed: str
    independent_sellers: Optional[int]
    valid_observations: Optional[int]
    coverage: str
    history: str


def snapshot_cards(watchlist: list[dict]) -> list[Card]:
    return [Card(w["product_key"], w["model_key"], w["display_name"], w["status"], _money(w["lowest_listed_inr"]),
                 w["independent_sellers"], w["valid_observations"], labels.coverage_level(w["coverage_level"]),
                 labels.history_status(w["coverage_level"])) for w in watchlist]


# ---------- product detail ----------

@dataclass(frozen=True)
class Identity:
    brand: str
    model_key: str
    display_name: str
    status: str
    plan_ref: Optional[str]
    plan_query: Optional[str]
    plan_status: Optional[str]
    other_plans: tuple[str, ...]


@dataclass(frozen=True)
class Kpis:
    lowest_listed: str
    lowest_listed_at: Optional[str]
    independent_sellers: Optional[int]
    valid_observations: int
    observed_days: int
    runs: int


@dataclass(frozen=True)
class CoverageView:
    level_code: str
    level: str
    observed_days: int
    runs: int
    independent_sellers: int
    valid_observations: int
    days: tuple[str, ...]


@dataclass(frozen=True)
class Evidence:
    observation_id: str
    storefront: Optional[str]
    fetched_at: str
    observed_day: Optional[str]
    run_id: str
    source: str
    search_id: Optional[str]
    raw_path: str
    raw_sha256: str


@dataclass(frozen=True)
class ClaimView:
    claim_id: str
    kind: str
    text: str
    level: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class MarketRow:
    storefront: Optional[str]
    listed_price: str
    list_price: str
    delivery: str
    stock: str
    observed_at: str


@dataclass(frozen=True)
class HistoryPoint:
    observed_at: str
    day: str
    storefront: Optional[str]
    seller: Optional[str]
    price: float
    price_label: str


@dataclass(frozen=True)
class HistoryView:
    message: Optional[str]
    points: tuple[HistoryPoint, ...]


@dataclass(frozen=True)
class LedgerRow:
    observation_id: str
    storefront: Optional[str]
    title: str
    listed_price: str
    included: bool
    match: str
    reasons: tuple[str, ...]
    observed_day: str
    fetched_at: str
    source: str


@dataclass(frozen=True)
class ProductView:
    product_key: str
    identity: Identity
    kpis: Kpis
    coverage: CoverageView
    summary: str
    claims: tuple[ClaimView, ...]
    market: tuple[MarketRow, ...]
    history: HistoryView
    ledger: tuple[LedgerRow, ...]
    no_valid_observations: bool
    as_of: str


def _claim(claims: list[dict], kind: str) -> Optional[dict]:
    return next((c for c in claims if c["kind"] == kind), None)


def _list_price(row: dict) -> str:
    if row.get("list_price_inr") is None:
        return DASH
    return f"{inr(row['list_price_inr'])} (shown by seller, not verified by DealLens)"


def product_view(product: dict, current_market: list[dict], price_series: list[dict], ledger: list[dict],
                 plans: list[dict]) -> ProductView:
    cov = product["coverage"]
    plan = next((p for p in plans if p["plan_ref"] == cov["plan"]), None)
    days_by_obs = {r["observation_id"]: r["observed_day"] for r in ledger}

    lowest = _claim(product["claims"], "current_lowest_listed")
    seller_count = _claim(product["claims"], "seller_count")
    kpis = Kpis(_money(lowest["params"]["price_inr"]) if lowest else DASH,
                ", ".join(sorted({p["storefront"] for p in lowest["provenance"]})) if lowest else None,
                seller_count["params"]["independent"] if seller_count else None,
                cov["valid_observations"], len(cov["observed_days"]), len(cov["runs"]))

    claims = tuple(ClaimView(c["claim_id"], c["kind"], c["text"], labels.coverage_level(c["min_level"]), tuple(
        Evidence(p["observation_id"], p["storefront"], p["fetched_at"], days_by_obs.get(p["observation_id"]),
                 p["run_id"], labels.run_source(p["run_source"]), p["search_id"], p["raw_path"], p["raw_sha256"])
        for p in c["provenance"])) for c in product["claims"])

    market = tuple(MarketRow(r["storefront"], _money(r["listed_price_inr"]), _list_price(r),
                             r.get("delivery_raw") or DASH, r["stock_status"], r["fetched_at"]) for r in current_market)

    if cov["level"] == "no_history":
        history = HistoryView(NO_HISTORY_MESSAGE, ())
    else:
        history = HistoryView(None, tuple(HistoryPoint(r["fetched_at"], r["observed_day"], r["storefront"],
                                                       r["seller_key"], r["listed_price_inr"],
                                                       _money(r["listed_price_inr"])) for r in price_series))

    return ProductView(
        product["product_key"],
        Identity(product["brand"], product["model_key"], product["display_name"], product["status"], cov["plan"],
                 plan["params"].get("q") if plan else None, plan["status"] if plan else None,
                 tuple(cov["other_plans_not_combined"])),
        kpis,
        CoverageView(cov["level"], labels.coverage_level(cov["level"]), len(cov["observed_days"]), len(cov["runs"]),
                     cov["independent_sellers"], cov["valid_observations"], tuple(cov["observed_days"])),
        product["summary"], claims, market, history, ledger_rows(ledger), cov["valid_observations"] == 0,
        product["as_of"])


def ledger_rows(rows: list[dict]) -> tuple[LedgerRow, ...]:
    """Label projection ledger rows as they are; selection was already made by the projection."""
    return tuple(LedgerRow(r["observation_id"], r["storefront"], r["title"], r.get("price_raw") or DASH,
                           r["included"], labels.match_outcome(r["match_outcome"]),
                           tuple(labels.reason(x) for x in r["reasons"]), r["observed_day"], r["fetched_at"],
                           labels.run_source(r["run_source"])) for r in rows)
