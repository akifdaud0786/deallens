import dataclasses

from deallens.config import ListingPin
from deallens.domain import MatchOutcome
from deallens.market.matching import match


def test_exact_alias_with_invisible_character_matches_one_product(config):
    m = match("ASUS ‎X1504VAP-BQ224WS Intel Core 5", None, config)
    assert (m.outcome, m.product_key) == (MatchOutcome.MATCHED, "asus-x1504vap-bq224ws")
    assert m.evidence == ({"product_key": "asus-x1504vap-bq224ws", "via": "alias", "alias": "X1504VAP-BQ224WS"},)


def test_family_names_and_longer_model_keys_do_not_match(config):
    assert match("ASUS Vivobook 15 X1504VA Laptop", None, config).outcome is MatchOutcome.UNMATCHED
    assert match("ASUS Vivobook 15 X1504VAP-BQ1341WS", None, config).outcome is MatchOutcome.UNMATCHED
    assert match("X1504VAP-BQ224WSX", None, config).outcome is MatchOutcome.UNMATCHED


def test_synthetic_two_skus_in_one_title_is_ambiguous_and_unattributed(config):
    m = match("Compare ASUS X1504VAP-BQ224WS vs X1504MA-BQ832WS", None, config)
    assert m.outcome is MatchOutcome.AMBIGUOUS and m.product_key is None
    assert m.candidates == ("asus-x1504ma-bq832ws", "asus-x1504vap-bq224ws")


def test_listing_pins_are_ignored_while_pins_are_disabled(config):
    pinned = dataclasses.replace(config, listing_pins=(ListingPin("asus-x1504ma-bq832ws", "L1", "me", "2026-10-03"),))
    assert match("Asus Vivobook 15 2025", "L1", pinned).outcome is MatchOutcome.UNMATCHED
    enabled = dataclasses.replace(pinned, listing_pins_enabled=True)
    assert match("Asus Vivobook 15 2025", "L1", enabled).product_key == "asus-x1504ma-bq832ws"
    assert match("ASUS X1504VAP-BQ224WS", "L1", enabled).outcome is MatchOutcome.AMBIGUOUS
