"""Indistinguishable Results policies (ADR 0004). Selected by name from rules.json; replaceable.

A shared fingerprint within one Observation Run means the rows carry no independent price evidence.
It does NOT mean they are the same listing. Google ids are deliberately excluded.
"""
from __future__ import annotations

from typing import Callable, Hashable

from deallens.text import title_tokens


def _storefront_title_prices_v1(run_id, storefront, title, listed_price, list_price) -> Hashable:
    return (run_id, storefront, " ".join(title_tokens(title)), listed_price, list_price)


POLICIES: dict[str, Callable[..., Hashable]] = {"storefront_title_prices@1": _storefront_title_prices_v1}


def policy(name: str) -> Callable[..., Hashable]:
    try:
        return POLICIES[name]
    except KeyError:
        raise ValueError(f"unknown indistinguishable policy {name!r}") from None
