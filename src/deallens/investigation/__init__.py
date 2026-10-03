"""On-demand Immersive Product Investigation (ADR 0002). Never scheduled; Offers never enter statistics.

Raw responses contain reviewer names and text, so they are stored only in the private area.
`sanitize` produces the only publishable form.
"""
from __future__ import annotations

from typing import Callable

from deallens.config import Config
from deallens.domain import Investigation, Observation, Offer, SearchStatus
from deallens.evidence import EvidenceStore
from deallens.serpapi import CallBlocked, CallBudget, CreditReadError, SerpApi


def _offers(body) -> tuple[Offer, ...]:
    stores = (body or {}).get("product_results", {}).get("stores", [])
    return tuple(Offer(s.get("name"), s.get("price"), s.get("extracted_price"), s.get("extracted_total"),
                       s.get("shipping"), tuple(s.get("details_and_offers", [])), s.get("link")) for s in stores)


def investigate(observation: Observation, serpapi: SerpApi, store: EvidenceStore, config: Config, *,
                now: Callable[[], str]) -> Investigation:
    at = now()
    inv_id = f"investigation-{at}"

    def result(status, raw_ref=None, offers=(), title=None, error=None):
        return Investigation(inv_id, observation.observation_id, at, status, raw_ref, offers, title, error)

    if not observation.immersive_page_token:
        return result(SearchStatus.SKIPPED, error="observation has no Immersive page token")
    budget = CallBudget(serpapi, 1, config.collector.min_remaining)    # one paid call at most
    try:
        budget.open()
    except CreditReadError as e:
        return result(SearchStatus.FAILED, error=f"credit read failed: {e}")
    except CallBlocked as e:
        return result(SearchStatus.SKIPPED, error=str(e))
    params = {"engine": "google_immersive_product", "page_token": observation.immersive_page_token,
              "more_stores": "true", "no_cache": "true"}
    out = budget.search(params, config.collector.timeout_s)
    if out.status != "ok":
        return result(SearchStatus.FAILED, error=f"{out.status}: {out.error}")
    sid = (out.body or {}).get("search_metadata", {}).get("id")
    ref = store.write_raw({"run_id": inv_id, "kind": "immersive", "plan": None, "params": params, "fetched_at": at,
                           "search_id": sid, "status": "succeeded", "observation_id": observation.observation_id},
                          out.body, sensitivity="private")
    return result(SearchStatus.SUCCEEDED, ref, _offers(out.body), (out.body or {}).get("product_results", {}).get("title"))


def sanitize(inv: Investigation) -> dict:
    """Publishable view: offers and timing only. No raw path, no reviewer data."""
    return {"investigation_id": inv.investigation_id, "observation_id": inv.observation_id,
            "fetched_at": inv.fetched_at, "status": inv.status.value, "title": inv.title, "source": "cached",
            "offers": [{"name": o.name, "price_raw": o.price_raw, "listed_price_inr": o.listed_price_inr,
                        "total_inr": o.total_inr, "shipping": o.shipping, "stock_text": list(o.stock_text),
                        "link": o.link} for o in inv.offers]}
