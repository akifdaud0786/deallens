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
        warnings = (f"{len(missing)} development probe file{'s are' if len(missing) != 1 else ' is'} not part of this "
                    f"build ({', '.join(missing)}). Probes never count toward statistics, so nothing shown here "
                    "depends on them.",)
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
    current: bool = True


def snapshot_cards(watchlist: list[dict], plans: Optional[list[dict]] = None,
                   coverage_plans: Optional[dict] = None) -> list[Card]:
    """With plans and each product's Coverage plan, products not observed under the active plan show no price."""
    active = active_plan_ref(plans) if plans is not None else None
    cards = []
    for w in watchlist:
        current = plans is None or (coverage_plans or {}).get(w["product_key"]) == active
        price = _money(w["lowest_listed_inr"]) if current else f"No current {_short(active)} observation"
        cards.append(Card(w["product_key"], w["model_key"], w["display_name"], w["status"], price,
                          w["independent_sellers"], w["valid_observations"],
                          labels.coverage_level(w["coverage_level"]), labels.history_status(w["coverage_level"]),
                          current))
    return cards


def active_plan_ref(plans: list[dict]) -> Optional[str]:
    """The single non-retired plan, as configured; None if there is not exactly one."""
    active = [p["plan_ref"] for p in plans if p["status"] != "retired"]
    return active[0] if len(active) == 1 else None


def _short(ref: Optional[str]) -> str:
    return "@" + ref.split("@", 1)[1] if ref and "@" in ref else (ref or "active-plan")


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
    title: str = ""
    source: str = "Google Shopping via SerpApi"


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
class PlanState:
    active_ref: Optional[str]        # the configured non-retired Query Plan
    shown_ref: Optional[str]         # the plan this product's Coverage comes from
    is_current: bool                 # Coverage comes from the active plan
    label: Optional[str]             # explicit label when the shown evidence is from a retired plan


@dataclass(frozen=True)
class Decision:
    question: str
    answer: str
    badge: str
    checks: tuple[tuple[bool, str], ...]
    verdict: str


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
    plan: Optional[PlanState] = None
    decision: Optional[Decision] = None
    hero_price: str = DASH
    hero_meta: str = ""
    known: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()


def _claim(claims: list[dict], kind: str) -> Optional[dict]:
    return next((c for c in claims if c["kind"] == kind), None)


def _list_price(row: dict) -> str:
    if row.get("list_price_inr") is None:
        return DASH
    return f"{inr(row['list_price_inr'])} (shown by seller, not verified by DealLens)"


def product_view(product: dict, current_market: list[dict], price_series: list[dict], ledger: list[dict],
                 plans: list[dict], policy: Optional[dict] = None) -> ProductView:
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
        for p in c["provenance"]), labels.claim_kind(c["kind"])) for c in product["claims"])

    market = tuple(MarketRow(r["storefront"], _money(r["listed_price_inr"]), _list_price(r),
                             r.get("delivery_raw") or DASH, r["stock_status"], r["fetched_at"]) for r in current_market)

    if cov["level"] == "no_history":
        history = HistoryView(NO_HISTORY_MESSAGE, ())
    else:
        history = HistoryView(None, tuple(HistoryPoint(r["fetched_at"], r["observed_day"], r["storefront"],
                                                       r["seller_key"], r["listed_price_inr"],
                                                       _money(r["listed_price_inr"])) for r in price_series))

    active = active_plan_ref(plans)
    is_current = cov["plan"] is not None and cov["plan"] == active
    retired = plan is not None and plan["status"] == "retired"
    plan_state = PlanState(active, cov["plan"], is_current,
                           f"Retired {_short(cov['plan'])} evidence — not included in current {_short(active)} analysis"
                           if retired else None)
    coverage = CoverageView(cov["level"], labels.coverage_level(cov["level"]), len(cov["observed_days"]),
                            len(cov["runs"]), cov["independent_sellers"], cov["valid_observations"],
                            tuple(cov["observed_days"]))
    current = is_current and cov["valid_observations"] > 0
    lowest_claim = next((c for c in claims if c.kind == "current_lowest_listed"), None)
    known, unknown = _knowledge(product, kpis, coverage, market, claims, lowest_claim, plan_state, current, policy)

    return ProductView(
        product["product_key"],
        Identity(product["brand"], product["model_key"], product["display_name"], product["status"], cov["plan"],
                 plan["params"].get("q") if plan else None, plan["status"] if plan else None,
                 tuple(cov["other_plans_not_combined"])),
        kpis, coverage, product["summary"], claims, market, history, ledger_rows(ledger),
        cov["valid_observations"] == 0, product["as_of"],
        plan_state, _decision(kpis, coverage, plan_state, current),
        kpis.lowest_listed if current else DASH,
        (f"{_count(kpis.independent_sellers or 0, 'seller')} observed · {_count(coverage.runs, 'production run')} · "
         f"{_count(coverage.observed_days, 'observed calendar day')}") if current else "",
        known, unknown)


