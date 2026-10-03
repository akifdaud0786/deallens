from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
SHOPPING = FIXTURES / "shopping"
BROAD = SHOPPING / "20261003T140442Z_shopping.json"
REPEAT = SHOPPING / "20261003T140455Z_shopping.json"
MODEL_QUERY = SHOPPING / "20261003T144432Z_shopping.json"


@pytest.fixture(scope="session")
def config():
    from deallens.config import load_config
    return load_config(ROOT / "config")


@pytest.fixture(scope="session")
def probe_evidence(tmp_path_factory):
    """The three real 3 Oct probes, registered as manifest-less probes in a scratch project root."""
    import json
    import shutil
    from deallens.evidence import EvidenceStore
    root = tmp_path_factory.mktemp("probes")
    (root / "data" / "cache").mkdir(parents=True)
    for f in (BROAD, REPEAT, MODEL_QUERY):
        shutil.copy(f, root / "data" / "cache" / f.name)
    (root / "data" / "evidence").mkdir(parents=True)
    (root / "data" / "evidence" / "probes.json").write_text(json.dumps(
        {"probes": [f"data/cache/{f.name}" for f in (BROAD, REPEAT, MODEL_QUERY)]}), encoding="utf-8")
    return EvidenceStore(root).read_all()


@pytest.fixture(scope="session")
def probe_ledger(probe_evidence, config):
    """Real semantics: manifest-less probes are kept but excluded as development_probe."""
    from deallens.market import build_ledger
    return build_ledger(probe_evidence, config)


@pytest.fixture(scope="session")
def fixture_ledger(probe_evidence, config):
    """The same real 3 Oct rows re-labelled as a production run (`fixture:` run ids), for tests that exercise
    production matching/claims on real data. Not a stand-in for real history."""
    from deallens.market import build_ledger
    from synthetic import as_production
    return build_ledger(as_production(probe_evidence), config)
