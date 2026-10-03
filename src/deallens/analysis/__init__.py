"""analysis: Ledger -> Coverage -> allowed Claims -> template summary, per Tracked Product. Pure; no LLM."""
from __future__ import annotations

from deallens.analysis import claims as _claims
from deallens.analysis import coverage as _coverage
from deallens.analysis.summary import render_template
from deallens.config import Config
from deallens.domain import DealAnalysis, Ledger


def analyse(ledger: Ledger, product_key: str, config: Config, *, as_of: str) -> DealAnalysis:
    cov, obs = _coverage.compute(ledger, product_key, config, as_of)
    claims = _claims.build(cov, obs, ledger, as_of, config.sellers)
    return DealAnalysis(product_key, as_of, cov, claims, render_template(cov, claims), "template",
                        {**config.versions, "plan": cov.plan})


__all__ = ["analyse"]
