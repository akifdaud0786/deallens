"""Demo redesign view models: decision card, active vs retired plan, known/unknown, claim cards.
All derived from existing projection state; no new analytical rule."""
import re

import pytest

from deallens.analysis import analyse
from deallens.app import views
from deallens.domain import RunSource
from deallens.market import build_ledger
from deallens.projection import ProjectionReader, rebuild
from synthetic import synthetic_evidence, synthetic_row, synthetic_run

AS_OF = "2026-10-10T18:29:59+00:00"
BQ224, BQ832, NJ = "asus-x1504vap-bq224ws", "asus-x1504ma-bq832ws", "asus-x1504va-nj2324ws"
T = "ASUS Vivobook 15 X1504VAP-BQ224WS"
NJ_T = "Asus Vivobook 15 X1504VA-NJ2324WS"
FORBIDDEN = re.compile(r"great deal|bargain|unusually cheap|price dropped|lowest ever|best deal|good deal|all-time", re.I)
P2 = "vivobook15-broad@2"


def project(config, tmp_path, *runs):
    ledger = build_ledger(synthetic_evidence(*runs), config)
    path = tmp_path / "p.sqlite"
    rebuild(ledger, [analyse(ledger, p.product_key, config, as_of=AS_OF) for p in config.products], path,
            products=config.products, plans=config.plans, as_of=AS_OF, coverage_policy=config.coverage)
    return ProjectionReader(path)


def view(r, key):
    return views.product_view(r.product(key), r.current_market(key), r.price_series(key), r.ledger(key), r.plans(),
                              policy=r.info()["coverage_policy"])


def first_active_run():
    """SYNTHETIC copy of today's real state: one @2 run, BQ224WS at Flipkart (with list price) and ASUS eshop IN."""
    return synthetic_run("scheduled-a", "2026-10-04T10:01:33+00:00",
                         [synthetic_row(1, "Flipkart", T, 66990, old_price="₹73,990"),
                          synthetic_row(2, "ASUS eshop IN", T, 73990)], plan=P2)


def retired_manual_run():
    return synthetic_run("manual-old", "2026-10-03T19:05:53+00:00", [synthetic_row(1, "Flipkart", NJ_T, 61599)],
                         plan="vivobook15-broad@1")


@pytest.fixture
def today(config, tmp_path):
    return project(config, tmp_path, first_active_run(), retired_manual_run())


def test_first_active_run_asks_and_answers_honestly(today):
    v = view(today, BQ224)
    d = v.decision
    assert v.plan.is_current and v.plan.active_ref == P2
    assert d.question == "Is ₹66,990 a good price?"
    assert d.answer == "Not enough evidence yet"
    assert d.badge == "Evidence accumulating"
    assert d.checks == ((True, "Exact product identity matched"), (True, "2 independent sellers observed"),
                        (True, "Current market price observed"), (False, "Historical baseline not available yet"))
    assert d.verdict == "Keep watching — historical evidence is still accumulating."
    assert v.hero_meta == "2 sellers observed · 1 production run · 1 observed calendar day"
    assert not FORBIDDEN.search(" ".join([d.question, d.answer, d.badge, d.verdict, *[t for _, t in d.checks]]))


def test_known_and_unknown_come_from_the_evidence(today):
    v = view(today, BQ224)
    assert v.known == ("Exact model X1504VAP-BQ224WS matched by deterministic identity rules",
                       "2 independent sellers observed in the latest run",
                       "Lowest observed listed price: ₹66,990 at Flipkart",
                       "Production observation recorded at 2026-10-04T10:01:33+00:00 UTC (run scheduled-a)",
                       "1 raw SerpApi response stored with its SHA-256 hash")
    assert v.unknown == (
        "Observed low / high / average: needs at least 5 observed calendar days, 8 runs and 2 independent sellers",
        "How the price moves over time: no price history yet",
        "Stock availability: unknown (Google Shopping results do not state it)",
        "Whether the seller-displayed list price was ever charged: not verified by DealLens",
        "Sellers beyond this Google Shopping page: one query returns about 40 results, so coverage is not exhaustive")


def test_retired_plan_evidence_is_never_shown_as_current(today):
    v = view(today, NJ)
    assert not v.plan.is_current and v.plan.shown_ref == "vivobook15-broad@1"
    assert v.plan.label == "Retired @1 evidence — not included in current @2 analysis"
    assert v.decision.answer == "No current @2 observation"
    assert v.decision.badge == "No current observation"
    assert v.hero_price == "—" and "61,599" not in v.decision.question + v.decision.answer
    assert v.known == ("Older observations exist under retired plan vivobook15-broad@1; they are not used here",)
    assert v.unknown[0] == "Today's price under the active plan vivobook15-broad@2"


def test_product_without_any_observation_has_no_current_observation(today):
    v = view(today, BQ832)
    assert v.decision.answer == "No current @2 observation" and v.hero_price == "—" and v.plan.label is None


def test_cards_flag_products_without_a_current_observation(today):
    keys = [w["product_key"] for w in today.watchlist()]
    cards = views.snapshot_cards(today.watchlist(), today.plans(), {k: today.product(k)["coverage"]["plan"] for k in keys})
    assert [(c.model_key, c.lowest_listed, c.current) for c in cards] == [
        ("X1504VAP-BQ224WS", "₹66,990", True),
        ("X1504MA-BQ832WS", "No current @2 observation", False),
        ("X1504VA-NJ2324WS", "No current @2 observation", False)]


def test_claim_cards_are_titled_and_traceable(today):
    v = view(today, BQ224)
    lowest = next(c for c in v.claims if c.kind == "current_lowest_listed")
    assert lowest.title == "Current lowest listed price"
    assert lowest.claim_id == f"{BQ224}:C1" and lowest.source == "Google Shopping via SerpApi"
    assert [(e.storefront, e.run_id, e.search_id) for e in lowest.evidence] == [("Flipkart", "scheduled-a", "sid-scheduled-a")]


def test_probes_never_count_as_production_runs(config, tmp_path):
    probe_raw, _ = synthetic_run("probe:p", "2026-10-03T14:04:42+00:00", [synthetic_row(1, "Croma", T, 70000)],
                                 plan=P2, source=RunSource.MANIFEST_LESS_PROBE)   # real probes have no manifest
    ledger = build_ledger(synthetic_evidence(first_active_run(), orphans=[probe_raw]), config)
    path = tmp_path / "probe.sqlite"
    rebuild(ledger, [analyse(ledger, p.product_key, config, as_of=AS_OF) for p in config.products], path,
            products=config.products, plans=config.plans, as_of=AS_OF, coverage_policy=config.coverage)
    v = view(ProjectionReader(path), BQ224)
    assert v.hero_meta == "2 sellers observed · 1 production run · 1 observed calendar day"
    assert "Croma" not in [m.storefront for m in v.market]


@pytest.mark.parametrize("days,answer,badge", [
    (3, "Early evidence only", "Limited history"),
    (6, "Compare with the observed range", "History available"),
])
def test_decision_follows_the_existing_coverage_level(config, tmp_path, days, answer, badge):
    runs = [synthetic_run(f"d{d}r{r}", f"2026-10-0{4 + d}T0{3 + 6 * r}:30:00+00:00",
                          [synthetic_row(1, "Amazon.in", T, 72800 - d), synthetic_row(2, "Croma", T, 73990)], plan=P2)
            for d in range(days) for r in range(2)]
    d = view(project(config, tmp_path, *runs), BQ224).decision
    assert (d.answer, d.badge) == (answer, badge) and not FORBIDDEN.search(d.verdict + d.answer)
