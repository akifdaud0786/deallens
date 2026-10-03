import json
import shutil

import pytest

from conftest import BROAD, REPEAT
from deallens.domain import RawRef, RunManifest, RunSource, RunStatus, SearchAttempt, SearchStatus
from deallens.evidence import EvidenceError, EvidenceStore

FETCHED = "2026-10-04T03:30:00+00:00"
PARAMS = {"engine": "google_shopping", "q": "ASUS Vivobook 15", "gl": "in"}


def meta(run_id="scheduled-2026-10-04T09:00+05:30", **kw):
    return {"run_id": run_id, "kind": "shopping", "plan": "vivobook15-broad@1", "params": PARAMS,
            "fetched_at": FETCHED, "search_id": "abc", "status": "succeeded", "attempt_no": 1, **kw}


def manifest(run_id, ref):
    return RunManifest(run_id=run_id, trigger="scheduled", target_time="2026-10-04T09:00+05:30",
                       started_at=FETCHED, finished_at=FETCHED, status=RunStatus.COMPLETED,
                       searches=(SearchAttempt(1, "vivobook15-broad@1", PARAMS, SearchStatus.SUCCEEDED, FETCHED, "abc", ref),))


@pytest.fixture
def store(tmp_path):
    return EvidenceStore(tmp_path)


def test_raw_is_written_atomically_with_its_hash(store, tmp_path):
    ref = store.write_raw(meta(), {"search_metadata": {"id": "abc"}}, sensitivity="shareable")
    f = tmp_path / ref.path
    assert f.exists() and ref.path.startswith("data/evidence/raw/shopping/")
    import hashlib
    assert hashlib.sha256(f.read_bytes()).hexdigest() == ref.sha256
    doc = json.loads(f.read_text(encoding="utf-8"))
    assert doc["meta"]["fetched_at"] == FETCHED and doc["response"]["search_metadata"]["id"] == "abc"
    assert not [p for p in f.parent.iterdir() if p.name.endswith(".tmp")]


def test_raw_is_never_overwritten(store):
    store.write_raw(meta(), {"a": 1}, sensitivity="shareable")
    with pytest.raises(EvidenceError, match="exists"):
        store.write_raw(meta(), {"a": 2}, sensitivity="shareable")


def test_raw_metadata_cannot_carry_an_api_key(store):
    with pytest.raises(EvidenceError, match="api_key"):
        store.write_raw(meta(params={**PARAMS, "api_key": "secret"}), {}, sensitivity="shareable")


def test_private_raws_live_outside_the_shareable_evidence_area(store, tmp_path):
    ref = store.write_raw(meta(kind="immersive"), {"product_results": {}}, sensitivity="private")
    assert ref.path.startswith("data/private/raw/immersive/")
    assert not list((tmp_path / "data" / "evidence").rglob("*immersive*"))


def test_manifest_is_write_once(store):
    m = manifest("run-1", None)
    store.write_manifest(m)
    assert store.has_run("run-1")
    with pytest.raises(EvidenceError, match="run-1"):
        store.write_manifest(m)


def test_read_all_links_raws_to_manifests_and_verifies_hashes(store, tmp_path):
    ref = store.write_raw(meta(run_id="run-1"), {"search_metadata": {"id": "abc"}}, sensitivity="shareable")
    store.write_manifest(manifest("run-1", ref))
    ev = store.read_all()
    assert [m.run_id for m in ev.manifests] == ["run-1"]
    (raw,) = ev.raws
    assert raw.run_source is RunSource.MANIFEST and raw.hash_verified is True
    (tmp_path / ref.path).write_text("{\"meta\": {}, \"response\": {}}", encoding="utf-8")  # tamper
    assert store.read_all().raws[0].hash_verified is False


def test_raws_without_a_manifest_are_orphans(store):
    store.write_raw(meta(run_id="crashed-run"), {"search_metadata": {"id": "zzz"}}, sensitivity="shareable")
    ev = store.read_all()
    assert [r.run_id for r in ev.orphans] == ["crashed-run"]
    assert ev.orphans[0].run_source is RunSource.ORPHAN


def test_registered_probes_are_manifest_less(tmp_path):
    (tmp_path / "data" / "cache").mkdir(parents=True)
    for f in (BROAD, REPEAT):
        shutil.copy(f, tmp_path / "data" / "cache" / f.name)
    reg = tmp_path / "data" / "evidence" / "probes.json"
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"probes": [f"data/cache/{BROAD.name}", f"data/cache/{REPEAT.name}"]}), encoding="utf-8")
    ev = EvidenceStore(tmp_path).read_all()
    assert {r.run_source for r in ev.raws} == {RunSource.MANIFEST_LESS_PROBE}
    assert sorted(r.run_id for r in ev.raws) == [f"probe:{BROAD.name}", f"probe:{REPEAT.name}"]
    assert EvidenceStore(tmp_path).known_search_ids() == {"6ac10b76a26f566bae26b24b"}


def test_missing_registered_probe_is_reported_not_crashed(tmp_path):
    reg = tmp_path / "data" / "evidence" / "probes.json"
    reg.parent.mkdir(parents=True)
    reg.write_text(json.dumps({"probes": ["data/cache/not-in-this-checkout.json"]}), encoding="utf-8")
    ev = EvidenceStore(tmp_path).read_all()
    assert ev.raws == () and ev.missing_probes == ("data/cache/not-in-this-checkout.json",)
