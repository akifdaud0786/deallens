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

    selected = ui.market_snapshot(views.snapshot_cards(reader.watchlist()))
    if selected:
        product = views.product_view(reader.product(selected), reader.current_market(selected),
                                     reader.price_series(selected), reader.ledger(selected), reader.plans())
        st.divider()
        ui.product_identity(product)
        ui.kpis(product)
        ui.current_market(product)
        ui.deal_intelligence(product)
        ui.price_history(product)
        ui.coverage(product, info.get("coverage_policy"))
        ui.evidence(product)
        ui.evidence_ledger(product)
    ui.unattributed(views.ledger_rows(reader.unattributed()))
    ui.footer()


main()
