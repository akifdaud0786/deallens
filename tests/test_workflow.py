"""Static checks of the scheduled-collector workflow (it is never run by tests)."""
import re

import pytest

from conftest import ROOT

yaml = pytest.importorskip("yaml")
WORKFLOW = ROOT / ".github" / "workflows" / "scheduled-collector.yml"


@pytest.fixture(scope="module")
def wf():
    text = WORKFLOW.read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    return text, doc, doc.get("on", doc.get(True))      # PyYAML reads the key `on` as True


def steps(doc):
    return doc["jobs"]["collect"]["steps"]


def test_runs_only_on_the_three_ist_slots(wf):
    _, _, on = wf
    assert [s["cron"] for s in on["schedule"]] == ["30 3 * * *", "30 9 * * *", "30 15 * * *"]
    assert set(on) == {"schedule"}                       # no push/PR/manual triggers that could spend credits


def test_scheduled_jobs_never_overlap(wf):
    _, doc, _ = wf
    assert doc["concurrency"] == {"group": "deallens-scheduled-collector", "cancel-in-progress": False}


def test_crons_resolve_to_configured_slots(wf, config):
    from deallens.collector.schedule import scheduled_slot
    _, _, on = wf
    assert [scheduled_slot(s["cron"], "2026-10-05T18:00:00+00:00", config.collector.scheduled_slots_ist)
            for s in on["schedule"]] == ["2026-10-05T09:00+05:30", "2026-10-05T15:00+05:30", "2026-10-05T21:00+05:30"]


def test_collects_through_the_cli_with_an_explicit_slot(wf):
    text, doc, _ = wf
    runs = "\n".join(s.get("run", "") for s in steps(doc))
    assert "python -m deallens.cli --root . slot --cron" in runs and "github.event.schedule" in text
    assert re.search(r"python -m deallens\.cli --root \. collect --trigger scheduled --target-time \"\$\{\{ steps\.slot\.outputs\.target \}\}\"", runs)
    assert "python -m deallens.cli --root . rebuild" in runs
    assert "serpapi.com" not in text and "urlopen" not in text           # no collector logic duplicated in YAML


def test_secret_reaches_only_the_collect_step_and_is_never_printed(wf):
    text, doc, _ = wf
    with_secret = [s for s in steps(doc) if "secrets.SERPAPI_API_KEY" in str(s)]
    assert [s["name"] for s in with_secret] == ["Collect (one paid Shopping call per slot)"]
    assert with_secret[0]["env"] == {"SERPAPI_API_KEY": "${{ secrets.SERPAPI_API_KEY }}", "DEALLENS_MODE": "live"}
    assert not re.search(r"(echo|printf|cat)[^\n]*SERPAPI_API_KEY", text)
    assert "set -x" not in text


def test_evidence_is_persisted_outside_git_and_never_committed(wf):
    text, doc, _ = wf
    assert not re.search(r"git (add|commit|push)", text)
    assert doc["permissions"] == {"contents": "read"}
    uses = [s.get("uses", "") for s in steps(doc)]
    assert any(u.startswith("actions/cache/restore@") for u in uses) and any(u.startswith("actions/cache/save@") for u in uses)
    assert any(u.startswith("actions/upload-artifact@") for u in uses)
    for s in steps(doc):
        path = s.get("with", {}).get("path", "")
        if s.get("uses", "").startswith("actions/cache/"):            # raw evidence chain stays in the cache
            assert "data/evidence" in path and "data/private" in path
        if s.get("uses", "").startswith("actions/upload-artifact@"):  # artifacts are downloadable in a public repo
            assert path.split() == ["data/evidence/manifests", "data/projection"], path
