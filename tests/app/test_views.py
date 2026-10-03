"""App view models: pure transforms of ProjectionReader outputs. No Streamlit, no domain rules."""
import pytest

from deallens.analysis import analyse
from deallens.app import labels, views
from deallens.domain import CoverageLevel, Reason, RunSource
from deallens.market import build_ledger
from deallens.projection import ProjectionReader, rebuild
from synthetic import synthetic_evidence, synthetic_row, synthetic_run

AS_OF = "2026-10-10T18:29:59+00:00"
BQ224, BQ832, NJ = "asus-x1504vap-bq224ws", "asus-x1504ma-bq832ws", "asus-x1504va-nj2324ws"
T = "ASUS X1504VAP-BQ224WS"


def project(ledger, config, tmp_path, name="p.sqlite", missing=()):
    path = tmp_path / name
    rebuild(ledger, [analyse(ledger, p.product_key, config, as_of=AS_OF) for p in config.products], path,
            products=config.products, plans=config.plans, missing_probes=missing, as_of=AS_OF,
            coverage_policy=config.coverage)
    return ProjectionReader(path)


def product_view(r, key):
    return views.product_view(r.product(key), r.current_market(key), r.price_series(key), r.ledger(key), r.plans())


@pytest.fixture
def real(fixture_ledger, config, tmp_path):
    return project(fixture_ledger, config, tmp_path)


def days(config, tmp_path, n, runs_per_day=1, sellers=("Amazon.in", "Croma")):
    runs = [synthetic_run(f"d{d}r{r}", f"2026-10-0{4 + d}T0{3 + 6 * r}:30:00+00:00",
                          [synthetic_row(i + 1, s, T, 72800 - 100 * d + 1000 * i) for i, s in enumerate(sellers)])
            for d in range(n) for r in range(runs_per_day)]
    return project(build_ledger(synthetic_evidence(*runs), config), config, tmp_path)


# ---------- A, B, C, M: page state ----------

def test_missing_projection_has_a_message_and_no_numbers():
    s = views.page_state("missing", None)
    assert s.status == "missing" and not s.show_products
    assert s.message == "No DealLens projection has been built yet. Run `deallens rebuild` to create one."
    assert s.as_of is None and s.warnings == ()


def test_empty_projection_says_no_observations(config, tmp_path):
    r = project(build_ledger(synthetic_evidence(), config), config, tmp_path)
    s = views.page_state("empty", r.info())
    assert s.message == "No observations collected yet." and not s.show_products and s.as_of == AS_OF


def test_missing_probes_become_a_warning(probe_ledger, config, tmp_path):
    r = project(probe_ledger, config, tmp_path, missing=("data/cache/a.json", "data/cache/b.json"))
    s = views.page_state("ready", r.info())
    assert s.show_products and s.message is None and s.as_of == AS_OF
    assert s.warnings == ("2 registered probe files are missing from this checkout: data/cache/a.json, "
                          "data/cache/b.json. Observations from them are not shown.",)


# ---------- market snapshot ----------

def test_snapshot_cards_show_only_projected_values(real):
    cards = views.snapshot_cards(real.watchlist())
    assert [(c.model_key, c.lowest_listed, c.independent_sellers, c.coverage, c.history) for c in cards] == [
        ("X1504VAP-BQ224WS", "₹72,800", 2, "No history", "No price history yet"),
        ("X1504MA-BQ832WS", "₹82,990", 1, "No history", "No price history yet"),
        ("X1504VA-NJ2324WS", "₹61,599", 1, "No history", "No price history yet")]


def test_card_without_a_price_shows_a_dash_not_a_number(config, tmp_path):
    r = project(build_ledger(synthetic_evidence(), config), config, tmp_path)
    assert {c.lowest_listed for c in views.snapshot_cards(r.watchlist())} == {"—"}


# ---------- E, I, J, L: today's real state ----------

def test_no_history_product_has_no_chart_points(real):
    v = product_view(real, BQ224)
    assert v.history.message == "No price history yet." and v.history.points == ()
    assert v.coverage.level == "No history" and v.coverage.observed_days == 1 and v.coverage.runs == 1
    assert v.kpis.lowest_listed == "₹72,800" and v.kpis.lowest_listed_at == "Amazon.in"
    assert v.kpis.independent_sellers == 1 + 1 and v.kpis.valid_observations == 2
    assert v.summary.endswith("No price history yet.")


def test_current_market_rows_keep_stock_unknown_and_label_list_prices(real):
    rows = product_view(real, NJ).market
    assert [(m.storefront, m.listed_price, m.list_price, m.stock) for m in rows] == [
        ("Flipkart", "₹61,599", "₹68,999 (shown by seller, not verified by DealLens)", "unknown")]
    assert [m.list_price for m in product_view(real, BQ224).market] == ["—", "—"]


def test_evidence_exposes_only_projected_provenance(real):
    v = product_view(real, BQ224)
    lowest = next(c for c in v.claims if c.kind == "current_lowest_listed")
    (e,) = lowest.evidence
    assert (e.storefront, e.fetched_at, e.observed_day, e.source) == (
        "Amazon.in", "2026-10-03T14:04:42.517480+00:00", "2026-10-03", "Scheduled or manual run")
    assert e.raw_path == "data/cache/20261003T140442Z_shopping.json" and len(e.raw_sha256) == 64
    assert e.search_id == "6ac10b76a26f566bae26b24b"


