import dataclasses

from deallens.market.sellers import independent_seller_count, seller_of


def test_storefront_is_its_own_seller_by_default(config):
    assert seller_of("ASUS eshop IN", config.sellers) == "ASUS eshop IN"


def test_explicit_seller_map_merges_storefronts(config):
    merged = dataclasses.replace(config.sellers, storefront_to_seller={"Shopsy By Flipkart": "Flipkart"})
    assert seller_of("Shopsy By Flipkart", merged) == "Flipkart"


def test_unresolved_related_storefronts_count_once(config):
    assert independent_seller_count(["asus.com", "ASUS eshop IN"], config.sellers) == 1
    assert independent_seller_count(["asus.com", "ASUS eshop IN", "Amazon.in"], config.sellers) == 2


def test_related_storefronts_marked_independent_count_separately(config):
    groups = tuple(dataclasses.replace(g, status="independent") for g in config.sellers.related_groups)
    sellers = dataclasses.replace(config.sellers, related_groups=groups)
    assert independent_seller_count(["asus.com", "ASUS eshop IN"], sellers) == 2
