from pathlib import Path

import pytest

from deallens.analysis import analyse
from deallens.projection import ProjectionReader, rebuild

AS_OF = "2026-10-10T18:29:59+00:00"


@pytest.fixture
def built(fixture_ledger, config, tmp_path):
    analyses = [analyse(fixture_ledger, p.product_key, config, as_of=AS_OF) for p in config.products]
    path = tmp_path / "deallens.sqlite"
    build(fixture_ledger, analyses, path, config)
    return path, analyses


def build(ledger, analyses, path, config):
    rebuild(ledger, analyses, path, products=config.products, plans=config.plans,
            missing_probes=("data/cache/gone.json",), as_of=AS_OF, coverage_policy=config.coverage)


def snapshot(path):
    r = ProjectionReader(path)
    keys = [w["product_key"] for w in r.watchlist()]
    return (r.info(), r.watchlist(), r.plans(), r.ledger(), [r.product(k) for k in keys],
            [r.price_series(k) for k in keys], [r.current_market(k) for k in keys])


def test_rebuild_is_deterministic_and_disposable(built, fixture_ledger, config):
    path, analyses = built
    first = snapshot(path)
    Path(path).unlink()
    build(fixture_ledger, analyses, path, config)
    assert snapshot(path) == first
    build(fixture_ledger, analyses, path, config)                        # replace in place
    assert snapshot(path) == first


def test_watchlist_serves_the_ui(built):
    w = ProjectionReader(built[0]).watchlist()
    assert [(x["model_key"], x["coverage_level"], x["lowest_listed_inr"], x["independent_sellers"]) for x in w] == [
        ("X1504VAP-BQ224WS", "no_history", 72800, 2),
        ("X1504MA-BQ832WS", "no_history", 82990, 1),
        ("X1504VA-NJ2324WS", "no_history", 61599, 1)]


def test_product_and_claims_are_what_analysis_computed(built):
    path, analyses = built
    r = ProjectionReader(path)
    a = analyses[0]
    p = r.product(a.product_key)
    assert p["summary"] == a.summary and p["coverage"]["level"] == "no_history"
    assert [c["claim_id"] for c in p["claims"]] == [c.claim_id for c in a.claims]
    c = r.claim(a.claims[0].claim_id)
    assert c["text"] == a.claims[0].text
    assert [s["observation_id"] for s in c["provenance"]] == list(a.claims[0].supporting_observation_ids)
    assert set(c["provenance"][0]) >= {"raw_path", "raw_sha256", "run_id", "run_source", "search_id", "storefront",
                                       "fetched_at"}


def test_ledger_keeps_every_observation_with_reasons(built, fixture_ledger):
    r = ProjectionReader(built[0])
    rows = r.ledger()
    assert len(rows) == len(fixture_ledger.observations) == 80
    unmatched = next(x for x in rows if x["observation_id"].endswith("20261003T140442Z_shopping.json#1"))
    assert unmatched["included"] is False and "unmatched" in unmatched["reasons"]
    assert len(r.ledger("asus-x1504vap-bq224ws")) == 2


def test_projection_contains_no_business_rules():
    src = (Path(__file__).resolve().parents[2] / "src" / "deallens" / "projection" / "__init__.py").read_text(encoding="utf-8")
    for rule in ("min_sample", "threshold", "min_remaining", "sufficient_min", "cross_border_storefront", "aliases"):
        assert rule not in src


# ---------- read model for the UI ----------

def test_metadata_carries_as_of_missing_probes_and_coverage_policy(built):
    info = ProjectionReader(built[0]).info()
    assert info["as_of"] == AS_OF and info["missing_probes"] == ["data/cache/gone.json"]
    assert info["coverage_policy"] == {"version": "coverage-1", "limited_min_days": 2, "limited_min_runs": 2,
                                       "sufficient_min_days": 5, "sufficient_min_runs": 8, "sufficient_min_sellers": 2}
    assert info["observations"] == 80


def test_plans_are_projected_from_configuration(built):
    old, new = ProjectionReader(built[0]).plans()
    assert (old["plan_ref"], old["status"]) == ("vivobook15-broad@1", "retired")
    assert (new["plan_ref"], new["status"], new["params"]["q"]) == ("vivobook15-broad@2", "provisional", "ASUS Vivobook 15")
    assert new["serves"] == ["asus-x1504vap-bq224ws", "asus-x1504ma-bq832ws", "asus-x1504va-nj2324ws"]


