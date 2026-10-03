"""Disposable SQLite read model (ADR 0001). Stores what market/analysis computed; decides nothing.

rebuild() replaces the file atomically; ProjectionReader serves the UI.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Iterable, Optional

from deallens.domain import DealAnalysis, Ledger

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE products (ord INTEGER, product_key TEXT PRIMARY KEY, brand TEXT, model_key TEXT, display_name TEXT,
                       status TEXT);
CREATE TABLE analyses (product_key TEXT PRIMARY KEY, as_of TEXT, plan TEXT, other_plans TEXT, coverage_level TEXT,
                       observed_days TEXT, runs TEXT, sellers TEXT, independent_sellers INTEGER,
                       valid_observations INTEGER, summary TEXT, summary_source TEXT, config_versions TEXT,
                       latest_run_id TEXT, observation_ids TEXT);
CREATE TABLE claims (claim_id TEXT PRIMARY KEY, product_key TEXT, ord INTEGER, kind TEXT, text TEXT, params TEXT,
                     min_level TEXT);
CREATE TABLE claim_support (claim_id TEXT, ord INTEGER, observation_id TEXT, raw_path TEXT, raw_sha256 TEXT,
                            run_id TEXT, run_source TEXT, search_id TEXT, storefront TEXT, fetched_at TEXT);
CREATE TABLE observations (ord INTEGER, observation_id TEXT PRIMARY KEY, product_key TEXT, candidates TEXT,
                           match_outcome TEXT, included INTEGER, reasons TEXT, storefront TEXT, seller_key TEXT,
                           title TEXT, listed_price_inr REAL, price_raw TEXT, list_price_inr REAL, list_price_raw TEXT,
                           delivery_raw TEXT, stock_status TEXT, fetched_at TEXT, observed_day TEXT, run_id TEXT,
                           run_source TEXT, search_id TEXT, plan TEXT, raw_path TEXT, raw_sha256 TEXT,
                           google_ids TEXT, outlier_check TEXT);
CREATE TABLE runs (run_id TEXT PRIMARY KEY, source TEXT, status TEXT);
CREATE TABLE plans (ord INTEGER, plan_ref TEXT PRIMARY KEY, plan_id TEXT, version INTEGER, status TEXT,
                    effective_from TEXT, rationale TEXT, params TEXT, serves TEXT);
"""


@dataclass(frozen=True)
class ProjectionInfo:
    path: str
    observations: int
    products: int
    config_versions: dict


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def rebuild(ledger: Ledger, analyses: Iterable[DealAnalysis], path, *, products, plans=(), missing_probes=(),
            as_of: Optional[str] = None, coverage_policy=None) -> ProjectionInfo:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    try:
        db.executescript(SCHEMA)
        policy = asdict(coverage_policy) if is_dataclass(coverage_policy) else coverage_policy
        db.executemany("INSERT INTO meta VALUES (?, ?)", sorted({
            "config_versions": _j(dict(ledger.config_versions)),
            # Only shareable evidence may be named here: private (Immersive) raws never reach the projection.
            "sources": _j(sorted({r.ref.path: r.ref.sha256 for r in ledger.raws
                                  if r.sensitivity == "shareable"}.items())),
            "as_of": _j(as_of),
            "missing_probes": _j(list(missing_probes)),
            "coverage_policy": _j(policy),
            "observations": _j(len(ledger.observations)),
            "latest_observation_at": _j(max((o.fetched_at for o in ledger.observations), default=None)),
        }.items()))
        db.executemany("INSERT INTO plans VALUES (?,?,?,?,?,?,?,?,?)", [
            (i, q.ref, q.plan_id, q.version, q.status, q.effective_from, q.rationale, _j(dict(q.params)),
             _j(list(q.serves))) for i, q in enumerate(plans)])
        db.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)",
                       [(i, p.product_key, p.brand, p.model_key, p.display_name, p.status) for i, p in enumerate(products)])
        for a in analyses:
            c = a.coverage
            db.execute("INSERT INTO analyses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (a.product_key, a.as_of, c.plan, _j(list(c.other_plans_not_combined)), c.level.value,
                        _j(list(c.observed_days)), _j(list(c.runs)), _j(list(c.sellers)), c.independent_seller_count,
                        c.valid_observations, a.summary, a.summary_source, _j(dict(a.config_versions)),
                        c.latest_run_id, _j(list(c.observation_ids))))
            for i, cl in enumerate(a.claims):
                db.execute("INSERT INTO claims VALUES (?,?,?,?,?,?,?)",
                           (cl.claim_id, a.product_key, i, cl.kind, cl.text, _j(dict(cl.params)), cl.min_level.value))
                db.executemany("INSERT INTO claim_support VALUES (?,?,?,?,?,?,?,?,?,?)", [
                    (cl.claim_id, j, p.observation_id, p.raw_path, p.raw_sha256, p.run_id, p.run_source.value,
                     p.search_id, p.storefront, p.fetched_at) for j, p in enumerate(cl.provenance)])
        db.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            (i, o.observation_id, o.match.product_key, _j(list(o.match.candidates)), o.match.outcome.value,
             int(o.included), _j([r.value for r in o.reasons]), o.storefront, o.seller_key, o.title,
             o.listed_price_inr, o.price_raw, o.list_price.list_price_inr, o.list_price_raw, o.delivery_raw,
             o.stock_status, o.fetched_at, o.observed_day, o.run_id, o.run_source.value, o.search_id, o.plan,
             o.raw_ref.path, o.raw_ref.sha256, _j(dict(o.google_ids)), o.outlier_check)
            for i, o in enumerate(ledger.observations)])
        db.executemany("INSERT INTO runs VALUES (?,?,?)",
                       [(r.run_id, r.source.value, r.status.value if r.status else None) for r in ledger.runs])
        db.commit()
    finally:
        db.close()
    os.replace(tmp, path)
    return ProjectionInfo(str(path), len(ledger.observations), len(list(products)), dict(ledger.config_versions))


