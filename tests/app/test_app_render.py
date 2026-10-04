"""Rendering tests with streamlit.testing.AppTest on sanitized fixture / synthetic projections (no private files)."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from deallens.analysis import analyse  # noqa: E402
from deallens.domain import RawRecord, RawRef, RunSource  # noqa: E402
from deallens.market import build_ledger  # noqa: E402
from deallens.projection import rebuild  # noqa: E402
from deallens.public import PROJECTION  # noqa: E402
from synthetic import synthetic_evidence, synthetic_row, synthetic_run  # noqa: E402

MAIN = Path(__file__).resolve().parents[2] / "src" / "deallens" / "app" / "main.py"
AS_OF = "2026-10-10T18:29:59+00:00"
T = "ASUS X1504VAP-BQ224WS"


def build(root, ledger, config, missing=()):
    rebuild(ledger, [analyse(ledger, p.product_key, config, as_of=AS_OF) for p in config.products],
            Path(root) / PROJECTION, products=config.products, plans=config.plans, missing_probes=missing,
            as_of=AS_OF, coverage_policy=config.coverage)


def render(root, product=None):
    at = AppTest.from_file(str(MAIN), default_timeout=60)
    at.session_state["deallens_root"] = str(root)
    if product:
        at.session_state["deallens_product"] = product
    return at.run()


def all_text(at) -> str:
    parts = []
    for kind in ("title", "header", "subheader", "markdown", "caption", "info", "warning", "error", "success",
                 "metric", "expander", "radio", "text"):
        for el in getattr(at, kind, []):
            for attr in ("value", "label", "body", "proto"):
                v = getattr(el, attr, None)
                if v is not None:
                    parts.append(str(v))
    for df in at.dataframe:
        parts.append(df.value.to_string())
    return "\n".join(parts)


def charts(at):
    return at.get("arrow_vega_lite_chart")


def test_missing_projection_renders_a_message_and_no_products(tmp_path):
    at = render(tmp_path)
    assert not at.exception
    text = all_text(at)
    assert "No DealLens projection has been built yet" in text
    assert "X1504VAP-BQ224WS" not in text and "₹" not in text


def test_empty_projection_says_no_observations(tmp_path, config):
    build(tmp_path, build_ledger(synthetic_evidence(), config), config)
    at = render(tmp_path)
    assert not at.exception and "No observations collected yet." in all_text(at)
    assert "₹" not in all_text(at)


def test_no_history_product_shows_message_and_no_chart(tmp_path, config, fixture_ledger):
    build(tmp_path, fixture_ledger, config, missing=("data/cache/gone.json",))
    at = render(tmp_path)
    assert not at.exception
    text = all_text(at)
    assert "No price history yet." in text and charts(at) == []
    assert "Don't just tell me the cheapest price. Tell me what today's price means." in text
    assert "Read-only" in text and "data/cache/gone.json" in text
    assert "₹72,800" in text and "unknown" in text


def test_list_price_label_and_claims_render_verbatim(tmp_path, config, fixture_ledger):
    build(tmp_path, fixture_ledger, config)
    at = render(tmp_path, product="asus-x1504va-nj2324ws")
    text = all_text(at)
    assert "₹68,999 (shown by seller, not verified by DealLens)" in text
    assert ("Flipkart displayed a list price of ₹68,999 next to ₹61,599; DealLens has not verified that list price."
            in text)


def test_limited_history_renders_observed_points(tmp_path, config):
    runs = [synthetic_run(f"d{d}", f"2026-10-0{4 + d}T03:30:00+00:00",
                          [synthetic_row(1, "Amazon.in", T, 72800 - 100 * d), synthetic_row(2, "Croma", T, 73990)],
                          plan="vivobook15-broad@2")
            for d in range(3)]
    build(tmp_path, build_ledger(synthetic_evidence(*runs), config), config)
    at = render(tmp_path, product="asus-x1504vap-bq224ws")
    assert not at.exception
    (chart,) = charts(at)
    assert "No price history yet." not in all_text(at)
    spec = str(chart.proto)
    assert "Observed listed price" in spec                              # chart title and y-axis label
    assert '\\"point\\"' in spec and '\\"line\\"' not in spec              # points only, no implied trend
    assert "Points are not joined" in all_text(at)


def test_excluded_only_product_shows_excluded_count_and_no_price(tmp_path, config):
    rows = [synthetic_row(1, "desertcart.in", T, 99000)]
    run = synthetic_run("r1", "2026-10-04T03:30:00+00:00", rows, plan="vivobook15-broad@2")
    build(tmp_path, build_ledger(synthetic_evidence(run), config), config)
    at = render(tmp_path, product="asus-x1504vap-bq224ws")
    text = all_text(at)
    assert not at.exception
    assert "1 observation attributed to this product was excluded from statistics" in text
    assert "₹99,000" not in "\n".join(m.value for m in at.metric)       # no fake current price
    assert "Cross-border reseller" in text                               # still visible in the ledger


def test_private_raw_paths_never_render(tmp_path, config):
    shareable, man = synthetic_run("r1", "2026-10-04T03:30:00+00:00", [synthetic_row(1, "Amazon.in", T, 72800)])
    private = RawRecord(RawRef("data/private/raw/immersive/20261004T040000Z_investigation.json", "1" * 64),
                        {"run_id": "investigation-x", "kind": "immersive", "fetched_at": "2026-10-04T04:00:00+00:00",
                         "params": {}}, {"product_results": {"user_reviews": [{"user_name": "Synthetic Reviewer"}]}},
                        "investigation-x", RunSource.ORPHAN, "private")
    build(tmp_path, build_ledger(synthetic_evidence((shareable, man), orphans=[private]), config), config)
    at = render(tmp_path, product="asus-x1504vap-bq224ws")
    text = all_text(at)
    assert not at.exception and "synthetic/r1.json" in text
    assert "data/private" not in text and "immersive" not in text and "Synthetic Reviewer" not in text


# ---------- UI review fixes ----------

def literal_texts(at) -> list[str]:
    """Text rendered without Markdown interpretation (st.text)."""
    return [t.value for t in at.text]


def test_claims_and_summary_render_literally(tmp_path, config):
    store = "Shop_one *Deals* $5 :fire:"
    build(tmp_path, build_ledger(synthetic_evidence(synthetic_run("r1", "2026-10-04T03:30:00+00:00",
                                                                  [synthetic_row(1, store, T, 72800)])), config), config)
    at = render(tmp_path, product="asus-x1504vap-bq224ws")
    assert not at.exception
    claim = f"Lowest listed price observed in the latest run: ₹72,800 at {store} (stock status: unknown)."
    texts = literal_texts(at)
    assert claim in texts                                              # each claim, verbatim and literal
    assert any(t.startswith("Based on the observations collected by DealLens") and claim in t for t in texts)
    assert not any(claim in m.value for m in at.markdown)              # never passed through Markdown


def test_status_strip_separates_build_time_from_latest_observation(tmp_path, config, fixture_ledger):
    build(tmp_path, fixture_ledger, config)
    text = all_text(render(tmp_path))
    assert "Data as of" not in text
    assert f"Analysis built: {AS_OF} (UTC)" in text
    assert "Latest observation: 2026-10-03T14:44:32.234191+00:00 (UTC)" in text


def test_seller_count_labels_name_their_window(tmp_path, config, fixture_ledger):
    build(tmp_path, fixture_ledger, config)
    text = all_text(render(tmp_path, product="asus-x1504vap-bq224ws"))
    assert "Independent sellers (observed window): 2" in text
    assert "Independent sellers (latest run)" in text
    assert "Independent sellers: " not in text


def test_coverage_wording_uses_observed_calendar_days(tmp_path, config):
    runs = [synthetic_run(f"d{d}", f"2026-10-0{4 + d}T03:30:00+00:00", [synthetic_row(1, "Amazon.in", T, 72800 - d)],
                          plan="vivobook15-broad@2")
            for d in range(2)]
    build(tmp_path, build_ledger(synthetic_evidence(*runs), config), config)
    text = all_text(render(tmp_path, product="asus-x1504vap-bq224ws"))
    assert "Limited history · 2 observed calendar days · 2 runs" in text
    assert "Observed calendar days" in text and "Production runs" in text
    assert "at least 2 observed calendar days and 2 runs" in text
