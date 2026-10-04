"""Read-only JSON adapter for the React frontend.

Serves the existing view models (deallens.app.views) built from the public projection reader. No new logic:
every decision, label and number comes from analysis/projection/views. GET only; never constructs a SerpApi
client; reads no environment variables (the CLI passes the project root).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from deallens.app import views
from deallens.public import open_public_reader, projection_status


def _plain(obj):
    return dataclasses.asdict(obj) if dataclasses.is_dataclass(obj) else obj


def create_app(root, static_dir: Optional[Path] = None) -> FastAPI:
    root = Path(root)
    app = FastAPI(title="DealLens read-only API", docs_url=None, redoc_url=None, openapi_url=None)

    def reader():
        return open_public_reader(root) if projection_status(root) != "missing" else None

    @app.get("/api/status")
    def status():
        r = reader()
        return _plain(views.page_state(projection_status(root), r.info() if r else None))

    @app.get("/api/products")
    def products():
        r = reader()
        if r is None:
            return []
        plans, watchlist = r.plans(), r.watchlist()
        coverage_plans = {w["product_key"]: r.product(w["product_key"])["coverage"]["plan"] for w in watchlist}
        return [_plain(c) for c in views.snapshot_cards(watchlist, plans, coverage_plans)]

    @app.get("/api/products/{product_key}")
    def product(product_key: str):
        r = reader()
        p = r.product(product_key) if r else None
        if p is None:
            raise HTTPException(status_code=404, detail="unknown product")
        info, plans = r.info(), r.plans()
        view = views.product_view(p, r.current_market(product_key), r.price_series(product_key),
                                  r.ledger(product_key), plans, policy=info.get("coverage_policy"))
        return {"view": _plain(view), "plans": plans, "coverage_policy": info.get("coverage_policy")}

    if static_dir is not None and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
    return app
