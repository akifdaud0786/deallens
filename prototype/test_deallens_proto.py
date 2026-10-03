"""PROTOTYPE tests (requested by the user for this phase) — domain behaviour on the real 3 Oct fixtures."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import deallens_proto as dl  # noqa: E402
import proto_config as cfg  # noqa: E402

CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"
BROAD = CACHE / "20261003T140442Z_shopping.json"
REPEAT = CACHE / "20261003T140455Z_shopping.json"
MODEL_QUERY = CACHE / "20261003T144432Z_shopping.json"


@pytest.fixture(scope="module")
def res():
    return dl.run_pipeline([BROAD, REPEAT, MODEL_QUERY], cfg)


def obs(res, ref, pos):
    return next(o for o in res["observations"] if o["observation_id"] == f"{ref.name}#{pos}")


def analysis(res, model_key):
    return next(a for a in res["analyses"] if a["product"]["model_key"] == model_key)


# 1. matched
def test_matched_observation_from_real_fixture(res):
    o = obs(res, BROAD, 5)  # Amazon.in 'ASUS ‎X1504VAP-BQ224WS ...'
    assert o["match"]["outcome"] == "matched"
    assert o["match"]["product_key"] == "asus-x1504vap-bq224ws"
    assert o["included"] and o["reasons"] == []


# 2. unmatched stays visible
def test_unmatched_observation_is_kept_and_excluded(res):
    o = obs(res, BROAD, 1)  # ubuy NEW 2025 ASUS VivoBook ... no model key
    assert o["match"]["outcome"] == "unmatched"
    assert not o["included"] and "unmatched" in o["reasons"]
    assert len(res["observations"]) == 80  # nothing silently dropped (40 + 0 repeat + 40)


def test_alias_does_not_match_a_longer_model_key():
    o = {"title": "ASUS Vivobook 15 X1504VAP-BQ1341WS", "listing_ref": "x"}
    assert dl.match(o, cfg.TRACKED_PRODUCTS, [])["outcome"] == "unmatched"
    o = {"title": "ASUS Vivobook 15 X1504VA Laptop", "listing_ref": "x"}  # Microless row, family only
    assert dl.match(o, cfg.TRACKED_PRODUCTS, [])["outcome"] == "unmatched"


# 3. ambiguous — SYNTHETIC: no real fixture row contains two SKUs; built from two real aliases
def test_synthetic_ambiguous_observation_is_never_attributed():
    o = {"observation_id": "synthetic#1", "raw_ref": "synthetic", "run_id": "synthetic", "list_price_inr": None, "storefront": "Example", "title":
         "Compare ASUS X1504VAP-BQ224WS vs X1504VAP-BQ541WS", "listing_ref": "x", "listed_price_inr": 70000,
         "price_raw": "₹70,000", "alternative_price": None}
    dl.classify([o], cfg.TRACKED_PRODUCTS, [], cfg.SELLER_MAP, cfg.CROSS_BORDER, cfg.RULES)
    assert o["match"]["outcome"] == "ambiguous"
    assert o["match"]["product_key"] is None
    assert o["match"]["candidates"] == ["asus-x1504vap-bq224ws", "asus-x1504vap-bq541ws"]
    assert not o["included"] and "ambiguous" in o["reasons"]


def test_pin_plus_alias_of_another_product_is_ambiguous():
    o = {"title": "ASUS X1504VAP-BQ224WS", "listing_ref": "L1"}
    pins = [{"listing_ref": "L1", "product_key": "asus-x1504vap-bq541ws"}]
    assert dl.match(o, cfg.TRACKED_PRODUCTS, pins)["outcome"] == "ambiguous"


# 4. duplicates: LowestRate x6 (different product_ids AND different Google offer ids) and the repeated search_id
def test_lowestrate_indistinguishable_rows_count_once(res):
    rows = [o for o in res["observations"] if o["raw_ref"] == BROAD.name and o["storefront"] == "LowestRate Shopping"]
    assert len(rows) == 6
    assert len({o["listing_ref"] for o in rows}) == 6  # product_id cannot be the dedup key
    assert len({o["google_ids"]["headlineOfferDocid"] for o in rows}) == 6  # Google treats them as 6 offers
    assert sum("indistinguishable_in_run" not in o["reasons"] for o in rows) == 1
    assert sum("indistinguishable_in_run" in o["reasons"] for o in rows) == 5


def test_same_product_id_with_different_prices_is_not_collapsed(res):
    rows = [o for o in res["observations"] if o["listing_ref"] == "16994291886277941050"]  # JanSport, Test 3 fixture
    assert len(rows) == 4 and len({o["listed_price_inr"] for o in rows}) == 4
    assert not any("indistinguishable_in_run" in o["reasons"] for o in rows)
    assert {o["google_ids"]["catalogid"] for o in rows} == {"16994291886277941050"}  # product_id == Google catalog id


def test_spread_wording_when_prices_are_equal(res):
    spread = next(c for c in analysis(res, "X1504VAP-BQ541WS")["claims"] if c["kind"] == "current_spread")
    assert "range from" not in spread["text"]
    assert spread["text"] == "Observed listed prices are ₹73,990 across the included sellers in the latest run."
    spread = next(c for c in analysis(res, "X1504VAP-BQ224WS")["claims"] if c["kind"] == "current_spread")
    assert spread["text"] == "Listed prices in the latest run range from ₹72,800 to ₹73,990."


def test_no_product_level_exclusion_claim_without_attributable_exclusions(res):
    for a in res["analyses"]:
        assert not [c for c in a["claims"] if c["kind"] == "excluded_count"]


def test_repeated_search_id_creates_no_observations(res):
    rep = next(r for r in res["raws"] if r["raw_ref"] == REPEAT.name)
    assert rep["repeat_response"] is True and rep["observation_count"] == 0
    assert not [o for o in res["observations"] if o["raw_ref"] == REPEAT.name]


# 5. cross-border
def test_cross_border_by_alternative_currency_and_pattern(res):
    sa = obs(res, BROAD, 6)  # desertcart.com.sa, SAR alternative_price
    assert sa["storefront"] == "desertcart.com.sa" and "cross_border" in sa["reasons"]
    igeek = next(o for o in res["observations"] if o["storefront"] == "iGeek Megastore")  # JOD; name gives no hint
    assert "cross_border" in igeek["reasons"]


# 6. old_price parsing
@pytest.mark.parametrize("raw,price,pct,status", [
    ("11% off₹68,999", 68999, 11.0, "parsed"),
    ("₹68,999", 68999, None, "parsed"),
    ("15% off ₹72,999", 72999, 15.0, "parsed"),
    ("₹1,16,076.50", 116076.5, None, "parsed"),
    (None, None, None, "absent"),
    ("was SAR 2,800", None, None, "unparsed"),
    ("₹68,999 ₹72,999", None, None, "unparsed"),
    ("", None, None, "unparsed"),
])
def test_old_price_parsing(raw, price, pct, status):
    assert dl.parse_list_price(raw) == {"list_price_inr": price, "discount_pct": pct, "parse_status": status}


def test_extracted_old_price_is_ignored(res):
    o = obs(res, BROAD, 7)  # Flipkart: extracted_old_price == 11 in raw
    assert o["list_price_inr"] == 68999 and o["discount_pct"] == 11.0


# 7. related storefronts
def test_related_storefronts_count_once_unless_independent(res):
    assert analysis(res, "X1504VAP-BQ541WS")["coverage"]["independent_seller_count"] == 1
    assert analysis(res, "X1504VAP-BQ224WS")["coverage"]["independent_seller_count"] == 2
    independent = {**cfg.SELLER_MAP, "related_groups": [{**g, "status": "independent"} for g in cfg.SELLER_MAP["related_groups"]]}
    assert dl.independent_seller_count(["asus.com", "ASUS eshop IN"], independent) == 2


# 8. observed_day
def test_observed_day_is_ist_and_fetched_at_is_kept(res):
    assert dl.observed_day("2026-10-03T19:00:00+00:00") == "2026-10-04"  # 00:30 IST next day
    assert dl.observed_day("2026-10-03T18:29:59+00:00") == "2026-10-03"
    o = obs(res, BROAD, 5)
    assert o["fetched_at"] == "2026-10-03T14:04:42.517480+00:00" and o["observed_day"] == "2026-10-03"


# 9. coverage gating
def test_fixtures_only_support_current_market_claims(res):
    for a in res["analyses"]:
        assert a["coverage"]["level"] == "no_history"
        assert {c["min_level"] for c in a["claims"]} == {"no_history"}
        assert a["summary"].endswith("No price history yet.")
        for c in a["claims"]:
            assert not dl.FORBIDDEN.search(c["text"])


def test_unplanned_probe_is_not_counted_as_a_run(res):
    probe = next(r for r in res["raws"] if r["raw_ref"] == MODEL_QUERY.name)
    assert probe["plan"] is None
    for a in res["analyses"]:
        assert a["coverage"]["runs"] == [f"probe:{BROAD.name}"]
    assert {r["run_source"] for r in res["raws"]} == {"manifest_less_probe"}


# 10. provenance
def test_every_claim_traces_to_raw_response(res):
    by_id = {o["observation_id"]: o for o in res["observations"]}
    shas = {r["raw_ref"]: r["sha256"] for r in res["raws"]}
    for a in res["analyses"]:
        for c in a["claims"]:
            assert c["supporting_observation_ids"]
            for p in c["provenance"]:
                o = by_id[p["observation_id"]]
                assert p["raw_ref"] == o["raw_ref"] and p["raw_sha256"] == shas[o["raw_ref"]]
                assert p["search_id"] and p["storefront"] and p["fetched_at"]
            assert c["claim_id"] in a["summary"]
