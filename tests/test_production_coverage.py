"""Production coverage counts only observations from runs with a valid Run Manifest; plan versions stay isolated."""
import dataclasses

from conftest import BROAD
from deallens.analysis import analyse
from deallens.collector import collect
from deallens.domain import CoverageLevel, Reason, RunSource
from deallens.evidence import EvidenceStore
from deallens.market import build_ledger
from deallens.serpapi import FixtureSerpApi, SearchOutcome
from synthetic import synthetic_evidence, synthetic_row, synthetic_run

AS_OF = "2026-10-10T18:29:59+00:00"
BQ224, BQ832 = "asus-x1504vap-bq224ws", "asus-x1504ma-bq832ws"
T = "ASUS X1504VAP-BQ224WS"


def test_probe_observations_are_kept_but_excluded(probe_ledger):
    o = next(o for o in probe_ledger.observations if o.raw_ref.path.endswith(BROAD.name) and o.position == 5)
    assert o.match.product_key == BQ224 and not o.included
    assert o.reasons == (Reason.DEVELOPMENT_PROBE,)
    assert len(probe_ledger.observations) == 80                         # audit trail intact


def test_probes_cannot_inflate_production_coverage(config):
    probe = synthetic_run("probe:p1", "2026-10-03T14:00:00+00:00",
                          [synthetic_row(1, "Amazon.in", T, 72800), synthetic_row(2, "Croma", T, 73990)],
                          source=RunSource.MANIFEST_LESS_PROBE)
    prod = synthetic_run("r1", "2026-10-04T03:30:00+00:00", [synthetic_row(1, "Amazon.in", T, 72790)])
    a = analyse(build_ledger(synthetic_evidence(probe, prod), config), BQ224, config, as_of=AS_OF)
    c = a.coverage
    assert (c.observed_days, c.runs, c.sellers, c.valid_observations) == (("2026-10-04",), ("r1",), ("Amazon.in",), 1)
    assert c.level is CoverageLevel.NO_HISTORY and "change_since" not in {x.kind for x in a.claims}


def test_probe_only_product_has_no_production_coverage(probe_ledger, config):
    a = analyse(probe_ledger, BQ224, config, as_of=AS_OF)
    assert a.coverage.valid_observations == 0 and a.coverage.runs == ()
    assert [c.kind for c in a.claims] == ["excluded_count"]


def test_watchlist_replaces_bq541ws_with_bq832ws(config):
    assert [p.model_key for p in config.products] == ["X1504VAP-BQ224WS", "X1504MA-BQ832WS", "X1504VA-NJ2324WS"]
    assert [(p.ref, p.status) for p in config.plans] == [("vivobook15-broad@1", "retired"),
                                                         ("vivobook15-broad@2", "provisional")]
    assert BQ832 in config.plan("vivobook15-broad@2").serves


def test_planless_raws_resolve_to_the_plan_in_force_when_fetched(probe_ledger, config):
    o = next(o for o in probe_ledger.observations if o.raw_ref.path.endswith(BROAD.name))
    assert o.plan == "vivobook15-broad@1"                                # 3 Oct probe predates @2
    raw, man = synthetic_run("later", "2026-10-05T03:30:00+00:00", [synthetic_row(1, "Vijay Sales", "X1504MA-BQ832WS", 82990)])
    raw = dataclasses.replace(raw, meta={k: v for k, v in raw.meta.items() if k != "plan"})
    (later,) = build_ledger(synthetic_evidence((raw, man)), config).observations
    assert later.plan == "vivobook15-broad@2"


def test_old_and_new_plan_versions_never_share_coverage(config):
    old = synthetic_run("o1", "2026-10-04T03:30:00+00:00", [synthetic_row(1, "Amazon.in", T, 72800)],
                        plan="vivobook15-broad@1")
    new = synthetic_run("n1", "2026-10-05T03:30:00+00:00", [synthetic_row(1, "Amazon.in", T, 72500)],
                        plan="vivobook15-broad@2")
    c = analyse(build_ledger(synthetic_evidence(old, new), config), BQ224, config, as_of=AS_OF).coverage
    assert c.plan == "vivobook15-broad@2" and c.other_plans_not_combined == ("vivobook15-broad@1",)
    assert c.runs == ("n1",) and c.level is CoverageLevel.NO_HISTORY


def test_collector_runs_only_active_plans(config, tmp_path):
    api = FixtureSerpApi([SearchOutcome.ok({"search_metadata": {"id": "s1"}, "shopping_results": []})], credits=245)
    m = collect(config, api, EvidenceStore(tmp_path), trigger="manual", target_time=None,
                now=iter(f"2026-10-04T03:30:{s:02d}+00:00" for s in range(60)).__next__)
    assert len(api.calls) == 1 and [s.plan for s in m.searches] == ["vivobook15-broad@2"]


def test_summary_counts_calendar_days_not_duration(config):
    runs = [synthetic_run(f"d{d}", f"2026-10-0{4 + d}T03:30:00+00:00", [synthetic_row(1, "Amazon.in", T, 72800 - d)])
            for d in range(2)]
    a = analyse(build_ledger(synthetic_evidence(*runs), config), BQ224, config, as_of=AS_OF)
    assert "2 observed calendar days" in a.summary and a.summary.endswith("Limited history (2 observed calendar days).")
    assert "days of price history" not in a.summary
