import pytest

from deallens.analysis import analyse
from deallens.analysis.claims import UnsupportedClaim, check_text
from deallens.domain import CoverageLevel, RunSource
from deallens.market import build_ledger
from synthetic import synthetic_evidence, synthetic_row, synthetic_run

AS_OF = "2026-10-10T18:29:59+00:00"
BQ224, BQ832, NJ = "asus-x1504vap-bq224ws", "asus-x1504ma-bq832ws", "asus-x1504va-nj2324ws"


def kinds(a):
    return [c.kind for c in a.claims]


def claim(a, kind):
    return next(c for c in a.claims if c.kind == kind)


# ---------- real 3 Oct rows, relabelled as one production run (fixture_ledger) ----------

def test_real_fixtures_support_only_current_market_claims(fixture_ledger, config):
    for pk in (BQ224, BQ832, NJ):
        a = analyse(fixture_ledger, pk, config, as_of=AS_OF)
        assert a.coverage.level is CoverageLevel.NO_HISTORY
        assert a.coverage.observed_days == ("2026-10-03",) and len(a.coverage.runs) == 1
        assert {c.min_level for c in a.claims} == {CoverageLevel.NO_HISTORY}
        assert a.summary.endswith("No price history yet.") and a.summary_source == "template"
        assert "excluded_count" not in kinds(a)


def test_bq224ws_current_market(fixture_ledger, config):
    a = analyse(fixture_ledger, BQ224, config, as_of=AS_OF)
    assert a.coverage.independent_seller_count == 2 and a.coverage.valid_observations == 2
    assert claim(a, "current_lowest_listed").text == \
        "Lowest listed price observed in the latest run: ₹72,800 at Amazon.in (stock status: unknown)."
    assert claim(a, "current_spread").text == "Listed prices in the latest run range from ₹72,800 to ₹73,990."
    assert a.summary.startswith("Based on the observations collected by DealLens (2 valid observations, 1 run, "
                                "1 observed calendar day, 2 independent sellers):")


def test_related_storefronts_count_once_and_equal_prices_read_naturally(config):
    # BQ541WS (the real asus.com + ASUS eshop IN pair) left the watchlist; the same shape, SYNTHETIC, on BQ224WS.
    rows = [synthetic_row(1, "asus.com", "ASUS Vivobook 15 X1504VAP-BQ224WS", 73990),
            synthetic_row(2, "ASUS eshop IN", "ASUS Vivobook 15 X1504VAP-BQ224WS", 73990)]
    a = analyse(build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows)), config),
                BQ224, config, as_of=AS_OF)
    assert a.coverage.sellers == ("ASUS eshop IN", "asus.com") and a.coverage.independent_seller_count == 1
    assert claim(a, "current_spread").text == \
        "Observed listed prices are ₹73,990 across the included sellers in the latest run."


def test_displayed_list_price_is_restated_not_endorsed(fixture_ledger, config):
    a = analyse(fixture_ledger, NJ, config, as_of=AS_OF)
    assert claim(a, "listed_discount").text == \
        "Flipkart displayed a list price of ₹68,999 next to ₹61,599; DealLens has not verified that list price."


def test_every_claim_traces_back_to_raw_evidence(fixture_ledger, config):
    shas = {r.ref.path: r.ref.sha256 for r in fixture_ledger.raws}
    for pk in (BQ224, BQ832, NJ):
        a = analyse(fixture_ledger, pk, config, as_of=AS_OF)
        for c in a.claims:
            assert c.supporting_observation_ids and c.claim_id in a.summary
            for p in c.provenance:
                o = fixture_ledger.get(p.observation_id)
                assert p.raw_path == o.raw_ref.path and p.raw_sha256 == shas[p.raw_path]
                assert p.run_id == o.run_id and p.run_source is RunSource.MANIFEST
                assert p.search_id == "6ac10b76a26f566bae26b24b" and p.storefront and p.fetched_at == o.fetched_at


def test_analysis_is_deterministic(fixture_ledger, config):
    assert analyse(fixture_ledger, BQ224, config, as_of=AS_OF) == analyse(fixture_ledger, BQ224, config, as_of=AS_OF)


# ---------- SYNTHETIC multi-day histories ----------

T = "ASUS Vivobook 15 X1504VAP-BQ224WS"


def synthetic_days(prices_by_day, runs_per_day=1, sellers=("Amazon.in", "Croma"), plan="vivobook15-broad@1"):
    runs = []
    for d, prices in enumerate(prices_by_day):
        for r in range(runs_per_day):
            rows = [synthetic_row(i + 1, s, T, p) for i, (s, p) in enumerate(zip(sellers, prices))]
            runs.append(synthetic_run(f"syn-{plan}-d{d}-r{r}", f"2026-10-0{4 + d}T0{3 + 6 * r}:30:00+00:00",
                                      rows, plan=plan))
    return runs


def test_synthetic_three_days_is_limited_history_with_change_claims(config):
    ledger = build_ledger(synthetic_evidence(*synthetic_days([(72800, 73990), (72500, 73990), (72000, 73990)])), config)
    a = analyse(ledger, BQ224, config, as_of=AS_OF)
    assert a.coverage.level is CoverageLevel.LIMITED_HISTORY
    assert [c.text for c in a.claims if c.kind == "change_since"] == [
        "At Amazon.in the listed price moved from ₹72,800 on 2026-10-04 to ₹72,000 on 2026-10-06 (-1.1%).",
        "At Croma the listed price moved from ₹73,990 on 2026-10-04 to ₹73,990 on 2026-10-06 (0.0%)."]
    assert not {"observed_low", "observed_high", "observed_average"} & set(kinds(a))
    assert a.summary.endswith("Limited history (3 observed calendar days).")


