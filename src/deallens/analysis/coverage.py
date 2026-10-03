"""Coverage: how much evidence exists for a product under one Query Plan version. Never combines versions."""
from __future__ import annotations

from deallens.config import Config
from deallens.domain import Coverage, CoverageLevel, Ledger, Observation
from deallens.market.sellers import independent_seller_count


def compute(ledger: Ledger, product_key: str, config: Config, as_of: str) -> tuple[Coverage, list[Observation]]:
    mine = [o for o in ledger.for_product(product_key) if o.included and o.fetched_at <= as_of]
    by_plan: dict = {}
    for o in mine:
        by_plan.setdefault(o.plan, []).append(o)
    current = max(by_plan, key=lambda k: max(o.fetched_at for o in by_plan[k]), default=None)
    obs = sorted(by_plan.get(current, []), key=lambda o: (o.fetched_at, o.position))
    days = tuple(sorted({o.observed_day for o in obs}))
    runs = tuple(sorted({o.run_id for o in obs}))
    sellers = tuple(sorted({o.seller_key for o in obs}))
    indep = independent_seller_count(sellers, config.sellers)
    p = config.coverage
    if len(days) >= p.sufficient_min_days and len(runs) >= p.sufficient_min_runs and indep >= p.sufficient_min_sellers:
        level = CoverageLevel.SUFFICIENT_HISTORY
    elif len(days) >= p.limited_min_days and len(runs) >= p.limited_min_runs:
        level = CoverageLevel.LIMITED_HISTORY
    else:
        level = CoverageLevel.NO_HISTORY
    searched = tuple(sorted({r.run_id for r in ledger.raws if r.meta.get("fetched_at", "") <= as_of
                             and any(o.run_id == r.run_id and o.plan == current for o in ledger.observations)}))
    latest_run = obs[-1].run_id if obs else None          # obs is sorted by fetched_at
    cov = Coverage(product_key, current, tuple(sorted(k for k in by_plan if k != current)), days, runs, searched,
                   sellers, indep, len(obs), level, tuple(o.observation_id for o in obs), latest_run)
    return cov, obs
