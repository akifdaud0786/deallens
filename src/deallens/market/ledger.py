"""build_ledger: evidence + config -> every Observation with Match, Seller and Inclusion. Pure; no I/O."""
from __future__ import annotations

import dataclasses
from typing import Optional

from deallens.config import Config
from deallens.domain import (EvidenceSet, Ledger, Observation, RawRecord, Reason, RunInfo, RunSource, SearchStatus)
from deallens.market import parsing
from deallens.market.fingerprint import policy
from deallens.market.inclusion import outlier_flags, row_reasons
from deallens.market.matching import match
from deallens.market.sellers import seller_of

PLAN_KEYS = ("engine", "q", "gl", "hl", "google_domain", "location")


def _plan_for(raw: RawRecord, config: Config) -> Optional[str]:
    """The recorded plan, else the matching plan version in force when the raw was fetched (never a later one)."""
    if raw.meta.get("plan"):
        return raw.meta["plan"]
    params, fetched = raw.meta.get("params", {}), raw.meta.get("fetched_at", "")
    candidates = [p for p in config.plans if p.effective_from <= fetched
                  and all(params.get(k) == p.params.get(k) for k in PLAN_KEYS)]
    return max(candidates, key=lambda p: p.effective_from).ref if candidates else None


def _runs(evidence: EvidenceSet) -> tuple[RunInfo, ...]:
    runs = [RunInfo(m.run_id, RunSource.MANIFEST, m.status) for m in evidence.manifests]
    probes = sorted({r.run_id for r in evidence.raws if r.run_source is RunSource.MANIFEST_LESS_PROBE})
    return tuple(runs + [RunInfo(p, RunSource.MANIFEST_LESS_PROBE) for p in probes])


def _yields_observations(raw: RawRecord, seen_ids: set) -> bool:
    if raw.meta.get("kind") != "shopping" or raw.sensitivity != "shareable":
        return False
    if raw.meta.get("status") in (SearchStatus.REPEAT.value, SearchStatus.FAILED.value):
        return False
    sid = raw.response.get("search_metadata", {}).get("id")
    return sid not in seen_ids


def build_ledger(evidence: EvidenceSet, config: Config) -> Ledger:
    fingerprint = policy(config.rules.indistinguishable_policy)
    observations: list[Observation] = []
    seen_ids: set = set()
    seen_prints: set = set()
    for raw in sorted(evidence.raws, key=lambda r: (r.meta.get("fetched_at", ""), r.ref.path)):
        sid = raw.response.get("search_metadata", {}).get("id")
        if not _yields_observations(raw, seen_ids):
            if sid:
                seen_ids.add(sid)
            continue
        seen_ids.add(sid)
        plan = _plan_for(raw, config)
        fetched_at = raw.meta["fetched_at"]
        for row in raw.response.get("shopping_results", []):
            title = row.get("title", "")
            m = match(title, row.get("product_id"), config)
            listed = row.get("extracted_price")
            lp = parsing.parse_list_price(row.get("old_price"))
            fp = fingerprint(raw.run_id, row.get("source"), title, listed, lp.list_price_inr)
            reasons = row_reasons(match=m, listed_price=listed, price_raw=row.get("price"),
                                  storefront=row.get("source"), alternative_price=row.get("alternative_price"),
                                  title=title, second_hand_condition=row.get("second_hand_condition"),
                                  orphan=raw.run_source is RunSource.ORPHAN, repeated=fp in seen_prints,
                                  integrity_failed=raw.hash_verified is False,
                                  development_probe=raw.run_source is RunSource.MANIFEST_LESS_PROBE,
                                  rules=config.rules)
            seen_prints.add(fp)
            observations.append(Observation(
                observation_id=f"{raw.ref.path}#{row.get('position')}", raw_ref=raw.ref, run_id=raw.run_id,
                run_source=raw.run_source, search_id=sid, plan=plan, fetched_at=fetched_at,
                observed_day=parsing.observed_day(fetched_at), position=row.get("position"),
                storefront=row.get("source"), seller_key=seller_of(row.get("source"), config.sellers), title=title,
                google_ids=parsing.google_ids(row.get("product_id"), row.get("product_link")),
                listed_price_inr=listed, price_raw=row.get("price"), list_price=lp,
                list_price_raw=row.get("old_price"), alternative_price=row.get("alternative_price"),
                delivery_raw=row.get("delivery"), rating=row.get("rating"), reviews=row.get("reviews"),
                second_hand_condition=row.get("second_hand_condition"),
                immersive_page_token=row.get("immersive_product_page_token"), match=m, included=not reasons,
                reasons=reasons, config_versions={**config.versions, "plan": plan}))
    return Ledger(tuple(_with_outliers(observations, config)), _runs(evidence), evidence.raws, dict(config.versions))


def _with_outliers(observations: list[Observation], config: Config) -> list[Observation]:
    groups: dict = {}
    for i, o in enumerate(observations):
        if o.included:
            groups.setdefault((o.match.product_key, o.run_id), []).append(i)
    out = list(observations)
    for idxs in groups.values():
        flags, note = outlier_flags([observations[i].listed_price_inr for i in idxs], config.rules)
        for i, flagged in zip(idxs, flags):
            o = out[i]
            out[i] = dataclasses.replace(o, outlier_check=note, included=o.included and not flagged,
                                         reasons=o.reasons + ((Reason.OUTLIER,) if flagged else ()))
    return out
