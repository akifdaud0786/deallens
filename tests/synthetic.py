"""SYNTHETIC evidence builders for cases the real 3 Oct fixtures cannot provide (multi-day history,
ambiguous rows, orphans). Every record built here has a `synthetic/` path."""
from deallens.domain import (EvidenceSet, RawRecord, RawRef, RunManifest, RunSource, RunStatus, SearchAttempt,
                             SearchStatus)

PLAN = "vivobook15-broad@1"
PARAMS = {"engine": "google_shopping", "q": "ASUS Vivobook 15", "gl": "in", "hl": "en",
          "google_domain": "google.co.in", "location": "Mumbai,Maharashtra,India", "no_cache": "true"}


def synthetic_row(position, source, title, price, **extra):
    return {"position": position, "source": source, "title": title, "price": f"₹{price:,}",
            "extracted_price": price, "product_id": f"syn{position}", **extra}


def synthetic_run(run_id, fetched_at, rows, plan=PLAN, source=RunSource.MANIFEST, hash_verified=True):
    ref = RawRef(f"synthetic/{run_id}.json", "0" * 64)
    raw = RawRecord(ref, {"run_id": run_id, "kind": "shopping", "plan": plan, "params": PARAMS,
                          "fetched_at": fetched_at, "search_id": f"sid-{run_id}"},
                    {"search_metadata": {"id": f"sid-{run_id}"}, "shopping_results": rows},
                    run_id, source, "shareable", hash_verified)
    man = RunManifest(run_id, "scheduled", None, fetched_at, fetched_at, RunStatus.COMPLETED,
                      (SearchAttempt(1, plan, PARAMS, SearchStatus.SUCCEEDED, fetched_at, f"sid-{run_id}", ref),))
    return raw, man


def synthetic_evidence(*runs, orphans=()):
    raws = [r for r, _ in runs] + list(orphans)
    return EvidenceSet(tuple(m for _, m in runs), tuple(raws))


def as_production(evidence):
    """FIXTURE helper: re-label manifest-less probe raws as if a production run (with a manifest) had
    collected them, so tests can exercise production rules on real rows. Run ids are prefixed `fixture:`."""
    raws, manifests = [], []
    for r in evidence.raws:
        if r.run_source is not RunSource.MANIFEST_LESS_PROBE:
            raws.append(r)
            continue
        run_id = r.run_id.replace("probe:", "fixture:", 1)
        raws.append(RawRecord(r.ref, {**r.meta, "run_id": run_id}, r.response, run_id, RunSource.MANIFEST,
                              r.sensitivity, True))
        manifests.append(RunManifest(run_id, "manual", None, r.meta["fetched_at"], r.meta["fetched_at"],
                                     RunStatus.COMPLETED,
                                     (SearchAttempt(1, None, r.meta.get("params", {}), SearchStatus.SUCCEEDED,
                                                    r.meta["fetched_at"], r.meta.get("search_id"), r.ref),)))
    return EvidenceSet(tuple(evidence.manifests) + tuple(manifests), tuple(raws), evidence.missing_probes)
