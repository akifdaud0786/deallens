"""Static, read-only site export (GitHub Pages): the same JSON the API serves, written as files."""
import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from deallens.api import create_app, export_static  # noqa: E402
from test_api import BQ224, BQ832, NJ, client  # noqa: E402,F401  (fixture reused)


def test_export_writes_exactly_what_the_api_serves(client, tmp_path):
    root = client.app.state.root
    out = tmp_path / "site"
    written = export_static(root, out)
    assert sorted(p.relative_to(out).as_posix() for p in written) == sorted([
        "api/status.json", "api/products.json",
        f"api/products/{BQ224}.json", f"api/products/{BQ832}.json", f"api/products/{NJ}.json"])
    for path, url in [("api/status.json", "/api/status"), ("api/products.json", "/api/products"),
                      (f"api/products/{BQ224}.json", f"/api/products/{BQ224}")]:
        assert json.loads((out / path).read_text(encoding="utf-8")) == client.get(url).json()


def test_json_routes_match_the_static_file_names(client):
    """The frontend fetches `api/....json`; the live API answers the same paths."""
    for plain, dotted in [("/api/status", "/api/status.json"), ("/api/products", "/api/products.json"),
                          (f"/api/products/{BQ224}", f"/api/products/{BQ224}.json")]:
        assert client.get(dotted).json() == client.get(plain).json()


def test_export_of_a_missing_projection_is_honest(tmp_path):
    out = tmp_path / "site"
    export_static(tmp_path, out)
    assert json.loads((out / "api" / "status.json").read_text(encoding="utf-8"))["status"] == "missing"
    assert json.loads((out / "api" / "products.json").read_text(encoding="utf-8")) == []


def test_exported_site_carries_no_secrets_or_private_evidence(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "would-be-secret-key-0123456789")
    out = tmp_path / "site"
    export_static(client.app.state.root, out)
    blob = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*.json"))
    for bad in ("would-be-secret-key", "api_key", "data/private", "immersive", "Synthetic Reviewer", "serpapi.com"):
        assert bad not in blob, bad


def test_cli_export_static(client, tmp_path, capsys):
    from deallens import cli
    out = tmp_path / "site"
    assert cli.main(["--root", str(client.app.state.root), "export-static", "--out", str(out)], env={}) == 0
    assert (out / "api" / "products.json").exists() and "5 files" in capsys.readouterr().out


def test_create_app_records_its_root(tmp_path):
    assert TestClient(create_app(tmp_path)).app.state.root == tmp_path
