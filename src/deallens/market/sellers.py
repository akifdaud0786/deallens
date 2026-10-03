"""Storefront -> Seller mapping and Independent Seller Count (Related Storefront groups count once)."""
from __future__ import annotations

from typing import Iterable, Optional

from deallens.config import SellerMap


def seller_of(storefront: Optional[str], seller_map: SellerMap) -> Optional[str]:
    if storefront is None:
        return None
    return seller_map.storefront_to_seller.get(storefront, storefront)


def independent_seller_count(seller_keys: Iterable[str], seller_map: SellerMap) -> int:
    units = set()
    for s in seller_keys:
        group = next((g for g in seller_map.related_groups if s in g.storefronts and g.status != "independent"), None)
        units.add(("group", group.group_id) if group else ("seller", s))
    return len(units)
