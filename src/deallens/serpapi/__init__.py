"""SerpApi port. Adapters: `serpapi.http.HttpSerpApi` (live, constructed only by the CLI) and `FixtureSerpApi`.

The port never decides anything about products, sellers or prices, and never raises for API or transport
failures: those come back as a `SearchOutcome` status.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Protocol, Sequence

OK, API_ERROR, TRANSPORT_ERROR, TIMEOUT = "ok", "api_error", "transport_error", "timeout"
INVALID_RESPONSE = "invalid_response"     # body arrived but is not JSON: may be billed, never retried


@dataclass(frozen=True)
class SearchOutcome:
    status: str                                   # ok | api_error | transport_error | timeout | invalid_response
    body: Optional[Mapping[str, Any]] = field(default=None, repr=False)
    error: Optional[str] = None
    http_status: Optional[int] = None

    @classmethod
    def ok(cls, body: Mapping[str, Any]) -> "SearchOutcome":
        return cls(OK, body)

    @classmethod
    def failure(cls, status: str, error: str, http_status: Optional[int] = None) -> "SearchOutcome":
        return cls(status, None, error, http_status)

    @property
    def retryable(self) -> bool:
        return self.status in (TRANSPORT_ERROR, TIMEOUT)


@dataclass(frozen=True)
class CreditReading:
    plan_searches_left: int
    this_month_usage: Optional[int]
    read_at: str


class CreditReadError(RuntimeError):
    """The free Account API could not be read; message is already redacted."""


class SerpApi(Protocol):
    def search(self, params: Mapping[str, str], timeout_s: float) -> SearchOutcome: ...

    def credits(self) -> CreditReading: ...


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class FixtureSerpApi:
    """Replays scripted outcomes. Never billed. Used by tests and offline demos."""

    def __init__(self, outcomes: Sequence[SearchOutcome] = (), credits: int = 250,
                 credits_error: Optional[Exception] = None):
        self._outcomes = list(outcomes)
        self._credits = credits
        self._credits_error = credits_error
        self.calls: list[dict] = []

    def search(self, params: Mapping[str, str], timeout_s: float) -> SearchOutcome:
        self.calls.append(dict(params))
        assert self._outcomes, "unexpected SerpApi call: no scripted outcome left"
        return self._outcomes.pop(0)

    def credits(self) -> CreditReading:
        if self._credits_error is not None:
            raise CreditReadError(str(self._credits_error))
        return CreditReading(self._credits, None, now_utc())


class CallBlocked(RuntimeError):
    """A paid call was refused by the call budget or the credit guard."""


class CallBudget:
    """The single gate for paid calls: credit guard + hard call cap (codebase-design §11).

    `open()` reads credits once (free) and refuses when below `min_remaining`. Every `search()` then counts as
    billed, so the guard tightens as calls are made: no caller can exceed `max_calls` or dip below the minimum.
    """

    def __init__(self, api: SerpApi, max_calls: int, min_remaining: int):
        self._api, self.max_calls, self.min_remaining = api, max_calls, min_remaining
        self.used = 0
        self.credits_before: Optional[int] = None

    def open(self) -> int:
        """Reads credits (raises CreditReadError) and raises CallBlocked if already below the minimum."""
        self.credits_before = self._api.credits().plan_searches_left
        if self.credits_before < self.min_remaining:
            raise CallBlocked(self.blocked_reason())
        return self.credits_before

    def blocked_reason(self) -> Optional[str]:
        if self.credits_before is None:
            return "credit guard: credits not read"
        if self.used >= self.max_calls:
            return f"call budget of {self.max_calls} exhausted"
        remaining = self.credits_before - self.used
        if remaining < self.min_remaining:
            return f"credit guard: remaining {remaining} < minimum {self.min_remaining}"
        return None

    def search(self, params: Mapping[str, str], timeout_s: float) -> SearchOutcome:
        reason = self.blocked_reason()
        if reason:
            raise CallBlocked(reason)
        self.used += 1
        return self._api.search(params, timeout_s)
