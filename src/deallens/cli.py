"""Composition root. The only module that reads environment variables or constructs the live SerpApi adapter.

    python -m deallens.cli rebuild
    python -m deallens.cli ledger [product_key]
    DEALLENS_MODE=live python -m deallens.cli credits | collect --trigger scheduled --target-time ... | investigate <id>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from deallens.analysis import analyse
from deallens.config import load_config
from deallens.evidence import EvidenceStore
from deallens.market import build_ledger
from deallens.projection import rebuild
from deallens.public import PROJECTION

LIVE_COMMANDS = {"credits", "collect", "investigate"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _live_serpapi(env):
    if env.get("DEALLENS_MODE") != "live":
        raise SystemExit("live commands require DEALLENS_MODE=live")
    key = env.get("SERPAPI_API_KEY")
    if not key:
        raise SystemExit("live commands require SERPAPI_API_KEY in the environment")
    from deallens.serpapi.http import HttpSerpApi      # only place the live adapter is constructed
    return HttpSerpApi(key)


def _load_dotenv(root: Path, env: dict) -> dict:
    """Local convenience: values from <root>/.env fill in missing environment variables. Never logged."""
    f = root / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() and not line.lstrip().startswith("#"):
                env.setdefault(k.strip(), v.strip())
    return env


def cmd_rebuild(root: Path, as_of: str) -> int:
    config = load_config(root / "config")
    evidence = EvidenceStore(root).read_all()
    if evidence.missing_probes:
        print(f"warning: {len(evidence.missing_probes)} registered probe file(s) missing from this checkout "
              f"(data/cache is gitignored); rebuilding without them: {', '.join(evidence.missing_probes)}",
              file=sys.stderr)
    ledger = build_ledger(evidence, config)
    analyses = [analyse(ledger, p.product_key, config, as_of=as_of) for p in config.products]
    info = rebuild(ledger, analyses, root / PROJECTION, products=config.products, plans=config.plans,
                   missing_probes=evidence.missing_probes, as_of=as_of, coverage_policy=config.coverage)
    print(f"projection rebuilt: {info.observations} observations, {info.products} products -> {info.path}")
    for a in analyses:
        print(f"  {a.product_key}: {a.coverage.level.value}, {a.coverage.valid_observations} valid")
    return 0


def main(argv=None, env=None) -> int:
    ap = argparse.ArgumentParser(prog="deallens")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rb = sub.add_parser("rebuild")
    rb.add_argument("--as-of", default=None)
    lg = sub.add_parser("ledger")
    lg.add_argument("product_key", nargs="?")
    sub.add_parser("credits")
    co = sub.add_parser("collect")
    co.add_argument("--trigger", choices=["scheduled", "manual"], required=True)
    co.add_argument("--target-time", default=None)
    sl = sub.add_parser("slot", help="print the explicit IST slot for a scheduler cron (no network)")
    sl.add_argument("--cron", required=True)
    sl.add_argument("--now", default=None, help="UTC ISO time; defaults to the current time")
    sv = sub.add_parser("serve", help="read-only JSON API + built React frontend (no SerpApi calls)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    ex = sub.add_parser("export-static", help="write the API's JSON as static files for a read-only site")
    ex.add_argument("--out", default="frontend/dist")
    inv = sub.add_parser("investigate")
    inv.add_argument("observation_id")
    args = ap.parse_args(argv)
    root = Path(args.root)
    env = dict(os.environ) if env is None else dict(env)

    try:
        if args.cmd == "rebuild":
            return cmd_rebuild(root, args.as_of or _now())
        if args.cmd == "slot":
            from deallens.collector.schedule import scheduled_slot
            slots = load_config(root / "config").collector.scheduled_slots_ist
            try:
                print(scheduled_slot(args.cron, args.now or _now(), slots))
            except ValueError as e:
                print(str(e), file=sys.stderr)
                return 2
            return 0
        if args.cmd == "serve":
            import uvicorn
            from deallens.api import create_app
            uvicorn.run(create_app(root, static_dir=root / "frontend" / "dist"), host=args.host, port=args.port)
            return 0
        if args.cmd == "export-static":
            from deallens.api import export_static
            written = export_static(root, Path(args.out))
            print(f"exported {len(written)} files to {args.out}")
            return 0
        if args.cmd == "ledger":
            from deallens.public import open_public_reader
            for row in open_public_reader(root).ledger(args.product_key):
                print(json.dumps({k: row[k] for k in ("observation_id", "storefront", "listed_price_inr", "included",
                                                       "reasons", "match_outcome")}, ensure_ascii=False))
            return 0
        if args.cmd in LIVE_COMMANDS:
            env = _load_dotenv(root, env) if env.get("DEALLENS_MODE") == "live" else env
            api = _live_serpapi(env)
            config = load_config(root / "config")
            store = EvidenceStore(root)
            if args.cmd == "credits":
                print(json.dumps({"plan_searches_left": api.credits().plan_searches_left}))
                return 0
            if args.cmd == "collect":
                from deallens.collector import collect
                m = collect(config, api, store, trigger=args.trigger, target_time=args.target_time, now=_now)
                print(json.dumps({"run_id": m.run_id, "status": m.status.value, "skip_reason": m.skip_reason,
                                  "searches": [s.status.value for s in m.searches]}))
                return 0 if m.status.value in ("completed", "skipped") else 1
            if args.cmd == "investigate":
                from deallens.investigation import investigate, sanitize
                ledger = build_ledger(store.read_all(), config)
                inv = investigate(ledger.get(args.observation_id), api, store, config, now=_now)
                print(json.dumps(sanitize(inv), ensure_ascii=False))
                return 0 if inv.status.value == "succeeded" else 1
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
