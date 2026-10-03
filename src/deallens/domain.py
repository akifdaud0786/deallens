"""DealLens domain vocabulary (see GLOSSARY.md). Frozen data only: no I/O, no configuration values."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class SearchStatus(str, Enum):
    SUCCEEDED = "succeeded"
    REPEAT = "repeat"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunSource(str, Enum):
    MANIFEST = "manifest"
    MANIFEST_LESS_PROBE = "manifest_less_probe"
    ORPHAN = "orphan"


class MatchOutcome(str, Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"


class Reason(str, Enum):
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"
    CROSS_BORDER = "cross_border"
    USED_OR_REFURBISHED = "used_or_refurbished"
    UNPRICED = "unpriced"
    NON_INR = "non_inr"
    INDISTINGUISHABLE_IN_RUN = "indistinguishable_in_run"
    OUTLIER = "outlier"
    ORPHAN_RAW = "orphan_raw"
    INTEGRITY_FAILED = "integrity_failed"
    DEVELOPMENT_PROBE = "development_probe"


class CoverageLevel(str, Enum):
    NO_HISTORY = "no_history"
    LIMITED_HISTORY = "limited_history"
    SUFFICIENT_HISTORY = "sufficient_history"

    @property
    def rank(self) -> int:
        return list(CoverageLevel).index(self)


# ---------- Evidence ----------

@dataclass(frozen=True)
class RawRef:
    path: str          # relative to the project root, forward slashes
    sha256: str


@dataclass(frozen=True)
class SearchAttempt:
    attempt_no: int
    plan: Optional[str]                 # "plan_id@version"
    params: Mapping[str, str]           # never contains api_key
    status: SearchStatus
    started_at: str                     # UTC ISO
    search_id: Optional[str] = None
    raw_ref: Optional[RawRef] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    trigger: str                        # scheduled | manual
    target_time: Optional[str]
    started_at: str
    finished_at: str
    status: RunStatus
    searches: tuple[SearchAttempt, ...] = ()
    credits_before: Optional[int] = None
    skip_reason: Optional[str] = None
    config_versions: Mapping[str, str] = field(default_factory=dict)
    failure_reason: Optional[str] = None


@dataclass(frozen=True)
class RawRecord:
    ref: RawRef
    meta: Mapping[str, Any]
    response: Mapping[str, Any]
    run_id: str
    run_source: RunSource
    sensitivity: str                    # shareable | private
    hash_verified: Optional[bool] = None   # True/False when a manifest recorded the hash; None if unverifiable


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    source: RunSource
    status: Optional[RunStatus] = None


@dataclass(frozen=True)
class EvidenceSet:
    manifests: tuple[RunManifest, ...]
    raws: tuple[RawRecord, ...]
    missing_probes: tuple[str, ...] = ()      # registered probe paths absent from this checkout

    @property
    def orphans(self) -> tuple[RawRecord, ...]:
        return tuple(r for r in self.raws if r.run_source is RunSource.ORPHAN)


# ---------- Market ----------

@dataclass(frozen=True)
class ListPrice:
    list_price_inr: Optional[float]
    discount_pct: Optional[float]
    parse_status: str                   # parsed | absent | unparsed


@dataclass(frozen=True)
class Match:
    outcome: MatchOutcome
    product_key: Optional[str]
    candidates: tuple[str, ...]
    evidence: tuple[Mapping[str, str], ...] = ()


@dataclass(frozen=True)
class Observation:
    observation_id: str
    raw_ref: RawRef
    run_id: str
    run_source: RunSource
    search_id: Optional[str]
    plan: Optional[str]
    fetched_at: str                     # UTC ISO, authoritative
    observed_day: str                   # Asia/Kolkata date, derived
    position: int
    storefront: Optional[str]
    seller_key: Optional[str]
    title: str
    google_ids: Mapping[str, str]       # provenance only
    listed_price_inr: Optional[float]
    price_raw: Optional[str]
    list_price: ListPrice
    list_price_raw: Optional[str]
    alternative_price: Optional[Mapping[str, Any]]
    delivery_raw: Optional[str]
    rating: Optional[float]
    reviews: Optional[int]
    second_hand_condition: Optional[str]
    immersive_page_token: Optional[str]
    match: Match
    included: bool
    reasons: tuple[Reason, ...]
    config_versions: Mapping[str, str]
    stock_status: str = "unknown"
    outlier_check: Optional[str] = None


@dataclass(frozen=True)
class Ledger:
    observations: tuple[Observation, ...]
    runs: tuple[RunInfo, ...]
    raws: tuple[RawRecord, ...]
    config_versions: Mapping[str, str]

    def for_product(self, product_key: str) -> tuple[Observation, ...]:
        return tuple(o for o in self.observations if o.match.product_key == product_key)

    def unattributed(self) -> tuple[Observation, ...]:
        return tuple(o for o in self.observations if o.match.outcome is not MatchOutcome.MATCHED)

    def get(self, observation_id: str) -> Observation:
        return next(o for o in self.observations if o.observation_id == observation_id)


# ---------- Analysis ----------

@dataclass(frozen=True)
class Coverage:
    product_key: str
    plan: Optional[str]
    other_plans_not_combined: tuple[str, ...]
    observed_days: tuple[str, ...]
    runs: tuple[str, ...]
    runs_searched: tuple[str, ...]
    sellers: tuple[str, ...]
    independent_seller_count: int
    valid_observations: int
    level: CoverageLevel
    observation_ids: tuple[str, ...]
    latest_run_id: Optional[str] = None      # run of the most recent included Observation in this plan


@dataclass(frozen=True)
class Provenance:
    observation_id: str
    raw_path: str
    raw_sha256: str
    run_id: str
    run_source: RunSource
    search_id: Optional[str]
    storefront: Optional[str]
    fetched_at: str


@dataclass(frozen=True)
class Claim:
    claim_id: str
    kind: str
    text: str
    params: Mapping[str, Any]
    supporting_observation_ids: tuple[str, ...]
    provenance: tuple[Provenance, ...]
    min_level: CoverageLevel


@dataclass(frozen=True)
class DealAnalysis:
    product_key: str
    as_of: str
    coverage: Coverage
    claims: tuple[Claim, ...]
    summary: str
    summary_source: str                 # template | llm
    config_versions: Mapping[str, str]


# ---------- Investigation ----------

@dataclass(frozen=True)
class Offer:
    name: Optional[str]
    price_raw: Optional[str]
    listed_price_inr: Optional[float]
    total_inr: Optional[float]
    shipping: Optional[str]
    stock_text: tuple[str, ...]
    link: Optional[str]


@dataclass(frozen=True)
class Investigation:
    investigation_id: str
    observation_id: str
    fetched_at: str
    status: SearchStatus
    raw_ref: Optional[RawRef]
    offers: tuple[Offer, ...]
    title: Optional[str] = None
    error: Optional[str] = None
