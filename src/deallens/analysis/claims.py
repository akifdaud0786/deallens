"""Deterministic Claims. Every number comes from Observations; every Claim carries its provenance."""
from __future__ import annotations

import re
import statistics
from typing import Any, Iterable, Mapping

from deallens.config import SellerMap
from deallens.domain import Claim, Coverage, CoverageLevel, Ledger, Observation, Provenance
from deallens.market.sellers import independent_seller_count
from deallens.text import inr

FORBIDDEN = re.compile(r"all[- ]time|fake|will (drop|rise|fall|increase|decrease)|best deal|guarantee", re.I)


class UnsupportedClaim(ValueError):
    pass


def check_text(text: str) -> str:
    if FORBIDDEN.search(text):
        raise UnsupportedClaim(f"unsupported wording in claim: {text!r}")
    return text


def _prov(o: Observation) -> Provenance:
    return Provenance(o.observation_id, o.raw_ref.path, o.raw_ref.sha256, o.run_id, o.run_source, o.search_id,
                      o.storefront, o.fetched_at)


def build(cov: Coverage, obs: list[Observation], ledger: Ledger, as_of: str, sellers: SellerMap) -> tuple[Claim, ...]:
    pk = cov.product_key
    claims: list[Claim] = []

    def add(kind: str, text: str, support: Iterable[Observation], level: CoverageLevel, params: Mapping[str, Any]):
        if cov.level.rank < level.rank:
            return
        support = tuple(support)
        claims.append(Claim(f"{pk}:C{len(claims) + 1}", kind, check_text(text), dict(params),
                            tuple(o.observation_id for o in support), tuple(_prov(o) for o in support), level))

    now_level = CoverageLevel.NO_HISTORY
    if obs:
        now = [o for o in obs if o.run_id == cov.latest_run_id]
        low = min(o.listed_price_inr for o in now)
        high = max(o.listed_price_inr for o in now)
        lows = [o for o in now if o.listed_price_inr == low]
        add("current_lowest_listed", f"Lowest listed price observed in the latest run: {inr(low)} at "
            f"{', '.join(sorted({o.storefront for o in lows}))} (stock status: unknown).", lows, now_level,
            {"price_inr": low})
        # Both numbers describe the same window: the latest run.
        storefronts = sorted({o.storefront for o in now})
        independent = independent_seller_count({o.seller_key for o in now}, sellers)
        add("seller_count", f"Observed at {len(storefronts)} storefront{'s' if len(storefronts) != 1 else ''}, "
            f"counting as {independent} independent seller{'s' if independent != 1 else ''}.", now, now_level,
            {"storefronts": len(storefronts), "independent": independent})
        if len(now) >= 2:
            text = (f"Listed prices in the latest run range from {inr(low)} to {inr(high)}." if low != high else
                    f"Observed listed prices are {inr(low)} across the included sellers in the latest run.")
            add("current_spread", text, now, now_level, {"low": low, "high": high})
        for o in now:
            if o.list_price.list_price_inr is not None:
                add("listed_discount", f"{o.storefront} displayed a list price of {inr(o.list_price.list_price_inr)} "
                    f"next to {inr(o.listed_price_inr)}; DealLens has not verified that list price.", [o], now_level,
                    {"list_price_inr": o.list_price.list_price_inr, "listed_price_inr": o.listed_price_inr})

        for seller in sorted({o.seller_key for o in obs}):
            series = [o for o in obs if o.seller_key == seller]
            first, last = series[0], series[-1]
            if first.observed_day == last.observed_day:
                continue
            pct = (last.listed_price_inr - first.listed_price_inr) / first.listed_price_inr * 100
            add("change_since", f"At {seller} the listed price moved from {inr(first.listed_price_inr)} on "
                f"{first.observed_day} to {inr(last.listed_price_inr)} on {last.observed_day} ({pct:.1f}%).",
                [first, last], CoverageLevel.LIMITED_HISTORY,
                {"seller": seller, "from": first.listed_price_inr, "to": last.listed_price_inr, "pct": round(pct, 1)})

        days = len(cov.observed_days)
        lo = min(obs, key=lambda o: o.listed_price_inr)
        hi = max(obs, key=lambda o: o.listed_price_inr)
        avg = round(statistics.fmean(o.listed_price_inr for o in obs), 2)
        add("observed_low", f"Lowest listed price observed by DealLens over {days} observed calendar days: "
            f"{inr(lo.listed_price_inr)} at {lo.storefront} on {lo.observed_day}.",
            [o for o in obs if o.listed_price_inr == lo.listed_price_inr], CoverageLevel.SUFFICIENT_HISTORY,
            {"price_inr": lo.listed_price_inr})
        add("observed_high", f"Highest listed price observed by DealLens over {days} observed calendar days: "
            f"{inr(hi.listed_price_inr)} at {hi.storefront} on {hi.observed_day}.",
            [o for o in obs if o.listed_price_inr == hi.listed_price_inr], CoverageLevel.SUFFICIENT_HISTORY,
            {"price_inr": hi.listed_price_inr})
        add("observed_average", f"Based on the observations collected by DealLens over {days} observed calendar days, the "
            f"average listed price was {inr(round(avg))} across {len(obs)} valid observations.", obs,
            CoverageLevel.SUFFICIENT_HISTORY, {"price_inr": avg})

    attributed = [o for o in ledger.for_product(pk) if not o.included and o.fetched_at <= as_of]
    # Same Query Plan version as Coverage; if nothing was included, the most recent plan of the exclusions.
    scope = cov.plan if cov.plan is not None else max(attributed, key=lambda o: o.fetched_at).plan if attributed else None
    excluded = [o for o in attributed if o.plan == scope]
    if excluded:
        add("excluded_count", f"{len(excluded)} observation{'s' if len(excluded) != 1 else ''} attributed to this "
            f"product {'were' if len(excluded) != 1 else 'was'} excluded from statistics (see Evidence Ledger).",
            excluded, now_level, {"count": len(excluded)})
    return tuple(claims)
