"""Streamlit rendering of DealLens view models. Presentation only: every value arrives already decided."""
from __future__ import annotations

from typing import Optional

import altair as alt
import pandas as pd
import streamlit as st

from deallens.app.views import Card, LedgerRow, PageState, ProductView

TAGLINE = "Don't just tell me the cheapest price. Tell me what today's price means."
# Reference categorical palette (dataviz skill, light mode), fixed slot order; validated all-pairs for 3 slots.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SHAPES = ["circle", "square", "triangle-up", "diamond", "cross", "triangle-down", "triangle-left", "triangle-right"]


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def header() -> None:
    st.title("DealLens")
    st.markdown(f"**{TAGLINE}**")
    st.caption("Read-only demo · evidence-backed price intelligence for tracked laptop SKUs in India")


def status_strip(state: PageState) -> None:
    bits = ["Read-only view of the DealLens projection", "Google Shopping (India) data via SerpApi"]
    if state.latest_observation_at:
        bits.insert(1, f"Latest observation: {state.latest_observation_at} (UTC)")
    if state.as_of:
        bits.insert(1, f"Analysis built: {state.as_of} (UTC)")
    st.caption(" · ".join(bits))
    for w in state.warnings:
        st.warning(w)
    if state.message:
        st.info(state.message)


def market_snapshot(cards: list[Card]) -> Optional[str]:
    st.subheader("Market snapshot")
    cols = st.columns(len(cards)) if cards else []
    for col, c in zip(cols, cards):
        with col.container(border=True):
            st.markdown(f"**{c.model_key}**")
            st.caption(c.display_name)
            st.metric("Lowest listed price (latest run)", c.lowest_listed)
            sellers = "—" if c.independent_sellers is None else c.independent_sellers
            st.caption(f"Independent sellers (observed window): {sellers} · {c.coverage} · {c.history}")
    if not cards:
        return None
    return st.radio("Selected product", [c.product_key for c in cards], horizontal=True, key="deallens_product",
                    format_func=lambda k: next(c.model_key for c in cards if c.product_key == k))


def product_identity(v: ProductView) -> None:
    i = v.identity
    st.header(i.display_name)
    plan = f"Query Plan `{i.plan_ref}` ({i.plan_status}) · query “{i.plan_query}”" if i.plan_ref else "No Query Plan yet"
    st.caption(f"{i.brand} · model `{i.model_key}` · product status: {i.status} · {plan}")
    if i.other_plans:
        st.caption("Observations from other Query Plan versions are not combined here: " + ", ".join(i.other_plans))


def kpis(v: ProductView) -> None:
    k = v.kpis
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lowest listed price", k.lowest_listed, help="Latest run. Stock status unknown.")
    c1.caption(f"at {k.lowest_listed_at}" if k.lowest_listed_at else "no included observation")
    c2.metric("Independent sellers (latest run)", "—" if k.independent_sellers is None else k.independent_sellers)
    c3.metric("Valid observations", k.valid_observations)
    c4.metric("Observed calendar days / runs", f"{k.observed_days} / {k.runs}")


def current_market(v: ProductView) -> None:
    st.subheader("Current market")
    if v.no_valid_observations:
        st.info("No valid observations yet for this product under the current Query Plan.")
        return
    st.dataframe(pd.DataFrame([{"Storefront": m.storefront, "Listed price": m.listed_price,
                                "Displayed list price": m.list_price, "Delivery": m.delivery, "Stock": m.stock}
                               for m in v.market]), hide_index=True)


def deal_intelligence(v: ProductView) -> None:
    st.subheader("Deal intelligence")
    # Analysis text is rendered literally (st.text), never as Markdown, so it appears exactly as computed.
    st.text(v.summary)
    for c in v.claims:
        st.caption(c.claim_id)
        st.text(c.text)


