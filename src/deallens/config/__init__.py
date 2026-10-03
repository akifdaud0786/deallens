"""Load and validate config/*.json into one immutable Config. Validates shape, not policy."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from deallens.text import title_tokens


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TrackedProduct:
    product_key: str
    brand: str
    model_key: str
    display_name: str
    aliases: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class ListingPin:
    product_key: str
    listing_ref: str
    pinned_by: str
    pinned_at: str
    note: str = ""


@dataclass(frozen=True)
class QueryPlan:
    plan_id: str
    version: int
    status: str
    effective_from: str
    rationale: str
    params: Mapping[str, str]
    serves: tuple[str, ...]

    @property
    def ref(self) -> str:
        return f"{self.plan_id}@{self.version}"


@dataclass(frozen=True)
class RelatedGroup:
    group_id: str
    storefronts: tuple[str, ...]
    status: str                 # unresolved | independent
    note: str


@dataclass(frozen=True)
class SellerMap:
    version: str
    storefront_to_seller: Mapping[str, str]
    related_groups: tuple[RelatedGroup, ...]


@dataclass(frozen=True)
class Rules:
    version: str
    cross_border_storefront_patterns: tuple[str, ...]
    used_keywords: tuple[str, ...]
    outlier_min_sample: int
    outlier_threshold: float
    indistinguishable_policy: str


@dataclass(frozen=True)
class CoveragePolicy:
    version: str
    limited_min_days: int
    limited_min_runs: int
    sufficient_min_days: int
    sufficient_min_runs: int
    sufficient_min_sellers: int


@dataclass(frozen=True)
class CollectorLimits:
    version: str
    min_remaining: int
    max_calls_per_run: int
    timeout_s: float
    max_attempts: int
    scheduled_slots_ist: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    products: tuple[TrackedProduct, ...]
    listing_pins: tuple[ListingPin, ...]
    listing_pins_enabled: bool
    plans: tuple[QueryPlan, ...]
    sellers: SellerMap
    rules: Rules
    coverage: CoveragePolicy
    collector: CollectorLimits
    versions: Mapping[str, str]

    @property
    def active_plans(self) -> tuple[QueryPlan, ...]:
        """Plans the collector may execute; retired versions stay only for provenance."""
        return tuple(p for p in self.plans if p.status != "retired")

    def plan(self, ref: str) -> Optional[QueryPlan]:
        return next((p for p in self.plans if p.ref == ref), None)


def _read(d: Path, name: str) -> dict:
    try:
        return json.loads((d / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ConfigError(f"{name}: {e}") from e


def load_config(path) -> Config:
    d = Path(path)
    prod, plans, sell, rules, cov, col = (_read(d, n) for n in (
        "products.json", "query_plans.json", "sellers.json", "rules.json", "coverage.json", "collector.json"))
    problems = []

    products = tuple(TrackedProduct(p["product_key"], p["brand"], p["model_key"], p.get("display_name", p["model_key"]),
                                    tuple(p["aliases"]), p["status"]) for p in prod["products"])
    keys = [p.product_key for p in products]
    if len(set(keys)) != len(keys):
        problems.append("duplicate product_key")
    owner = {}
    for p in products:
        for a in p.aliases:
            norm = "".join(title_tokens(a))
            if norm in owner and owner[norm] != p.product_key:
                problems.append(f"alias {a!r} used by {owner[norm]} and {p.product_key}")
            owner[norm] = p.product_key

    qplans = tuple(QueryPlan(q["plan_id"], int(q["version"]), q["status"], q["effective_from"], q.get("rationale", ""),
                             dict(q["params"]), tuple(q["serves"])) for q in plans["plans"])
    for q in qplans:
        for s in q.serves:
            if s not in keys and q.status != "retired":   # retired plans may name retired products
                problems.append(f"plan {q.ref} serves unknown product {s}")
        if "api_key" in q.params:
            problems.append(f"plan {q.ref} must not contain api_key")

    groups = tuple(RelatedGroup(g["group_id"], tuple(g["storefronts"]), g["status"], g.get("note", ""))
                   for g in sell["related_groups"])
    seen = {}
    for g in groups:
        for s in g.storefronts:
            if s in seen:
                problems.append(f"storefront {s} in groups {seen[s]} and {g.group_id}")
            seen[s] = g.group_id

    pins = tuple(ListingPin(**p) for p in prod.get("listing_pins", []))
    for pin in pins:
        if pin.product_key not in keys:
            problems.append(f"listing pin for unknown product {pin.product_key}")

    if problems:
        raise ConfigError("; ".join(problems))

    return Config(
        products=products,
        listing_pins=pins,
        listing_pins_enabled=bool(prod.get("listing_pins_enabled", False)),
        plans=qplans,
        sellers=SellerMap(sell["version"], dict(sell.get("storefront_to_seller", {})), groups),
        rules=Rules(rules["version"], tuple(rules["cross_border_storefront_patterns"]), tuple(rules["used_keywords"]),
                    int(rules["outlier"]["min_sample"]), float(rules["outlier"]["threshold"]),
                    rules["indistinguishable_policy"]),
        coverage=CoveragePolicy(cov["version"], cov["limited_min_days"], cov["limited_min_runs"],
                                cov["sufficient_min_days"], cov["sufficient_min_runs"], cov["sufficient_min_sellers"]),
        collector=CollectorLimits(col["version"], int(col["min_remaining"]), int(col["max_calls_per_run"]),
                                  float(col["timeout_s"]), int(col["max_attempts"]),
                                  tuple(col.get("scheduled_slots_ist", ()))),
        versions={"products": prod["version"], "plans": plans["version"], "sellers": sell["version"],
                  "rules": rules["version"], "coverage": cov["version"], "collector": col["version"]},
    )