class ProjectionReader:
    def __init__(self, path):
        self.path = Path(path)

    def _rows(self, sql: str, args=()) -> list[dict]:
        db = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in db.execute(sql, args)]
        finally:
            db.close()

    def info(self) -> dict:
        return {r["key"]: json.loads(r["value"]) for r in self._rows("SELECT * FROM meta ORDER BY key")}

    def watchlist(self) -> list[dict]:
        out = []
        for p in self._rows("SELECT p.*, a.coverage_level, a.independent_sellers, a.valid_observations "
                            "FROM products p LEFT JOIN analyses a USING (product_key) ORDER BY p.ord"):
            low = self._rows("SELECT params FROM claims WHERE product_key=? AND kind='current_lowest_listed'",
                             (p["product_key"],))
            p.pop("ord")
            p["lowest_listed_inr"] = json.loads(low[0]["params"])["price_inr"] if low else None
            out.append(p)
        return out

    def product(self, product_key: str) -> Optional[dict]:
        rows = self._rows("SELECT * FROM analyses WHERE product_key=?", (product_key,))
        if not rows:
            return None
        a = rows[0]
        prod = self._rows("SELECT brand, model_key, display_name, status FROM products WHERE product_key=?",
                          (product_key,))[0]
        claims = [self.claim(c["claim_id"]) for c in
                  self._rows("SELECT claim_id FROM claims WHERE product_key=? ORDER BY ord", (product_key,))]
        return {"product_key": product_key, **prod, "as_of": a["as_of"], "summary": a["summary"],
                "summary_source": a["summary_source"], "config_versions": json.loads(a["config_versions"]),
                "coverage": {"level": a["coverage_level"], "plan": a["plan"],
                             "other_plans_not_combined": json.loads(a["other_plans"]),
                             "observed_days": json.loads(a["observed_days"]), "runs": json.loads(a["runs"]),
                             "sellers": json.loads(a["sellers"]), "independent_sellers": a["independent_sellers"],
                             "valid_observations": a["valid_observations"], "latest_run_id": a["latest_run_id"]},
                "claims": claims}

    def claim(self, claim_id: str) -> Optional[dict]:
        rows = self._rows("SELECT * FROM claims WHERE claim_id=?", (claim_id,))
        if not rows:
            return None
        c = rows[0]
        c.pop("ord")
        c["params"] = json.loads(c["params"])
        c["provenance"] = [{k: v for k, v in s.items() if k not in ("claim_id", "ord")} for s in
                           self._rows("SELECT * FROM claim_support WHERE claim_id=? ORDER BY ord", (claim_id,))]
        return c

    def ledger(self, product_key: Optional[str] = None) -> list[dict]:
        rows = self._rows("SELECT * FROM observations ORDER BY ord")
        if product_key:
            rows = [r for r in rows if product_key in json.loads(r["candidates"])]
        for r in rows:
            r.pop("ord")
            r["included"] = bool(r["included"])
            for k in ("reasons", "candidates", "google_ids"):
                r[k] = json.loads(r[k])
        return rows

    def _coverage_rows(self, product_key: str) -> tuple[list[dict], Optional[str]]:
        """Observations analysis put in this product's Coverage (one plan version), in Coverage order."""
        rows = self._rows("SELECT observation_ids, latest_run_id FROM analyses WHERE product_key=?", (product_key,))
        if not rows:
            return [], None
        ids = json.loads(rows[0]["observation_ids"])
        by_id = {r["observation_id"]: r for r in self._rows(
            f"SELECT * FROM observations WHERE observation_id IN ({','.join('?' * len(ids))})", ids)} if ids else {}
        out = []
        for i in ids:
            r = by_id[i]
            r.pop("ord")
            r["included"] = bool(r["included"])
            for k in ("reasons", "candidates", "google_ids"):
                r[k] = json.loads(r[k])
            out.append(r)
        return out, rows[0]["latest_run_id"]

    def price_series(self, product_key: str) -> list[dict]:
        """Included Observations of the Coverage plan only; never mixes Query Plan versions."""
        return self._coverage_rows(product_key)[0]

    def current_market(self, product_key: str) -> list[dict]:
        """Included Observations from the Coverage's latest run (as decided by analysis)."""
        rows, latest = self._coverage_rows(product_key)
        return [r for r in rows if r["run_id"] == latest]

    def plans(self) -> list[dict]:
        out = []
        for p in self._rows("SELECT * FROM plans ORDER BY ord"):
            p.pop("ord")
            p["params"], p["serves"] = json.loads(p["params"]), json.loads(p["serves"])
            out.append(p)
        return out

    def unattributed(self) -> list[dict]:
        """Observations attributed to no single product (unmatched or ambiguous), as Ledger.unattributed()."""
        return [r for r in self.ledger() if r["match_outcome"] != "matched"]

    def runs(self) -> list[dict]:
        return self._rows("SELECT * FROM runs ORDER BY run_id")
