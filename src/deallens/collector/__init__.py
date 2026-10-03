"""Collector: executes one Observation Run with every credit-safety rule.

Writes raw responses and exactly one Run Manifest. Knows nothing about matching, sellers, prices or claims.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from deallens.config import Config
from deallens.domain import RunManifest, RunStatus, SearchAttempt, SearchStatus
from deallens.evidence import EvidenceError, EvidenceStore
from deallens.serpapi import CallBlocked, CallBudget, CreditReadError, SerpApi

log = logging.getLogger(__name__)


IST = ZoneInfo("Asia/Kolkata")


def _ist_slot(target_time: str) -> tuple[str, str]:
    """Canonical IST spelling of a scheduled slot ('2026-10-04T09:00+05:30') and its 'HH:MM:SS.ffffff' clock."""
    t = datetime.fromisoformat(target_time)
    if t.tzinfo is None:
        raise ValueError("scheduled target_time must carry a UTC offset")
    t = t.astimezone(IST)
    return f"{t:%Y-%m-%dT%H:%M}+05:30", f"{t:%H:%M:%S.%f}"


def _run_id(trigger: str, target_time: Optional[str], started_at: str) -> str:
    if trigger == "scheduled":
        if not target_time:
            raise ValueError("scheduled runs need a target_time")
        return f"scheduled-{_ist_slot(target_time)[0]}"      # one id per slot, however the time is spelled
    return f"{trigger}-{started_at}"


def _status(searches) -> RunStatus:
    states = [s.status for s in searches]
    finals = {}
    for s in searches:                      # last attempt per plan decides that plan's result
        finals[s.plan] = s.status
    if not states or all(v is SearchStatus.SKIPPED for v in finals.values()):
        return RunStatus.SKIPPED
    if all(v in (SearchStatus.SUCCEEDED, SearchStatus.REPEAT) for v in finals.values()):
        return RunStatus.COMPLETED
    if all(v is SearchStatus.FAILED for v in finals.values()):
        return RunStatus.FAILED
    return RunStatus.PARTIAL


def collect(config: Config, serpapi: SerpApi, store: EvidenceStore, *, trigger: str,
            target_time: Optional[str], now: Callable[[], str]) -> RunManifest:
    limits = config.collector
    started = now()
    run_id = _run_id(trigger, target_time, started)

    def manifest(status, searches=(), credits=None, reason=None, failure=None):
        return RunManifest(run_id, trigger, target_time, started, now(), status, tuple(searches), credits, reason,
                           dict(config.versions), failure)

    if trigger == "scheduled":
        clock = _ist_slot(target_time)[1]
        if clock[:5] not in limits.scheduled_slots_ist or clock[5:] != ":00.000000":
            log.warning("run %s refused: %s is not a configured IST collection slot", run_id, target_time)
            return manifest(RunStatus.SKIPPED, reason=f"{target_time} is not a configured IST collection slot "
                                                      f"({', '.join(limits.scheduled_slots_ist)} IST)")

    if store.has_run(run_id):
        log.warning("run %s skipped: duplicate run id", run_id)
        return manifest(RunStatus.SKIPPED, reason="duplicate run id: a manifest already exists")

    budget = CallBudget(serpapi, limits.max_calls_per_run, limits.min_remaining)
    try:
        credits = budget.open()
    except CreditReadError as e:
        m = manifest(RunStatus.FAILED, failure=f"credit read failed: {e}")
        store.write_manifest(m)
        log.warning("run %s failed before any paid call: %s", run_id, m.failure_reason)
        return m
    except CallBlocked as e:
        m = manifest(RunStatus.SKIPPED, credits=budget.credits_before, reason=str(e))
        store.write_manifest(m)
        log.warning("run %s skipped: %s", run_id, m.skip_reason)
        return m

    known = store.known_search_ids()
    searches: list[SearchAttempt] = []
    attempt_no = 0
    evidence_lost = False
    for plan in config.active_plans:
        if evidence_lost:
            break
        params = {**plan.params, "no_cache": "true"}
        for attempt in range(1, limits.max_attempts + 1):
            attempt_no += 1
            at = now()

            def skipped(reason):
                return SearchAttempt(attempt_no, plan.ref, params, SearchStatus.SKIPPED, at, error=reason)

            try:
                out = budget.search(params, limits.timeout_s)      # every attempt counts as billed
            except CallBlocked as e:
                searches.append(skipped(str(e)))
                break
            if out.status == "ok":
                sid = (out.body or {}).get("search_metadata", {}).get("id")
                status = SearchStatus.REPEAT if sid in known else SearchStatus.SUCCEEDED
                try:
                    ref = store.write_raw({"run_id": run_id, "kind": "shopping", "plan": plan.ref, "params": params,
                                           "fetched_at": at, "search_id": sid, "status": status.value,
                                           "attempt_no": attempt_no}, out.body, sensitivity="shareable")
                except (EvidenceError, OSError) as e:
                    # The call was (probably) billed but its response is not stored: record that honestly, stop.
                    searches.append(SearchAttempt(attempt_no, plan.ref, params, SearchStatus.FAILED, at, sid,
                                                  error=f"raw write failed after paid call: {e}"))
                    evidence_lost = True
                    break
                known.add(sid)
                searches.append(SearchAttempt(attempt_no, plan.ref, params, status, at, sid, ref))
                break
            searches.append(SearchAttempt(attempt_no, plan.ref, params, SearchStatus.FAILED, at,
                                          error=f"{out.status}: {out.error}"))
            log.warning("run %s plan %s attempt %d failed: %s", run_id, plan.ref, attempt, out.status)
            if not out.retryable:
                break
    m = manifest(_status(searches), searches, credits)
    store.write_manifest(m)
    log.info("run %s finished: %s", run_id, m.status.value)
    return m
