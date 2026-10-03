from collections import Counter

from conftest import BROAD, MODEL_QUERY, REPEAT
from deallens.domain import MatchOutcome, Reason, RunSource
from deallens.market import build_ledger
from synthetic import synthetic_evidence, synthetic_row, synthetic_run


def obs(ledger, f, pos):
    return next(o for o in ledger.observations if o.raw_ref.path.endswith(f.name) and o.position == pos)


def test_every_row_of_every_non_repeat_response_is_kept(probe_ledger):
    assert len(probe_ledger.observations) == 80
    c = Counter(o.match.outcome for o in probe_ledger.observations)
    # watchlist products-2: BQ224WS x2, NJ2324WS x1, BQ832WS x1 matched; the BQ541WS rows are now unmatched
    assert c == {MatchOutcome.UNMATCHED: 76, MatchOutcome.MATCHED: 4}


def test_repeat_response_creates_no_observations(probe_ledger):
    assert not [o for o in probe_ledger.observations if o.raw_ref.path.endswith(REPEAT.name)]


def test_matched_row_is_attributed_and_included(fixture_ledger):
    o = obs(fixture_ledger, BROAD, 5)
    assert o.storefront == "Amazon.in" and o.match.product_key == "asus-x1504vap-bq224ws"
    assert o.included and o.reasons == () and o.listed_price_inr == 72800


def test_unmatched_rows_stay_inspectable(probe_ledger):
    o = obs(probe_ledger, BROAD, 1)
    assert o.match.outcome is MatchOutcome.UNMATCHED and not o.included and Reason.UNMATCHED in o.reasons
    assert o in probe_ledger.unattributed()


def test_list_price_comes_from_old_price_not_extracted_old_price(probe_ledger):
    o = obs(probe_ledger, BROAD, 7)
    assert o.list_price_raw == "11% off₹68,999"
    assert (o.list_price.list_price_inr, o.list_price.discount_pct) == (68999, 11.0)


def test_google_ids_are_provenance_and_product_id_is_the_catalog_or_product_id(probe_ledger):
    for o in probe_ledger.observations:
        g = o.google_ids
        assert g["product_id"] == (g.get("catalogid") or g.get("productid"))


def test_lowestrate_indistinguishable_rows_count_once(probe_ledger):
    rows = [o for o in probe_ledger.observations if o.storefront == "LowestRate Shopping"]
    assert len(rows) == 6 and len({o.google_ids["headlineOfferDocid"] for o in rows}) == 6
    assert sum(Reason.INDISTINGUISHABLE_IN_RUN in o.reasons for o in rows) == 5


def test_rows_with_different_prices_are_never_collapsed(probe_ledger):
    rows = [o for o in probe_ledger.observations if o.google_ids.get("product_id") == "16994291886277941050"]
    assert len(rows) == 4 and len({o.listed_price_inr for o in rows}) == 4
    assert not any(Reason.INDISTINGUISHABLE_IN_RUN in o.reasons for o in rows)


def test_cross_border_by_foreign_currency_or_known_storefront(probe_ledger):
    assert Reason.CROSS_BORDER in obs(probe_ledger, BROAD, 6).reasons            # desertcart.com.sa, SAR
    igeek = next(o for o in probe_ledger.observations if o.storefront == "iGeek Megastore")
    assert Reason.CROSS_BORDER in igeek.reasons                                   # JOD; name gives no hint


def test_times_are_kept_in_utc_with_a_derived_india_day(probe_ledger):
    o = obs(probe_ledger, BROAD, 5)
    assert o.fetched_at == "2026-10-03T14:04:42.517480+00:00" and o.observed_day == "2026-10-03"


def test_probes_are_labelled_and_plans_resolved(probe_ledger):
    assert {o.run_source for o in probe_ledger.observations} == {RunSource.MANIFEST_LESS_PROBE}
    assert obs(probe_ledger, BROAD, 5).plan == "vivobook15-broad@1"
    assert obs(probe_ledger, MODEL_QUERY, 1).plan is None
    assert obs(probe_ledger, BROAD, 5).config_versions["rules"] == "rules-1"


def test_same_row_in_two_runs_is_two_observations(config):
    row = synthetic_row(1, "Amazon.in", "ASUS X1504VAP-BQ224WS", 72800)
    ev = synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", [row]),
                            synthetic_run("r2", "2026-10-04T09:30:00+00:00", [row]))
    assert [o.included for o in build_ledger(ev, config).observations] == [True, True]


def test_synthetic_ambiguous_row_is_kept_and_excluded(config):
    row = synthetic_row(1, "Example", "Compare X1504VAP-BQ224WS vs X1504MA-BQ832WS", 70000)
    ledger = build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", [row])), config)
    (o,) = ledger.observations
    assert o.match.outcome is MatchOutcome.AMBIGUOUS and o.reasons == (Reason.AMBIGUOUS,)


def test_used_and_unpriced_rows_are_excluded_with_reasons(config):
    rows = [synthetic_row(1, "Amazon.in", "Renewed ASUS X1504VAP-BQ224WS", 50000),
            {**synthetic_row(2, "Croma", "ASUS X1504VAP-BQ224WS", 1), "extracted_price": None, "price": None}]
    a, b = build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows)), config).observations
    assert a.reasons == (Reason.USED_OR_REFURBISHED,) and b.reasons == (Reason.UNPRICED,)


def test_orphan_raws_are_visible_but_never_count(config):
    rows = [synthetic_row(1, "Amazon.in", "X1504VAP-BQ224WS", 1)]
    raw, _ = synthetic_run("crashed", "2026-10-04T03:30:00+00:00", rows, source=RunSource.ORPHAN)
    ledger = build_ledger(synthetic_evidence(orphans=[raw]), config)
    (o,) = ledger.observations
    assert Reason.ORPHAN_RAW in o.reasons and not o.included
    assert [r.run_id for r in ledger.runs] == []


def test_outliers_are_flagged_only_with_enough_observations(config):
    title = "ASUS X1504VAP-BQ224WS"
    rows = [synthetic_row(i, f"Shop{i}", title, p) for i, p in enumerate([72000, 72500, 73000, 73500, 120000], 1)]
    ledger = build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows)), config)
    assert [Reason.OUTLIER in o.reasons for o in ledger.observations] == [False] * 4 + [True]
    few = build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows[3:])), config)
    assert not any(Reason.OUTLIER in o.reasons for o in few.observations)
    assert "not applied" in few.observations[0].outlier_check


def test_tampered_raw_is_excluded_from_statistics(config):
    rows = [synthetic_row(1, "Amazon.in", "ASUS X1504VAP-BQ224WS", 72800)]
    tampered = synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows, hash_verified=False)
    intact = synthetic_run("r2", "2026-10-04T09:30:00+00:00", rows, hash_verified=True)
    a, b = build_ledger(synthetic_evidence(tampered, intact), config).observations
    assert a.reasons == (Reason.INTEGRITY_FAILED,) and not a.included      # kept, visible, excluded
    assert b.included                                                       # verified raw unaffected
    unverifiable = synthetic_run("r3", "2026-10-04T15:30:00+00:00", rows, hash_verified=None)
    (c,) = build_ledger(synthetic_evidence(unverifiable), config).observations
    assert c.included                                                       # no recorded hash != failed
