"""Read-only JSON adapter over the projection and the existing view models (no new logic)."""
import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from deallens.analysis import analyse  # noqa: E402
from deallens.api import create_app  # noqa: E402
from deallens.domain import RawRecord, RawRef, RunSource  # noqa: E402
from deallens.market import build_ledger  # noqa: E402
from deallens.projection import rebuild  # noqa: E402
from deallens.public import PROJECTION  # noqa: E402
from synthetic import synthetic_evidence, synthetic_row, synthetic_run  # noqa: E402

AS_OF = "2026-10-10T18:29:59+00:00"
T = "ASUS Vivobook 15 X1504VAP-BQ224WS"
BQ224, BQ832, NJ = "asus-x1504vap-bq224ws", "asus-x1504ma-bq832ws", "asus-x1504va-nj2324ws"


@pytest.fixture
def client(tmp_path, config):
    """SYNTHETIC copy of today's state + a development probe + a private Immersive raw."""
    active = synthetic_run("scheduled-a", "2026-10-04T10:01:33+00:00",
                           [synthetic_row(1, "Flipkart", T, 66990, old_price="₹73,990"),
                            synthetic_row(2, "ASUS eshop IN", T, 73990)], plan="vivobook15-broad@2")
    retired = synthetic_run("manual-old", "2026-10-03T19:05:53+00:00",
                            [synthetic_row(1, "Flipkart", "Asus Vivobook 15 X1504VA-NJ2324WS", 61599)],
                            plan="vivobook15-broad@1")
    probe, _ = synthetic_run("probe:p", "2026-10-03T14:04:42+00:00", [synthetic_row(1, "Croma", T, 70000)],
                             plan="vivobook15-broad@2", source=RunSource.MANIFEST_LESS_PROBE)
    private = RawRecord(RawRef("data/private/raw/immersive/x.json", "1" * 64),
                        {"run_id": "inv", "kind": "immersive", "fetched_at": "2026-10-04T11:00:00+00:00", "params": {}},
                        {"product_results": {"user_reviews": [{"user_name": "Synthetic Reviewer"}]}},
                        "inv", RunSource.ORPHAN, "private")
    ledger = build_ledger(synthetic_evidence(active, retired, orphans=[probe, private]), config)
    rebuild(ledger, [analyse(ledger, p.product_key, config, as_of=AS_OF) for p in config.products],
            tmp_path / PROJECTION, products=config.products, plans=config.plans, as_of=AS_OF,
            coverage_policy=config.coverage)
    return TestClient(create_app(tmp_path))


def test_status_reports_projection_state(client):
    s = client.get("/api/status").json()
    assert s["status"] == "ready" and s["show_products"] and s["as_of"] == AS_OF
    assert s["latest_observation_at"] == "2026-10-04T10:01:33+00:00"      # private raws yield no observations


def test_missing_projection_is_reported_not_invented(tmp_path):
    c = TestClient(create_app(tmp_path))
    assert c.get("/api/status").json()["status"] == "missing"
    assert c.get("/api/products").json() == []
    assert c.get(f"/api/products/{BQ224}").status_code == 404


def test_products_flag_missing_active_plan_observations(client):
    cards = client.get("/api/products").json()
    assert [(c["model_key"], c["lowest_listed"], c["current"]) for c in cards] == [
        ("X1504VAP-BQ224WS", "₹66,990", True),
        ("X1504MA-BQ832WS", "No current @2 observation", False),
        ("X1504VA-NJ2324WS", "No current @2 observation", False)]


def test_product_view_carries_the_backend_decision(client):
    p = client.get(f"/api/products/{BQ224}").json()
    v = p["view"]
    assert v["hero_price"] == "₹66,990"
    assert v["hero_meta"] == "2 sellers observed · 1 production run · 1 observed calendar day"
    assert v["decision"]["question"] == "Is ₹66,990 a good price?"
    assert v["decision"]["answer"] == "Not enough evidence yet"
    assert v["decision"]["checks"][-1] == [False, "Historical baseline not available yet"]
    assert [m["storefront"] for m in v["market"]] == ["Flipkart", "ASUS eshop IN"]           # probe Croma excluded
    assert v["plan"]["active_ref"] == "vivobook15-broad@2" and v["plan"]["is_current"]
    assert v["history"]["message"] == "No price history yet." and v["history"]["points"] == []
    assert p["coverage_policy"]["sufficient_min_days"] == 5
    assert [(x["plan_ref"], x["status"]) for x in p["plans"]] == [("vivobook15-broad@1", "retired"),
                                                                   ("vivobook15-broad@2", "provisional")]


def test_evidence_ids_stay_traceable(client):
    claims = client.get(f"/api/products/{BQ224}").json()["view"]["claims"]
    lowest = next(c for c in claims if c["kind"] == "current_lowest_listed")
    assert lowest["claim_id"] == f"{BQ224}:C1" and lowest["title"] == "Current lowest listed price"
    assert lowest["source"] == "Google Shopping via SerpApi"
    assert [(e["storefront"], e["run_id"], e["search_id"]) for e in lowest["evidence"]] == [
        ("Flipkart", "scheduled-a", "sid-scheduled-a")]


def test_retired_evidence_is_labelled_not_current(client):
    v = client.get(f"/api/products/{NJ}").json()["view"]
    assert not v["plan"]["is_current"] and v["hero_price"] == "—"
    assert v["decision"]["answer"] == "No current @2 observation"
    assert v["plan"]["label"] == "Retired @1 evidence — not included in current @2 analysis"


def test_product_without_observations(client):
    v = client.get(f"/api/products/{BQ832}").json()["view"]
    assert v["decision"]["answer"] == "No current @2 observation" and v["plan"]["label"] is None


def test_unknown_product_is_404_and_api_is_read_only(client):
    assert client.get("/api/products/nope").status_code == 404
    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)("/api/products").status_code == 405


def test_responses_never_carry_secrets_or_private_evidence(client, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "would-be-secret-key-0123456789")
    blob = json.dumps([client.get(u).json() for u in
                       ("/api/status", "/api/products", *[f"/api/products/{k}" for k in (BQ224, BQ832, NJ)])])
    for bad in ("would-be-secret-key", "api_key", "data/private", "immersive", "Synthetic Reviewer", "serpapi.com"):
        assert bad not in blob, bad


def test_cli_serve_builds_the_read_only_app_on_localhost(monkeypatch, tmp_path):
    import uvicorn
    from deallens import cli
    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: seen.update(app=app, host=host, port=port))
    assert cli.main(["--root", str(tmp_path), "serve"], env={"SERPAPI_API_KEY": "x", "DEALLENS_MODE": "live"}) == 0
    assert seen["host"] == "127.0.0.1" and seen["port"] == 8000
    assert TestClient(seen["app"]).get("/api/status").json()["status"] == "missing"
