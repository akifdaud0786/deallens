"""End to end through the CLI composition root on the real 3 Oct probes (no network, no key)."""
import json
import shutil

import pytest

from conftest import BROAD, MODEL_QUERY, REPEAT, ROOT
from deallens import cli
from deallens.projection import ProjectionReader


@pytest.fixture
def project(tmp_path):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    (tmp_path / "data" / "cache").mkdir(parents=True)
    for f in (BROAD, REPEAT, MODEL_QUERY):
        shutil.copy(f, tmp_path / "data" / "cache" / f.name)
    (tmp_path / "data" / "evidence").mkdir(parents=True)
    (tmp_path / "data" / "evidence" / "probes.json").write_text(json.dumps(
        {"probes": [f"data/cache/{f.name}" for f in (BROAD, REPEAT, MODEL_QUERY)]}), encoding="utf-8")
    return tmp_path


def test_rebuild_produces_an_evidence_backed_projection(project, capsys):
    assert cli.main(["--root", str(project), "rebuild", "--as-of", "2026-10-10T18:29:59+00:00"], env={}) == 0
    r = ProjectionReader(project / "data" / "projection" / "deallens.sqlite")
    assert [w["coverage_level"] for w in r.watchlist()] == ["no_history"] * 3
    p = r.product("asus-x1504vap-bq224ws")
    # Probes are development evidence: kept and traceable, but they are not production coverage.
    assert p["coverage"]["valid_observations"] == 0 and [c["kind"] for c in p["claims"]] == ["excluded_count"]
    first = p["claims"][0]["provenance"][0]
    assert first["raw_path"] == f"data/cache/{BROAD.name}" and first["run_source"] == "manifest_less_probe"
    assert first["search_id"] == "6ac10b76a26f566bae26b24b" and first["storefront"] == "Amazon.in"
    assert "80 observations" in capsys.readouterr().out


def test_live_commands_refuse_without_explicit_live_mode(project, capsys):
    assert cli.main(["--root", str(project), "collect", "--trigger", "manual"], env={"SERPAPI_API_KEY": "x"}) == 2
    assert "DEALLENS_MODE=live" in capsys.readouterr().err
    assert cli.main(["--root", str(project), "credits"], env={"DEALLENS_MODE": "live"}) == 2
    assert not (project / "data" / "evidence" / "manifests").exists()


def test_rebuild_on_a_clean_checkout_warns_about_missing_probes(project, capsys):
    for f in (project / "data" / "cache").iterdir():
        f.unlink()                                       # data/cache is gitignored: absent on a fresh clone
    assert cli.main(["--root", str(project), "rebuild", "--as-of", "2026-10-10T18:29:59+00:00"], env={}) == 0
    err = capsys.readouterr().err
    assert "3 registered probe file(s) missing" in err and f"data/cache/{BROAD.name}" in err


def test_rebuild_supplies_ui_metadata(project):
    cli.main(["--root", str(project), "rebuild", "--as-of", "2026-10-10T18:29:59+00:00"], env={})
    r = ProjectionReader(project / "data" / "projection" / "deallens.sqlite")
    info = r.info()
    assert info["as_of"] == "2026-10-10T18:29:59+00:00" and info["missing_probes"] == []
    assert info["coverage_policy"]["sufficient_min_days"] == 5
    assert [(p["plan_ref"], p["status"]) for p in r.plans()] == [("vivobook15-broad@1", "retired"),
                                                                 ("vivobook15-broad@2", "provisional")]
    assert r.current_market("asus-x1504vap-bq224ws") == []          # probes only: no production market yet
    assert "development_probe" in r.ledger("asus-x1504vap-bq224ws")[0]["reasons"]
