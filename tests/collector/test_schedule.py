"""Cron -> explicit IST slot (pure), max_attempts=1 for the collection week, and the CLI `slot` command."""
import dataclasses

import pytest

from deallens import cli
from deallens.collector import collect
from deallens.collector.schedule import scheduled_slot
from deallens.domain import RunStatus
from deallens.evidence import EvidenceStore
from deallens.serpapi import FixtureSerpApi, SearchOutcome

SLOTS = ("09:00", "15:00", "21:00")


@pytest.mark.parametrize("cron,now,slot", [
    ("30 3 * * *", "2026-10-04T03:30:05+00:00", "2026-10-04T09:00+05:30"),
    ("30 9 * * *", "2026-10-04T09:41:00+00:00", "2026-10-04T15:00+05:30"),
    ("30 15 * * *", "2026-10-04T15:30:00+00:00", "2026-10-04T21:00+05:30"),
    ("30 15 * * *", "2026-10-04T18:10:00+00:00", "2026-10-04T21:00+05:30"),   # delayed start: same slot
    ("30 3 * * *", "2026-10-04T03:29:59+00:00", "2026-10-03T09:00+05:30"),    # early clock: previous slot (a replay)
])
def test_cron_maps_to_the_explicit_ist_slot(cron, now, slot):
    assert scheduled_slot(cron, now, SLOTS) == slot


@pytest.mark.parametrize("cron", ["0 4 * * *", "*/5 * * * *", "30 3 * * 1", "nonsense"])
def test_crons_outside_the_configured_slots_are_rejected(cron):
    with pytest.raises(ValueError):
        scheduled_slot(cron, "2026-10-04T04:00:00+00:00", SLOTS)


def test_cli_prints_the_slot_for_a_cron(capsys):
    from conftest import ROOT
    assert cli.main(["--root", str(ROOT), "slot", "--cron", "30 9 * * *", "--now", "2026-10-04T09:31:00+00:00"],
                    env={}) == 0
    assert capsys.readouterr().out.strip() == "2026-10-04T15:00+05:30"


def test_cli_slot_refuses_an_unconfigured_cron(capsys):
    from conftest import ROOT
    assert cli.main(["--root", str(ROOT), "slot", "--cron", "0 4 * * *", "--now", "2026-10-04T04:00:00+00:00"],
                    env={}) == 2


def test_collection_week_makes_one_attempt_per_slot(config, tmp_path):
    assert config.collector.max_attempts == 1
    api = FixtureSerpApi([SearchOutcome.failure("timeout", "slow"), SearchOutcome.ok({"search_metadata": {"id": "x"}})])
    m = collect(config, api, EvidenceStore(tmp_path), trigger="scheduled", target_time="2026-10-04T09:00+05:30",
                now=iter(f"2026-10-04T03:30:{s:02d}+00:00" for s in range(60)).__next__)
    assert len(api.calls) == 1 and m.status is RunStatus.FAILED     # no second, possibly billed, request