def test_claims_are_passed_through_unchanged(real):
    v = product_view(real, BQ832)
    analysis_texts = [c["text"] for c in real.product(BQ832)["claims"]]
    assert [c.text for c in v.claims] == analysis_texts
    assert [c.level for c in v.claims] == ["No history"] * len(analysis_texts)


# ---------- K: excluded observations ----------

def test_ledger_rows_keep_every_reason_with_its_label(config, tmp_path):
    rows = [synthetic_row(1, "Amazon.in", T, 72800), synthetic_row(2, "desertcart.in", T, 99000),
            synthetic_row(3, "Example", "Compare X1504VAP-BQ224WS vs X1504MA-BQ832WS", 70000)]
    r = project(build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows)), config),
                config, tmp_path)
    ledger = product_view(r, BQ224).ledger
    assert [(x.storefront, x.included, x.reasons) for x in ledger] == [
        ("Amazon.in", True, ()),
        ("desertcart.in", False, ("Cross-border reseller",)),
        ("Example", False, ("Ambiguous: matches more than one tracked product",))]


def test_observation_with_several_reasons_keeps_all_of_them(config, tmp_path):
    rows = [synthetic_row(1, "desertcart.in", "Renewed ASUS X1504VAP-BQ224WS", 50000)]
    r = project(build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows)), config),
                config, tmp_path)
    (row,) = product_view(r, BQ224).ledger
    assert row.reasons == ("Cross-border reseller", "Used, refurbished or open-box")


def test_every_exclusion_reason_and_source_has_a_label():
    assert set(labels.REASONS) == {r.value for r in Reason}
    assert set(labels.COVERAGE_LEVELS) == {c.value for c in CoverageLevel}
    assert set(labels.RUN_SOURCES) == {s.value for s in RunSource}
    assert labels.REASONS["integrity_failed"] == "Raw evidence failed its integrity check"
    assert labels.REASONS["orphan_raw"] == "Raw response without a run manifest"
    assert labels.reason("future_reason") == "future_reason"          # unknown codes are shown, never dropped


# ---------- D: no valid observations ----------

def test_product_with_only_excluded_observations(config, tmp_path):
    rows = [synthetic_row(1, "desertcart.in", T, 99000)]
    r = project(build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows)), config),
                config, tmp_path)
    v = product_view(r, BQ224)
    assert v.no_valid_observations is True and v.kpis.lowest_listed == "—" and v.market == ()
    assert [c.kind for c in v.claims] == ["excluded_count"]
    assert v.summary == "No valid observations yet for this product under the current Query Plan. No price history yet."


# ---------- F, G: history ----------

def test_limited_history_exposes_observed_points_and_change_claims(config, tmp_path):
    v = product_view(days(config, tmp_path, 3), BQ224)
    assert v.coverage.level == "Limited history" and v.history.message is None
    assert [(p.day, p.storefront, p.price) for p in v.history.points][:2] == [
        ("2026-10-04", "Amazon.in", 72800), ("2026-10-04", "Croma", 73800)]
    assert len(v.history.points) == 6
    assert {c.kind for c in v.claims} >= {"change_since"}


def test_sufficient_history_exposes_the_analysis_low_high_average(config, tmp_path):
    v = product_view(days(config, tmp_path, 6, runs_per_day=2), BQ224)
    assert v.coverage.level == "Sufficient history"
    assert {"observed_low", "observed_high", "observed_average"} <= {c.kind for c in v.claims}


# ---------- H: other Query Plans ----------

def test_other_plans_are_reported_not_combined(config, tmp_path):
    ev = synthetic_evidence(
        synthetic_run("o", "2026-10-04T03:30:00+00:00", [synthetic_row(1, "Amazon.in", T, 72800)], plan="vivobook15-broad@1"),
        synthetic_run("n", "2026-10-05T03:30:00+00:00", [synthetic_row(1, "Amazon.in", T, 72500)],
                      plan="vivobook15-broad@2"))
    v = product_view(project(build_ledger(ev, config), config, tmp_path), BQ224)
    assert v.identity.plan_ref == "vivobook15-broad@2" and v.identity.plan_query == "ASUS Vivobook 15"
    assert v.identity.plan_status == "provisional" and v.identity.other_plans == ("vivobook15-broad@1",)
    assert [p.price for p in v.history.points] == []          # no_history: one run under the current plan


def test_unattributed_rows_are_labelled_not_filtered(real):
    rows = views.ledger_rows(real.unattributed())
    assert len(rows) == 76 and {r.match for r in rows} == {"Unmatched"}
    assert all(not r.included and "Not matched to a tracked product" in r.reasons for r in rows)


def test_page_state_carries_build_time_and_latest_observation_separately(real):
    s = views.page_state("ready", real.info())
    assert s.as_of == AS_OF and s.latest_observation_at == "2026-10-03T14:44:32.234191+00:00"
