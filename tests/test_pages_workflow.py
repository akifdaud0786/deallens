"""Static checks of the GitHub Pages publishing workflow (never run by tests).

It republishes the read-only site from evidence already collected: no SerpApi call, no secret, no cache writes."""
import re

import pytest

from conftest import ROOT

yaml = pytest.importorskip("yaml")
WORKFLOW = ROOT / ".github" / "workflows" / "publish-site.yml"


@pytest.fixture(scope="module")
def wf():
    text = WORKFLOW.read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    return text, doc, doc.get("on", doc.get(True))


def test_runs_after_each_collection_or_on_demand(wf):
    _, _, on = wf
    assert on["workflow_run"] == {"workflows": ["DealLens scheduled collector"], "types": ["completed"]}
    assert "workflow_dispatch" in on and "schedule" not in on and "push" not in on


def test_never_spends_credits_or_sees_the_key(wf):
    text, _, _ = wf
    assert "secrets." not in text and "SERPAPI_API_KEY" not in text and "DEALLENS_MODE" not in text
    assert not re.search(r"deallens\.cli[^\n]*\b(collect|investigate|credits)\b", text)
    assert "serpapi.com" not in text and "urlopen" not in text


def test_reads_the_evidence_cache_but_never_writes_it(wf):
    _, doc, _ = wf
    uses = [s.get("uses", "") for job in doc["jobs"].values() for s in job["steps"]]
    assert any(u.startswith("actions/cache/restore@") for u in uses)
    assert not any(u.startswith(("actions/cache@", "actions/cache/save@")) for u in uses)


def test_builds_the_site_from_the_projection(wf):
    _, doc, _ = wf
    runs = "\n".join(s.get("run", "") for s in doc["jobs"]["build"]["steps"])
    for cmd in ("python -m deallens.cli --root . rebuild", "npm ci", "npm run build",
                "python -m deallens.cli --root . export-static --out frontend/dist"):
        assert cmd in runs, cmd
    uploads = [s for s in doc["jobs"]["build"]["steps"] if s.get("uses", "").startswith("actions/upload-pages-artifact@")]
    assert [s["with"]["path"] for s in uploads] == ["frontend/dist"]


def test_least_privilege_and_no_overlap(wf):
    _, doc, _ = wf
    assert doc["permissions"] == {"contents": "read"}
    assert doc["jobs"]["deploy"]["permissions"] == {"pages": "write", "id-token": "write"}
    assert doc["jobs"]["deploy"]["needs"] == "build"
    assert doc["concurrency"] == {"group": "deallens-pages", "cancel-in-progress": False}