def _count(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _decision(kpis: Kpis, cov: CoverageView, plan: PlanState, current: bool) -> Decision:
    """Wording for the existing Coverage Level and plan state. Never a good/bad verdict: DealLens has no such rule."""
    if not current:
        return Decision("Is there a current price to judge?", f"No current {_short(plan.active_ref)} observation",
                        "No current observation",
                        ((False, f"Not observed in the latest {plan.active_ref or 'active-plan'} results"),),
                        "Keep watching — DealLens reports a price once the active plan observes this product.")
    sellers = kpis.independent_sellers or 0
    base = ((True, "Exact product identity matched"),
            (True, f"{_count(sellers, 'independent seller')} observed"),
            (True, "Current market price observed"))
    question = f"Is {kpis.lowest_listed} a good price?"
    if cov.level_code == "no_history":
        return Decision(question, "Not enough evidence yet", "Evidence accumulating",
                        base + ((False, "Historical baseline not available yet"),),
                        "Keep watching — historical evidence is still accumulating.")
    if cov.level_code == "limited_history":
        return Decision(question, "Early evidence only", "Limited history",
                        base + ((True, f"Price changes observed across {_count(cov.observed_days, 'calendar day')}"),
                                (False, "Observed low / high / average not available yet")),
                        "Early signal only — see the observed changes below; not enough evidence for a historical "
                        "baseline.")
    return Decision(question, "Compare with the observed range", "History available",
                    base + ((True, "Observed low / high / average available"),),
                    "Compare today's price with the low, high and average DealLens observed below. "
                    "DealLens does not predict future prices.")


def _knowledge(product, kpis, cov, market, claims, lowest, plan, current, policy):
    if not current:
        known = ((f"Older observations exist under retired plan {plan.shown_ref}; they are not used here",)
                 if plan.label else ())
        return known, (f"Today's price under the active plan {plan.active_ref}",)
    run = lowest.evidence[0] if lowest and lowest.evidence else None
    raws = {e.raw_path for c in claims for e in c.evidence}
    known = [f"Exact model {product['model_key']} matched by deterministic identity rules",
             f"{_count(kpis.independent_sellers or 0, 'independent seller')} observed in the latest run",
             f"Lowest observed listed price: {kpis.lowest_listed} at {kpis.lowest_listed_at}"]
    if run:
        known.append(f"Production observation recorded at {run.fetched_at} UTC (run {run.run_id})")
    if cov.level_code != "no_history":
        known.append(f"Observed on {_count(cov.observed_days, 'calendar day')} across {_count(cov.runs, 'run')}")
    known.append(f"{_count(len(raws), 'raw SerpApi response')} stored with "
                 f"{'its' if len(raws) == 1 else 'their'} SHA-256 hash")
    unknown = []
    if cov.level_code != "sufficient_history" and policy:
        unknown.append(f"Observed low / high / average: needs at least {policy['sufficient_min_days']} observed "
                       f"calendar days, {policy['sufficient_min_runs']} runs and {policy['sufficient_min_sellers']} "
                       "independent sellers")
    if cov.level_code == "no_history":
        unknown.append("How the price moves over time: no price history yet")
    if any(m.stock == "unknown" for m in market):
        unknown.append("Stock availability: unknown (Google Shopping results do not state it)")
    if any(m.list_price != DASH for m in market):
        unknown.append("Whether the seller-displayed list price was ever charged: not verified by DealLens")
    unknown.append("Sellers beyond this Google Shopping page: one query returns about 40 results, so coverage is "
                   "not exhaustive")
    return tuple(known), tuple(unknown)


def ledger_rows(rows: list[dict]) -> tuple[LedgerRow, ...]:
    """Label projection ledger rows as they are; selection was already made by the projection."""
    return tuple(LedgerRow(r["observation_id"], r["storefront"], r["title"], r.get("price_raw") or DASH,
                           r["included"], labels.match_outcome(r["match_outcome"]),
                           tuple(labels.reason(x) for x in r["reasons"]), r["observed_day"], r["fetched_at"],
                           labels.run_source(r["run_source"])) for r in rows)
