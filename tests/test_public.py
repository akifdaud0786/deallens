"""Public read-only composition: projection status for cold-start UI states."""
from deallens.analysis import analyse
from deallens.market import build_ledger
from deallens.projection import rebuild
from deallens.public import PROJECTION, projection_status
from synthetic import synthetic_evidence

AS_OF = "2026-10-10T18:29:59+00:00"


def test_status_is_missing_when_no_projection_was_built(tmp_path):
    assert projection_status(tmp_path) == "missing"


def test_status_is_empty_when_the_projection_has_no_observations(tmp_path, config):
    ledger = build_ledger(synthetic_evidence(), config)
    rebuild(ledger, [analyse(ledger, p.product_key, config, as_of=AS_OF) for p in config.products],
            tmp_path / PROJECTION, products=config.products)
    assert projection_status(tmp_path) == "empty"


def test_status_is_ready_with_observations(tmp_path, config, probe_ledger):
    rebuild(probe_ledger, [], tmp_path / PROJECTION, products=config.products)
    assert projection_status(tmp_path) == "ready"
