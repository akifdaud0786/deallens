"""Evidence Store: the only reader/writer of source evidence (raw responses, Run Manifests, probe registry).

Write-once, atomic, hashed. Knows nothing about matching, prices, sellers, SQLite or SerpApi.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from deallens.domain import (EvidenceSet, RawRecord, RawRef, RunManifest, RunSource, RunStatus,
                             SearchAttempt, SearchStatus)

SHAREABLE_RAW = Path("data/evidence/raw")
PRIVATE_RAW = Path("data/private/raw")
MANIFESTS = Path("data/evidence/manifests")
PROBES = Path("data/evidence/probes.json")
REQUIRED_META = ("run_id", "kind", "fetched_at", "params")


class EvidenceError(RuntimeError):
    pass


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._@-]+", "-", text)


def _write_new(path: Path, data: bytes) -> None:
    """Atomic create: temp file then rename; refuses to replace an existing file."""
    if path.exists():
        raise EvidenceError(f"refusing to overwrite: {path} exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    try:
        if path.exists():
            raise EvidenceError(f"refusing to overwrite: {path} exists")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def manifest_to_dict(m: RunManifest) -> dict:
    d = asdict(m)
    d["status"] = m.status.value
    d["searches"] = [{**asdict(s), "status": s.status.value} for s in m.searches]
    return d


def manifest_from_dict(d: Mapping[str, Any]) -> RunManifest:
    searches = tuple(
        SearchAttempt(s["attempt_no"], s.get("plan"), dict(s["params"]), SearchStatus(s["status"]), s["started_at"],
                      s.get("search_id"), RawRef(**s["raw_ref"]) if s.get("raw_ref") else None, s.get("error"))
        for s in d.get("searches", []))
    return RunManifest(d["run_id"], d["trigger"], d.get("target_time"), d["started_at"], d["finished_at"],
                       RunStatus(d["status"]), searches, d.get("credits_before"), d.get("skip_reason"),
                       dict(d.get("config_versions", {})), d.get("failure_reason"))


class EvidenceStore:
    def __init__(self, root):
        self.root = Path(root)

    # ---------- writes ----------

    def write_raw(self, meta: Mapping[str, Any], response: Mapping[str, Any], *, sensitivity: str) -> RawRef:
        missing = [k for k in REQUIRED_META if k not in meta]
        if missing:
            raise EvidenceError(f"raw meta missing {missing}")
        if "api_key" in meta["params"]:
            raise EvidenceError("raw meta params must not contain api_key")
        if sensitivity not in ("shareable", "private"):
            raise EvidenceError(f"unknown sensitivity {sensitivity}")
        base = PRIVATE_RAW if sensitivity == "private" else SHAREABLE_RAW
        stamp = meta["fetched_at"].replace("-", "").replace(":", "").split(".")[0].split("+")[0]
        name = f"{stamp}Z_{_safe(meta['run_id'])}_{_safe(str(meta.get('plan') or 'noplan'))}_{meta.get('attempt_no', 1)}.json"
        rel = base / meta["kind"] / name
        data = json.dumps({"meta": {**meta, "sensitivity": sensitivity}, "response": response},
                          ensure_ascii=False, indent=1).encode("utf-8")
        _write_new(self.root / rel, data)
        return RawRef(rel.as_posix(), hashlib.sha256(data).hexdigest())

    def write_manifest(self, manifest: RunManifest) -> RawRef:
        rel = MANIFESTS / f"{_safe(manifest.run_id)}.json"
        if (self.root / rel).exists():
            raise EvidenceError(f"manifest for run {manifest.run_id} already exists")
        data = json.dumps(manifest_to_dict(manifest), ensure_ascii=False, indent=1).encode("utf-8")
        _write_new(self.root / rel, data)
        return RawRef(rel.as_posix(), hashlib.sha256(data).hexdigest())

    # ---------- reads ----------

    def has_run(self, run_id: str) -> bool:
        return (self.root / MANIFESTS / f"{_safe(run_id)}.json").exists()

    def known_search_ids(self) -> set[str]:
        return {r.response.get("search_metadata", {}).get("id") for r in self.read_all().raws} - {None}

    def _manifests(self) -> list[RunManifest]:
        d = self.root / MANIFESTS
        return [manifest_from_dict(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(d.glob("*.json"))] \
            if d.exists() else []

    def _probe_paths(self) -> list[str]:
        reg = self.root / PROBES
        if not reg.exists():
            return []
        return list(json.loads(reg.read_text(encoding="utf-8")).get("probes", []))

    def read_all(self) -> EvidenceSet:
        manifests = self._manifests()
        run_ids = {m.run_id for m in manifests}
        recorded = {s.raw_ref.path: s.raw_ref.sha256 for m in manifests for s in m.searches if s.raw_ref}
        raws = []
        for base, sensitivity in ((SHAREABLE_RAW, "shareable"), (PRIVATE_RAW, "private")):
            for p in sorted((self.root / base).rglob("*.json")):
                rel = p.relative_to(self.root).as_posix()
                blob = p.read_bytes()
                doc = json.loads(blob.decode("utf-8"))
                run_id = doc.get("meta", {}).get("run_id", "")
                source = RunSource.MANIFEST if run_id in run_ids else RunSource.ORPHAN
                sha = hashlib.sha256(blob).hexdigest()
                verified = (recorded[rel] == sha) if rel in recorded else None
                raws.append(RawRecord(RawRef(rel, sha), doc.get("meta", {}), doc.get("response", {}),
                                      run_id, source, sensitivity, verified))
        missing = []
        for rel in self._probe_paths():
            p = self.root / rel
            if not p.exists():                 # probes live in gitignored data/cache: absent on a fresh clone
                missing.append(rel)
                continue
            blob = p.read_bytes()
            doc = json.loads(blob.decode("utf-8"))
            raws.append(RawRecord(RawRef(p.relative_to(self.root).as_posix(), hashlib.sha256(blob).hexdigest()),
                                  doc.get("meta", {}), doc.get("response", {}), f"probe:{p.name}",
                                  RunSource.MANIFEST_LESS_PROBE, "shareable", None))
        return EvidenceSet(tuple(manifests), tuple(raws), tuple(missing))
