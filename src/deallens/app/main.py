"""DealLens Streamlit entry point (read-only). Run from the repository root:

    PYTHONPATH=src streamlit run src/deallens/app/main.py

Reads only the local projection through deallens.public. Never constructs a SerpApi client.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from deallens.app import components as ui
from deallens.app import views
from deallens.public import open_public_reader, projection_status

DEFAULT_ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    st.set_page_config(page_title="DealLens", page_icon="🔎", layout="wide")
    root = Path(st.session_state.get("deallens_root", DEFAULT_ROOT))
    status = projection_status(root)
    reader = open_public_reader(root) if status != "missing" else None
    info = reader.info() if reader else None
    state = views.page_state(status, info)

    ui.header()
    ui.status_strip(state)
    if not state.show_products:
        ui.footer()
        return

    plans = reader.plans()
    watchlist = reader.watchlist()
    coverage_plans = {w["product_key"]: reader.product(w["product_key"])["coverage"]["plan"] for w in watchlist}
    cards = views.snapshot_cards(watchlist, plans, coverage_plans)
    selected = ui.product_picker(cards)
    if selected:
        product = views.product_view(reader.product(selected), reader.current_market(selected),
                                     reader.price_series(selected), reader.ledger(selected), plans,
                                     policy=info.get("coverage_policy"))
        ui.hero_and_decision(product)                      # first viewport: price, question, answer, why
        st.divider()
        ui.todays_market(product)
        ui.knowledge(product)
        if product.plan.is_current:
            ui.price_history(product)
        if product.plan.is_current or not product.plan.label:  # retired evidence is shown only in its own section
            ui.why(product)
        ui.retired_evidence(product)
        ui.coverage(product, info.get("coverage_policy"), state.latest_observation_at)
        ui.tracking_plan(product, plans)
        ui.evidence_ledger(product)
    ui.overview(cards)
    ui.unattributed(views.ledger_rows(reader.unattributed()))
    ui.footer()


main()
