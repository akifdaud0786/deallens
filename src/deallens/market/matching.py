"""Deterministic attribution of a listing title to Tracked Products (ADR 0003). No fuzzy/embedding/LLM matching."""
from __future__ import annotations

from typing import Optional

from deallens.config import Config
from deallens.domain import Match, MatchOutcome
from deallens.text import title_tokens

MAX_ALIAS_TOKENS = 4


def _contains(tokens: tuple[str, ...], alias: str) -> bool:
    """Alias found as a whole run of adjacent title tokens, so X1504VA never matches X1504VAP."""
    target = "".join(title_tokens(alias))
    return any("".join(tokens[i:i + n]) == target
               for i in range(len(tokens)) for n in range(1, MAX_ALIAS_TOKENS + 1))


def match(title: str, listing_ref: Optional[str], config: Config) -> Match:
    tokens = title_tokens(title)
    evidence = [{"product_key": p.product_key, "via": "alias", "alias": a}
                for p in config.products for a in p.aliases if _contains(tokens, a)]
    if config.listing_pins_enabled and listing_ref:
        evidence += [{"product_key": pin.product_key, "via": "pin", "listing_ref": pin.listing_ref}
                     for pin in config.listing_pins if pin.listing_ref == listing_ref]
    candidates = tuple(sorted({e["product_key"] for e in evidence}))
    if not candidates:
        return Match(MatchOutcome.UNMATCHED, None, (), ())
    if len(candidates) == 1:
        return Match(MatchOutcome.MATCHED, candidates[0], candidates, tuple(evidence))
    return Match(MatchOutcome.AMBIGUOUS, None, candidates, tuple(evidence))
