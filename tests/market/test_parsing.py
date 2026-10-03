import pytest

from deallens.market import parsing


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
def test_list_price_is_parsed_deterministically_from_old_price(raw, price, pct, status):
    lp = parsing.parse_list_price(raw)
    assert (lp.list_price_inr, lp.discount_pct, lp.parse_status) == (price, pct, status)


@pytest.mark.parametrize("raw,expected", [
    ("₹1,16,076", 116076), ("₹72,051.94", 72051.94), ("₹61,599", 61599), ("SAR 2,800", None), (None, None), ("", None),
])
def test_inr_price_parsing(raw, expected):
    assert parsing.parse_inr(raw) == expected


def test_title_tokens_strip_invisible_characters():
    assert parsing.title_tokens("ASUS ‎X1504VAP-BQ224WS Intel") == ("ASUS", "X1504VAP", "BQ224WS", "INTEL")


def test_google_ids_are_read_from_product_link():
    link = ("https://www.google.co.in/search?ibp=oshop&q=x&prds=catalogid:5432821007270738963,"
            "productid:16516639321499895759,headlineOfferDocid:14130856623982048097,imageDocid:9,pvt:hg&hl=en")
    assert parsing.google_ids("5432821007270738963", link) == {
        "product_id": "5432821007270738963", "catalogid": "5432821007270738963",
        "productid": "16516639321499895759", "headlineOfferDocid": "14130856623982048097"}
    assert parsing.google_ids("7", None) == {"product_id": "7"}


def test_observed_day_is_the_india_calendar_date():
    assert parsing.observed_day("2026-10-03T19:00:00+00:00") == "2026-10-04"
    assert parsing.observed_day("2026-10-03T18:29:59+00:00") == "2026-10-03"