def price_history(v: ProductView) -> None:
    st.subheader("Price history")
    if v.history.message:
        st.info(v.history.message)
        return
    df = pd.DataFrame([{"Observed at (UTC)": p.observed_at, "Day (IST)": p.day, "Storefront": p.storefront,
                        "Observed listed price": p.price, "Price": p.price_label} for p in v.history.points])
    stores = sorted(df["Storefront"].unique())
    color = alt.Color("Storefront:N", scale=alt.Scale(domain=stores, range=SERIES[:len(stores)]),
                      legend=alt.Legend(title="Storefront"))
    chart = (alt.Chart(df, title="Observed listed price")
             .mark_point(filled=True, size=90, opacity=1)
             .encode(x=alt.X("Observed at (UTC):T", title="Observed at (UTC)"),
                     y=alt.Y("Observed listed price:Q", title="Observed listed price (₹)", scale=alt.Scale(zero=False)),
                     color=color,
                     shape=alt.Shape("Storefront:N", scale=alt.Scale(domain=stores, range=SHAPES[:len(stores)]),
                                     legend=None),
                     tooltip=["Storefront", "Price", "Day (IST)", "Observed at (UTC)"]))
    st.altair_chart(chart)
    st.caption("Each point is one observation collected by DealLens. Points are not joined: prices between "
               "observations are unknown.")
    with st.expander("Observed points as a table"):
        st.dataframe(df[["Day (IST)", "Observed at (UTC)", "Storefront", "Price"]], hide_index=True)


def coverage(v: ProductView, policy: Optional[dict]) -> None:
    st.subheader("Coverage")
    c = v.coverage
    st.markdown(f"{c.level} · {_n(c.observed_days, 'observed calendar day')} · {_n(c.runs, 'run')} · "
                f"{_n(c.valid_observations, 'valid observation')} · {_n(c.independent_sellers, 'independent seller')}")
    st.caption("Calendar days are counted in India time (IST): they say on how many dates DealLens observed "
               "prices, not how long a period is covered.")
    if policy:
        st.caption(f"DealLens policy: history claims need at least {policy['limited_min_days']} observed calendar days and "
                   f"{policy['limited_min_runs']} runs; low/high/average need {policy['sufficient_min_days']} calendar days, "
                   f"{policy['sufficient_min_runs']} runs and {policy['sufficient_min_sellers']} independent sellers. "
                   "This is a product policy, not a statistical guarantee.")


def evidence(v: ProductView) -> None:
    st.subheader("Evidence")
    st.caption("Every claim is based only on observations collected by DealLens.")
    for c in v.claims:
        with st.expander(f"{c.claim_id} · {c.kind}"):
            st.text(c.text)
            st.dataframe(pd.DataFrame([{"Storefront": e.storefront, "Observed at (UTC)": e.fetched_at,
                                        "Day (IST)": e.observed_day, "Run": e.run_id, "Source": e.source,
                                        "Search id": e.search_id, "Raw response": e.raw_path,
                                        "SHA-256": e.raw_sha256[:12] + "…"} for e in c.evidence]), hide_index=True)


def _ledger_table(rows: tuple[LedgerRow, ...]) -> None:
    st.dataframe(pd.DataFrame([{"Included": "yes" if r.included else "no", "Reasons": "; ".join(r.reasons) or "—",
                                "Storefront": r.storefront, "Price": r.listed_price, "Title": r.title,
                                "Match": r.match, "Day (IST)": r.observed_day, "Source": r.source,
                                "Observation": r.observation_id} for r in rows]), hide_index=True)


def evidence_ledger(v: ProductView) -> None:
    with st.expander(f"Evidence ledger for this product ({len(v.ledger)} observations, included and excluded)"):
        _ledger_table(v.ledger)


def unattributed(rows: tuple[LedgerRow, ...]) -> None:
    with st.expander(f"Observations not attributed to any tracked product ({len(rows)})"):
        st.caption("Unmatched or ambiguous results are kept for transparency and never enter statistics.")
        if rows:
            _ledger_table(rows)


def footer() -> None:
    st.divider()
    st.caption("Observed data only: prices are what DealLens saw at the listed times, not all-time lows or "
               "predictions. List prices are displayed by sellers and not verified by DealLens. Stock status is "
               "unknown unless a source stated it. Google Shopping data via SerpApi. Rows labelled "
               "“Development probe” come from test searches made before scheduled collection began.")