def test_synthetic_six_days_twelve_runs_two_sellers_is_sufficient(config):
    days = [(72800, 73990), (72500, 73990), (72000, 73990), (71500, 73990), (71000, 73990), (70500, 73990)]
    ledger = build_ledger(synthetic_evidence(*synthetic_days(days, runs_per_day=2)), config)
    a = analyse(ledger, BQ224, config, as_of=AS_OF)
    assert a.coverage.level is CoverageLevel.SUFFICIENT_HISTORY
    assert (len(a.coverage.observed_days), len(a.coverage.runs), a.coverage.valid_observations) == (6, 12, 24)
    assert claim(a, "observed_low").params["price_inr"] == 70500
    assert claim(a, "observed_high").params["price_inr"] == 73990
    assert claim(a, "observed_average").params["price_inr"] == 72853.33
    assert claim(a, "observed_average").text.startswith(
        "Based on the observations collected by DealLens over 6 observed calendar days, the average listed price was ₹72,853")


def test_synthetic_related_storefronts_alone_cannot_reach_sufficient(config):
    days = [(73990, 73990)] * 6
    ev = synthetic_evidence(*synthetic_days(days, runs_per_day=2, sellers=("asus.com", "ASUS eshop IN")))
    a = analyse(build_ledger(ev, config), BQ224, config, as_of=AS_OF)
    assert a.coverage.independent_seller_count == 1 and a.coverage.level is CoverageLevel.LIMITED_HISTORY


def test_synthetic_query_plan_versions_are_never_combined(config):
    old = synthetic_days([(72800, 73990), (72500, 73990)], plan="vivobook15-broad@1")
    new = [synthetic_run("syn-v2", "2026-10-07T03:30:00+00:00", [synthetic_row(1, "Amazon.in", T, 71000)],
                         plan="vivobook15-broad@2")]
    a = analyse(build_ledger(synthetic_evidence(*old, *new), config), BQ224, config, as_of=AS_OF)
    assert a.coverage.plan == "vivobook15-broad@2" and a.coverage.other_plans_not_combined == ("vivobook15-broad@1",)
    assert a.coverage.runs == ("syn-v2",) and a.coverage.level is CoverageLevel.NO_HISTORY


def test_as_of_ignores_later_observations(config):
    ledger = build_ledger(synthetic_evidence(*synthetic_days([(72800, 73990), (72000, 73990)])), config)
    a = analyse(ledger, BQ224, config, as_of="2026-10-04T23:00:00+00:00")
    assert a.coverage.observed_days == ("2026-10-04",) and claim(a, "current_lowest_listed").params["price_inr"] == 72800


def test_attributable_exclusions_get_a_product_claim(config):
    rows = [synthetic_row(1, "Amazon.in", T, 72800), synthetic_row(2, "desertcart.in", T, 99000)]
    a = analyse(build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows)), config),
                BQ224, config, as_of=AS_OF)
    c = claim(a, "excluded_count")
    assert c.params["count"] == 1 and c.supporting_observation_ids == ("synthetic/r1.json#2",)


def test_excluded_count_survives_when_every_matched_row_is_excluded(config):
    rows = [synthetic_row(1, "desertcart.in", T, 99000)]      # matched, but cross-border
    a = analyse(build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows)), config),
                BQ224, config, as_of=AS_OF)
    assert a.coverage.valid_observations == 0
    c = claim(a, "excluded_count")
    assert c.params["count"] == 1 and c.supporting_observation_ids == ("synthetic/r1.json#1",)


def test_seller_count_uses_the_latest_run_only(config):
    first = synthetic_run("r1", "2026-10-04T03:30:00+00:00",
                          [synthetic_row(1, "Amazon.in", T, 72800), synthetic_row(2, "Croma", T, 73990)])
    latest = synthetic_run("r2", "2026-10-05T03:30:00+00:00", [synthetic_row(1, "Amazon.in", T, 72500)])
    a = analyse(build_ledger(synthetic_evidence(first, latest), config), BQ224, config, as_of=AS_OF)
    c = claim(a, "seller_count")
    assert c.text == "Observed at 1 storefront, counting as 1 independent seller."
    assert c.params == {"storefronts": 1, "independent": 1}
    assert a.coverage.independent_seller_count == 2          # the whole window still sees both sellers


def test_product_without_observations_says_so(config):
    a = analyse(build_ledger(synthetic_evidence(), config), BQ224, config, as_of=AS_OF)
    assert a.claims == () and a.summary == \
        "No valid observations yet for this product under the current Query Plan. No price history yet."


@pytest.mark.parametrize("text", ["All-time low price", "This is a fake discount", "Price will drop soon",
                                  "Best deal today", "guaranteed lowest"])
def test_forbidden_claim_wording_is_rejected(text):
    with pytest.raises(UnsupportedClaim):
        check_text(text)


def test_coverage_names_the_latest_run(fixture_ledger, config):
    from conftest import BROAD
    assert analyse(fixture_ledger, BQ224, config, as_of=AS_OF).coverage.latest_run_id == f"fixture:{BROAD.name}"
    ledger = build_ledger(synthetic_evidence(*synthetic_days([(72800, 73990), (72500, 73990)])), config)
    assert analyse(ledger, BQ224, config, as_of=AS_OF).coverage.latest_run_id == "syn-vivobook15-broad@1-d1-r0"
    assert analyse(build_ledger(synthetic_evidence(), config), BQ224, config, as_of=AS_OF).coverage.latest_run_id is None
