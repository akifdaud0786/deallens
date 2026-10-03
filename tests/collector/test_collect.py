import dataclasses
import io
import json
import logging

import pytest

from deallens.collector import collect
from deallens.domain import RunStatus, SearchStatus
from deallens.evidence import EvidenceStore
from deallens.serpapi import FixtureSerpApi, SearchOutcome
from deallens.serpapi.http import HttpSerpApi

SLOT = "2026-10-04T09:00+05:30"
KEY = "k3y-THAT-must-never-leak-0123456789"


def clock():
    t = iter(f"2026-10-04T03:30:{s:02d}+00:00" for s in range(60))
    return lambda: next(t)


def ok(sid="s1"):
    return SearchOutcome.ok({"search_metadata": {"id": sid, "status": "Success"}, "shopping_results": []})


@pytest.fixture
def store(tmp_path):
    return EvidenceStore(tmp_path)


def run(config, api, store, **kw):
    return collect(config, api, store, trigger=kw.pop("trigger", "scheduled"), target_time=kw.pop("target_time", SLOT),
                   now=kw.pop("now", clock()))


def with_plans(config, n):
    p = config.active_plans[0]
    return dataclasses.replace(config, plans=tuple(dataclasses.replace(p, plan_id=f"plan{i}") for i in range(n)))


def test_successful_run_writes_raw_evidence_and_exactly_one_manifest(config, store, tmp_path):
    m = run(config, FixtureSerpApi([ok()], credits=247), store)
    assert m.status is RunStatus.COMPLETED and m.run_id == f"scheduled-{SLOT}" and m.credits_before == 247
    (s,) = m.searches
    assert s.status is SearchStatus.SUCCEEDED and s.search_id == "s1" and s.plan == "vivobook15-broad@2"
    raw = json.loads((tmp_path / s.raw_ref.path).read_text(encoding="utf-8"))
    assert raw["meta"]["run_id"] == m.run_id and raw["meta"]["params"]["no_cache"] == "true"
    assert "api_key" not in raw["meta"]["params"]
    assert len(list((tmp_path / "data/evidence/manifests").glob("*.json"))) == 1


def test_duplicate_scheduled_slot_is_skipped_without_calls(config, store, tmp_path):
    run(config, FixtureSerpApi([ok()]), store)
    api = FixtureSerpApi([])
    m = run(config, api, store)
    assert m.status is RunStatus.SKIPPED and "duplicate" in m.skip_reason and api.calls == []
    assert len(list((tmp_path / "data/evidence/manifests").glob("*.json"))) == 1


def test_api_error_fails_the_search_without_retry(config, store):
    api = FixtureSerpApi([SearchOutcome.failure("api_error", "Invalid API key")])
    m = run(config, api, store)
    assert len(api.calls) == 1 and m.status is RunStatus.FAILED
    assert m.searches[0].status is SearchStatus.FAILED and m.searches[0].raw_ref is None


def two_attempts(config):
    return dataclasses.replace(config, collector=dataclasses.replace(config.collector, max_attempts=2))


def test_transport_failure_is_retried_within_the_attempt_limit(config, store):
    api = FixtureSerpApi([SearchOutcome.failure("timeout", "slow"), ok()])
    m = run(two_attempts(config), api, store)
    assert [s.status for s in m.searches] == [SearchStatus.FAILED, SearchStatus.SUCCEEDED]
    assert m.status is RunStatus.COMPLETED


def test_retries_stop_at_max_attempts(config, store):
    api = FixtureSerpApi([SearchOutcome.failure("transport_error", "x")] * 5)
    m = run(two_attempts(config), api, store)
    assert len(api.calls) == 2 and m.status is RunStatus.FAILED


@pytest.mark.parametrize("credits,calls,status", [(59, 0, RunStatus.SKIPPED), (60, 1, RunStatus.COMPLETED)])
def test_credit_guard_blocks_runs_below_the_minimum(config, store, credits, calls, status):
    api = FixtureSerpApi([ok()], credits=credits)
    m = run(config, api, store)
    assert len(api.calls) == calls and m.status is status and m.credits_before == credits
    if status is RunStatus.SKIPPED:
        assert "remaining" in m.skip_reason and store.has_run(m.run_id)


def test_guard_counts_calls_already_made_in_the_run(config, store):
    api = FixtureSerpApi([ok("a"), ok("b"), ok("c")], credits=61)
    m = run(with_plans(config, 3), api, store)
    assert len(api.calls) == 2 and m.status is RunStatus.PARTIAL
    assert m.searches[-1].status is SearchStatus.SKIPPED and "remaining" in m.searches[-1].error


def test_call_budget_caps_calls_per_run(config, store):
    api = FixtureSerpApi([ok(c) for c in "abcd"], credits=247)
    m = run(with_plans(config, 4), api, store)
    assert len(api.calls) == config.collector.max_calls_per_run == 3
    assert m.searches[-1].status is SearchStatus.SKIPPED and "budget" in m.searches[-1].error


def test_already_recorded_search_id_is_a_repeat(config, store):
    run(config, FixtureSerpApi([ok("same")]), store)
    m = run(config, FixtureSerpApi([ok("same")]), store, trigger="manual", target_time=None)
    assert m.searches[0].status is SearchStatus.REPEAT and m.searches[0].raw_ref is not None
    assert m.run_id.startswith("manual-")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_credit_read_failure_writes_a_failed_manifest(config, store):
    api = FixtureSerpApi([ok()], credits_error=OSError("account endpoint unreachable"))
    m = run(config, api, store)
    assert m.status is RunStatus.FAILED and api.calls == [] and m.searches == ()
    assert m.failure_reason.startswith("credit read failed") and store.has_run(m.run_id)


class RefusingStore(EvidenceStore):
    def write_raw(self, meta, response, *, sensitivity):
        from deallens.evidence import EvidenceError
        raise EvidenceError("disk full")


def test_raw_write_failure_after_a_paid_call_is_recorded_and_stops_the_run(config, tmp_path):
    store = RefusingStore(tmp_path)
    api = FixtureSerpApi([ok("s1"), ok("s2")], credits=247)
    m = run(with_plans(config, 2), api, store)
    assert len(api.calls) == 1                                   # no further paid calls after evidence was lost
    first = m.searches[0]
    assert first.status is SearchStatus.FAILED and first.search_id == "s1" and first.raw_ref is None
    assert "raw write failed" in first.error and m.status is RunStatus.FAILED
    assert store.has_run(m.run_id) and not list((tmp_path / "data" / "evidence" / "raw").rglob("*.json"))


def test_malformed_json_spends_exactly_one_paid_attempt(config, store):
    replies = [json.dumps({"plan_searches_left": 247}).encode(), b"not json", b"not json"]
    urls = []

    def opener(url, timeout):
        urls.append(url)
        return _Resp(replies.pop(0))

    m = run(config, HttpSerpApi(KEY, opener=opener), store)
    assert sum("/search.json" in u for u in urls) == 1
    assert m.status is RunStatus.FAILED and m.searches[0].error.startswith("invalid_response")


def test_api_key_never_reaches_logs_or_evidence(config, store, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    bodies = [{"plan_searches_left": 247}, {"error": f"bad key {KEY}"}]
    api = HttpSerpApi(KEY, opener=lambda url, timeout: _Resp(json.dumps(bodies.pop(0)).encode()))
    m = run(config, api, store)
    assert m.status is RunStatus.FAILED
    assert KEY not in caplog.text
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert KEY not in f.read_text(encoding="utf-8")
