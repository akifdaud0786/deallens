"""Pre-collection audit regressions: canonical IST slots, slot allow-list, no fabricated observations,
raw evidence never tracked by git."""
import subprocess

import pytest

from conftest import ROOT
from deallens.collector import collect
from deallens.domain import RunStatus
from deallens.evidence import EvidenceStore
from deallens.market import build_ledger
from deallens.serpapi import FixtureSerpApi, SearchOutcome


def clock():
    t = iter(f"2026-10-04T03:30:{s:02d}+00:00" for s in range(60))
    return lambda: next(t)


def ok(sid="s1"):
    return SearchOutcome.ok({"search_metadata": {"id": sid}, "shopping_results": []})


def scheduled(config, api, store, target_time):
    return collect(config, api, store, trigger="scheduled", target_time=target_time, now=clock())


def test_the_same_slot_written_two_ways_is_one_run(config, tmp_path):
    store = EvidenceStore(tmp_path)
    first = scheduled(config, FixtureSerpApi([ok()]), store, "2026-10-04T09:00+05:30")
    api = FixtureSerpApi([ok("s2")])
    replay = scheduled(config, api, store, "2026-10-04T03:30:00+00:00")           # same instant, UTC spelling
    assert first.run_id == "scheduled-2026-10-04T09:00+05:30"
    assert replay.status is RunStatus.SKIPPED and api.calls == [] and replay.run_id == first.run_id


@pytest.mark.parametrize("slot", ["2026-10-04T09:00+05:30", "2026-10-04T15:00+05:30", "2026-10-04T21:00+05:30"])
def test_configured_ist_slots_are_collected(config, tmp_path, slot):
    api = FixtureSerpApi([ok()])
    m = scheduled(config, api, EvidenceStore(tmp_path), slot)
    assert m.status is RunStatus.COMPLETED and len(api.calls) == 1


@pytest.mark.parametrize("slot", ["2026-10-04T10:00+05:30", "2026-10-04T09:05+05:30", "2026-10-04T09:00:00+00:00"])
def test_scheduled_times_outside_the_ist_slots_spend_nothing(config, tmp_path, slot):
    store = EvidenceStore(tmp_path)
    api = FixtureSerpApi([ok()])
    m = scheduled(config, api, store, slot)
    assert m.status is RunStatus.SKIPPED and "not a configured IST collection slot" in m.skip_reason
    assert api.calls == [] and not store.has_run(m.run_id)


def test_failed_call_yields_no_observations(config, tmp_path):
    store = EvidenceStore(tmp_path)
    scheduled(config, FixtureSerpApi([SearchOutcome.failure("api_error", "Invalid API key")]), store,
              "2026-10-04T09:00+05:30")
    assert build_ledger(store.read_all(), config).observations == ()


def test_raw_evidence_is_never_tracked_by_git():
    """Raw responses carry SerpApi account/archive URLs and are unpublishable until the Terms are checked."""
    paths = ["data/evidence/raw/shopping/x.json", "data/private/raw/immersive/x.json", "data/projection/deallens.sqlite",
             ".env"]
    r = subprocess.run(["git", "check-ignore", *paths], cwd=ROOT, capture_output=True, text=True)
    assert sorted(r.stdout.split()) == sorted(paths)