def test_current_market_is_the_latest_runs_included_rows(built):
    r = ProjectionReader(built[0])
    rows = r.current_market("asus-x1504vap-bq224ws")
    assert [(x["storefront"], x["listed_price_inr"]) for x in rows] == [("Amazon.in", 72800), ("ASUS eshop IN", 73990)]
    assert {x["stock_status"] for x in rows} == {"unknown"}
    assert r.product("asus-x1504vap-bq224ws")["coverage"]["latest_run_id"] == rows[0]["run_id"]


def _two_plan_projection(config, tmp_path):
    from deallens.market import build_ledger
    from synthetic import synthetic_evidence, synthetic_row, synthetic_run
    t = "ASUS X1504VAP-BQ224WS"
    ev = synthetic_evidence(
        synthetic_run("old-1", "2026-10-04T03:30:00+00:00", [synthetic_row(1, "Amazon.in", t, 72800)], plan="p@1"),
        synthetic_run("new-1", "2026-10-05T03:30:00+00:00", [synthetic_row(1, "Amazon.in", t, 72500)], plan="p@2"),
        synthetic_run("new-2", "2026-10-06T03:30:00+00:00", [synthetic_row(1, "Amazon.in", t, 72000),
                                                            synthetic_row(2, "Croma", t, 73990)], plan="p@2"))
    ledger = build_ledger(ev, config)
    analyses = [analyse(ledger, p.product_key, config, as_of=AS_OF) for p in config.products]
    path = tmp_path / "two-plans.sqlite"
    rebuild(ledger, analyses, path, products=config.products)
    return ProjectionReader(path)


def test_price_series_never_combines_query_plan_versions(config, tmp_path):
    r = _two_plan_projection(config, tmp_path)
    series = r.price_series("asus-x1504vap-bq224ws")
    assert [(x["run_id"], x["storefront"], x["listed_price_inr"]) for x in series] == [
        ("new-1", "Amazon.in", 72500), ("new-2", "Amazon.in", 72000), ("new-2", "Croma", 73990)]
    assert {x["plan"] for x in series} == {"p@2"}
    assert [x["run_id"] for x in r.current_market("asus-x1504vap-bq224ws")] == ["new-2", "new-2"]


def test_products_without_observations_have_empty_series(config, tmp_path):
    r = _two_plan_projection(config, tmp_path)
    assert r.price_series("asus-x1504va-nj2324ws") == [] and r.current_market("asus-x1504va-nj2324ws") == []


def test_private_raw_paths_never_reach_projection_metadata(config, tmp_path):
    from deallens.domain import RawRecord, RawRef, RunSource
    from deallens.market import build_ledger
    from synthetic import synthetic_evidence, synthetic_row, synthetic_run
    shareable, man = synthetic_run("r1", "2026-10-04T03:30:00+00:00",
                                   [synthetic_row(1, "Amazon.in", "ASUS X1504VAP-BQ224WS", 72800)])
    private = RawRecord(RawRef("data/private/raw/immersive/20261004T040000Z_investigation.json", "1" * 64),
                        {"run_id": "investigation-x", "kind": "immersive", "fetched_at": "2026-10-04T04:00:00+00:00",
                         "params": {}}, {"product_results": {"user_reviews": [{"user_name": "Synthetic"}]}},
                        "investigation-x", RunSource.ORPHAN, "private")
    ev = synthetic_evidence((shareable, man), orphans=[private])
    ledger = build_ledger(ev, config)
    path = tmp_path / "privacy.sqlite"
    rebuild(ledger, [], path, products=config.products)
    sources = dict(ProjectionReader(path).info()["sources"])
    assert "synthetic/r1.json" in sources
    assert not [s for s in sources if "private" in s or "immersive" in s]
    blob = path.read_bytes()
    assert b"data/private" not in blob and b"Synthetic" not in blob


def test_unattributed_mirrors_the_ledger_definition(built, fixture_ledger):
    rows = ProjectionReader(built[0]).unattributed()
    assert [r["observation_id"] for r in rows] == [o.observation_id for o in fixture_ledger.unattributed()]
    assert len(rows) == 76 and {r["match_outcome"] for r in rows} == {"unmatched"}


def test_metadata_records_the_latest_observation_time(built, config, tmp_path):
    assert ProjectionReader(built[0]).info()["latest_observation_at"] == "2026-10-03T14:44:32.234191+00:00"
    from deallens.market import build_ledger
    from synthetic import synthetic_evidence
    empty = tmp_path / "empty.sqlite"
    rebuild(build_ledger(synthetic_evidence(), config), [], empty, products=config.products)
    assert ProjectionReader(empty).info()["latest_observation_at"] is None
