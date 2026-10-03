import copy
import json

import pytest

from conftest import BROAD, FIXTURES
from deallens.domain import SearchStatus
from deallens.evidence import EvidenceStore
from deallens.investigation import investigate, sanitize
from deallens.market import build_ledger
from deallens.serpapi import FixtureSerpApi, SearchOutcome

IMMERSIVE = FIXTURES / "immersive_sanitized" / "20261003T140510Z_immersive_sanitized.json"


def clock():
    t = iter(f"2026-10-04T05:00:{s:02d}+00:00" for s in range(60))
    return lambda: next(t)


@pytest.fixture
def body():
    """Real (sanitized) Immersive response with a SYNTHETIC review re-added to prove it stays private."""
    b = copy.deepcopy(json.loads(IMMERSIVE.read_text(encoding="utf-8"))["response"])
    b["product_results"]["user_reviews"] = [{"user_name": "Synthetic Reviewer", "text": "synthetic review text"}]
    return b


@pytest.fixture
def flipkart(probe_ledger):
    return next(o for o in probe_ledger.observations if o.raw_ref.path.endswith(BROAD.name) and o.position == 7)


def test_investigation_returns_offers_and_keeps_the_raw_private(flipkart, body, config, tmp_path):
    store = EvidenceStore(tmp_path)
    api = FixtureSerpApi([SearchOutcome.ok(body)], credits=247)
    inv = investigate(flipkart, api, store, config, now=clock())
    assert inv.status is SearchStatus.SUCCEEDED and inv.observation_id == flipkart.observation_id
    assert api.calls[0]["engine"] == "google_immersive_product" and api.calls[0]["more_stores"] == "true"
    assert api.calls[0]["page_token"] == flipkart.immersive_page_token
    assert len(inv.offers) == 7 and {o.name for o in inv.offers} == {"Flipkart"}
    assert sum("Out of stock online" in o.stock_text for o in inv.offers) == 4
    assert inv.raw_ref.path.startswith("data/private/raw/immersive/")
    assert not [p for p in (tmp_path / "data" / "evidence").rglob("*.json")
                if "Synthetic Reviewer" in p.read_text(encoding="utf-8")]


def test_sanitized_view_has_no_reviewer_data(flipkart, body, config, tmp_path):
    inv = investigate(flipkart, FixtureSerpApi([SearchOutcome.ok(body)]), EvidenceStore(tmp_path), config, now=clock())
    public = sanitize(inv)
    text = json.dumps(public)
    assert "Synthetic Reviewer" not in text and "synthetic review text" not in text and "raw_path" not in text
    assert public["offers"][0] == {"name": "Flipkart", "price_raw": "₹61,599", "listed_price_inr": 61599,
                                   "total_inr": 61599, "shipping": "Free",
                                   "stock_text": ["In stock online", "Free delivery by 12 Oct"],
                                   "link": public["offers"][0]["link"]}
    assert public["source"] == "cached" and public["fetched_at"] == inv.fetched_at


def test_offers_never_enter_the_ledger(flipkart, body, config, tmp_path):
    store = EvidenceStore(tmp_path)
    investigate(flipkart, FixtureSerpApi([SearchOutcome.ok(body)]), store, config, now=clock())
    assert build_ledger(store.read_all(), config).observations == ()


def test_api_error_and_low_credits_make_no_raw(flipkart, config, tmp_path):
    store = EvidenceStore(tmp_path)
    failed = investigate(flipkart, FixtureSerpApi([SearchOutcome.failure("api_error", "expired token")]), store,
                         config, now=clock())
    assert failed.status is SearchStatus.FAILED and failed.raw_ref is None and "expired" in failed.error
    assert failed.offers == ()
    api = FixtureSerpApi([], credits=59)
    guarded = investigate(flipkart, api, store, config, now=clock())
    assert guarded.status is SearchStatus.SKIPPED and api.calls == []
    assert not list(tmp_path.rglob("*.json"))


def test_investigation_spends_at_most_one_budgeted_call(flipkart, body, config, tmp_path, monkeypatch):
    import deallens.investigation as inv_mod
    from deallens.serpapi import CallBudget
    budgets = []
    real = CallBudget

    def spy(api, max_calls, min_remaining):
        budgets.append((max_calls, min_remaining))
        return real(api, max_calls, min_remaining)

    monkeypatch.setattr(inv_mod, "CallBudget", spy)
    api = FixtureSerpApi([SearchOutcome.ok(body), SearchOutcome.ok(body)])
    investigate(flipkart, api, EvidenceStore(tmp_path), config, now=clock())
    assert budgets == [(1, config.collector.min_remaining)] and len(api.calls) == 1
