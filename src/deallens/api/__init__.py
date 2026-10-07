"""Read-only JSON adapter for the React frontend.

Serves the existing view models (deallens.app.views) built from the public projection reader. No new logic:
every decision, label and number comes from analysis/projection/views. GET only; never constructs a SerpApi
client; reads no environment variables (the CLI passes the project root).

The same payloads can be written as static files (`export_static`) for a read-only GitHub Pages site; the live
API also answers the `.json` file names so one frontend build works in both places.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from deallens.app import views
from deallens.public import open_public_reader, projection_status


def _plain(obj):
    return dataclasses.asdict(obj) if dataclasses.is_dataclass(obj) else obj


def _reader(root: Path):
    return open_public_reader(root) if projection_status(root) != "missing" else None


def status_payload(root: Path) -> dict:
    r = _reader(root)
    return _plain(views.page_state(projection_status(root), r.info() if r else None))


def products_payload(root: Path) -> list:
    r = _reader(root)
    if r is None:
        return []
    plans, watchlist = r.plans(), r.watchlist()
    coverage_plans = {w["product_key"]: r.product(w["product_key"])["coverage"]["plan"] for w in watchlist}
    return [_plain(c) for c in views.snapshot_cards(watchlist, plans, coverage_plans)]


def product_payload(root: Path, product_key: str) -> Optional[dict]:
    r = _reader(root)
    p = r.product(product_key) if r else None
    if p is None:
        return None
    info, plans = r.info(), r.plans()
    view = views.product_view(p, r.current_market(product_key), r.price_series(product_key),
                              r.ledger(product_key), plans, policy=info.get("coverage_policy"))
    return {"view": _plain(view), "plans": plans, "coverage_policy": info.get("coverage_policy")}


def create_app(root, static_dir: Optional[Path] = None) -> FastAPI:
    root = Path(root)
    app = FastAPI(title="DealLens read-only API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.root = root

    @app.get("/api/status")
    @app.get("/api/status.json")
    def status():
        return status_payload(root)

    @app.get("/api/products")
    @app.get("/api/products.json")
    def products():
        return products_payload(root)

    @app.get("/api/products/{product_key}")
    def product(product_key: str):
        payload = product_payload(root, product_key.removesuffix(".json"))
        if payload is None:
            raise HTTPException(status_code=404, detail="unknown product")
        return payload

    if static_dir is not None and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
    return app


def export_static(root, out_dir) -> list[Path]:
    """Write the API's GET payloads as files under out_dir/api/ (for a read-only static site)."""
    root, out = Path(root), Path(out_dir)
    files = {"api/status.json": status_payload(root), "api/products.json": products_payload(root)}
    for card in files["api/products.json"]:
        files[f"api/products/{card['product_key']}.json"] = product_payload(root, card["product_key"])
    written = []
    for rel, payload in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        written.append(path)
    return written
