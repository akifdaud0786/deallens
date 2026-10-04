"""Demo-first rendering (AppTest) on a SYNTHETIC copy of today's state: one @2 run for BQ224WS, retired @1
evidence for NJ2324WS, nothing for BQ832WS."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from deallens.analysis import analyse  # noqa: E402
from deallens.market import build_ledger  # noqa: E402
from deallens.projection import rebuild  # noqa: E402
from deallens.public import PROJECTION  # noqa: E402
from synthetic import synthetic_evidence, synthetic_row, synthetic_run  # noqa: E402
from test_app_render import all_text  # noqa: E402

MAIN = Path(__file__).resolve().parents[2] / "src" / "deallens" / "app" / "main.py"
AS_OF = "2026-10-10T18:29:59+00:00"
T = "ASUS Vivobook 15 X1504VAP-BQ224WS"


@pytest.fixture
def root(tmp_path, config):
    runs = [synthetic_run("scheduled-a", "2026-10-04T10:01:33+00:00",
                          [synthetic_row(1, "Flipkart", T, 66990, old_price="₹73,990"),
                           synthetic_row(2, "ASUS eshop IN", T, 73990)], plan="vivobook15-broad@2"),
            synthetic_run("manual-old", "2026-10-03T19:05:53+00:00",
                          [synthetic_row(1, "Flipkart", "Asus Vivobook 15 X1504VA-NJ2324WS", 61599)],
                          plan="vivobook15-broad@1")]
    ledger = build_ledger(synthetic_evidence(*runs), config)
    rebuild(ledger, [analyse(ledger, p.product_key, config, as_of=AS_OF) for p in config.products],
            tmp_path / PROJECTION, products=config.products, plans=config.plans, as_of=AS_OF,
            coverage_policy=config.coverage)
    return tmp_path


def render(root, product):
    at = AppTest.from_file(str(MAIN), default_timeout=60)
    at.session_state["deallens_root"] = str(root)
    at.session_state["deallens_product"] = product
    return at.run()


def test_first_viewport_answers_the_judges_questions(root):
    at = render(root, "asus-x1504vap-bq224ws")
    assert not at.exception
    text = all_text(at)
    for expected in ["Lowest observed listed price", "₹66,990",
                     "2 sellers observed · 1 production run · 1 observed calendar day", "Evidence accumulating",
                     "Is ₹66,990 a good price?", "Not enough evidence yet",
                     "Keep watching — historical evidence is still accumulating.",
                     "Historical baseline not available yet"]:
        assert expected in text, expected
    for forbidden in ["great deal", "bargain", "unusually cheap", "price dropped", "lowest ever", "best price"]:
        assert forbidden not in text.lower(), forbidden


def test_sections_tell_the_whole_story(root):
    text = all_text(render(root, "asus-x1504vap-bq224ws"))
    for expected in ["Today's observed market", "Flipkart", "ASUS eshop IN",
                     "₹73,990 (shown by seller, not verified by DealLens)",
                     "What we know", "What we don't know yet", "Exact model X1504VAP-BQ224WS matched",
                     "Stock availability: unknown",
                     "Price history is not available yet",
                     "DealLens needs more observed production runs before making historical price claims.",
                     "Why DealLens says this", "Current lowest listed price", "Google Shopping via SerpApi",
                     "Evidence coverage", "Latest production observation", "2026-10-04T10:01:33+00:00",
                     "09:00 · 15:00 · 21:00 IST", "Active tracking plan", "vivobook15-broad@2"]:
        assert expected in text, expected


def test_retired_evidence_is_labelled_and_never_shown_as_current(root):
    at = render(root, "asus-x1504va-nj2324ws")
    text = all_text(at)
    assert "No current @2 observation" in text
    assert "Retired @1 evidence — not included in current @2 analysis" in text
    assert "₹61,599" not in [m.value for m in at.metric]                     # never the headline price


def test_product_with_no_observation_says_so(root):
    at = render(root, "asus-x1504ma-bq832ws")
    assert not at.exception and "No current @2 observation" in all_text(at)
