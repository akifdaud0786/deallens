"""Streamlit rendering of DealLens view models. Presentation only: every value arrives already decided.

Data-bearing strings (seller names, claims, timestamps) are rendered with st.text so Markdown can never alter them;
Markdown/HTML is used only for fixed labels and layout.
"""
from __future__ import annotations

from typing import Optional

import altair as alt
import pandas as pd
import streamlit as st

from deallens.app.views import Card, ClaimView, LedgerRow, MarketRow, PageState, ProductView

TAGLINE = "Don't just tell me the cheapest price. Tell me what today's price means."
SCHEDULE = "09:00 · 15:00 · 21:00 IST"
# Reference categorical palette (dataviz skill, light mode), fixed slot order; validated all-pairs for 3 slots.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SHAPES = ["circle", "square", "triangle-up", "diamond", "cross", "triangle-down", "triangle-left", "triangle-right"]
BADGE = {  # fixed badge text -> (background, ink); never green "good deal" colours
    "Evidence accumulating": ("#fff4d6", "#7a5300"),
    "Limited history": ("#fff4d6", "#7a5300"),
    "History available": ("#e3eefb", "#1c4f8a"),
    "No current observation": ("#f0efec", "#52514e"),
}

CSS = """
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.dl-badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.8rem; font-weight:600;}
.dl-kicker {font-size:0.78rem; letter-spacing:0.06em; text-transform:uppercase; color:#6b6a66; margin-bottom:0.2rem;}
.dl-answer {font-size:1.6rem; font-weight:700; margin:0.1rem 0 0.4rem 0;}
</style>
"""


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _kicker(label: str) -> None:
    st.markdown(f'<div class="dl-kicker">{label}</div>', unsafe_allow_html=True)


def _badge(text: str) -> None:
    bg, ink = BADGE.get(text, ("#f0efec", "#52514e"))
    st.markdown(f'<span class="dl-badge" style="background:{bg};color:{ink}">{text}</span>', unsafe_allow_html=True)


# ---------- page frame ----------

def header() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("DealLens")
    st.markdown(f"**{TAGLINE}**")
    st.caption("Read-only demo · evidence-backed commerce intelligence for tracked laptop SKUs in India · "
               "Google Shopping data via SerpApi")


def status_strip(state: PageState) -> None:
    bits = []
    if state.as_of:
        bits.append(f"Analysis built: {state.as_of} (UTC)")
    if state.latest_observation_at:
        bits.append(f"Latest observation: {state.latest_observation_at} (UTC)")
    if bits:
        st.caption(" · ".join(bits))
    for w in state.warnings:
        st.warning(w)
    if state.message:
        st.info(state.message)


def product_picker(cards: list[Card]) -> Optional[str]:
    if not cards:
        return None
    return st.radio("Tracked product", [c.product_key for c in cards], horizontal=True, key="deallens_product",
                    format_func=lambda k: next(c.model_key for c in cards if c.product_key == k))


# ---------- 1-2: hero + decision (first viewport) ----------

def hero_and_decision(v: ProductView) -> None:
    left, right = st.columns([5, 7], gap="large")
    with left:
        _kicker(v.identity.brand)
        st.subheader(v.identity.display_name)
        st.text(f"Model {v.identity.model_key} · tracking status: {v.identity.status}")
        st.metric("Lowest observed listed price", v.hero_price,
                  help="The lowest price a seller listed in the latest run. Not verified, stock unknown.")
        if v.hero_meta:
            st.text(v.hero_meta)
        _badge(v.decision.badge)
    with right, st.container(border=True):
        _kicker("DealLens decision")
        st.markdown(f"#### {v.decision.question}")
        st.markdown(f'<div class="dl-answer">{v.decision.answer}</div>', unsafe_allow_html=True)
        for ok, text in v.decision.checks:
            st.text(("✓ " if ok else "⚠ ") + text)
        _kicker("DealLens verdict")
        st.text(v.decision.verdict)


# ---------- 3: today's observed market ----------

def todays_market(v: ProductView) -> None:
    st.subheader("Today's observed market")
    if not v.plan.is_current or v.no_valid_observations:
        st.info(f"{v.decision.answer} of this product.")
        return
    st.text(f"Independent sellers (latest run): {v.kpis.independent_sellers}")
    _seller_cards(v.market)


def _seller_cards(rows: tuple[MarketRow, ...]) -> None:
    cols = st.columns(min(len(rows), 3) or 1)
    for i, m in enumerate(rows):
        with cols[i % len(cols)].container(border=True):
            st.text(m.storefront)
            st.metric("Observed listed price", m.listed_price)
            if m.list_price != "—":
                st.text(f"Seller-displayed list price: {m.list_price}")
            st.text(f"Delivery: {m.delivery} · Stock: {m.stock}")


# ---------- 4: what we know / don't know ----------

def knowledge(v: ProductView) -> None:
    left, right = st.columns(2, gap="large")
    with left, st.container(border=True):
        st.markdown("##### What we know")
        for item in v.known:
            st.text("✓ " + item)
    with right, st.container(border=True):
        st.markdown("##### What we don't know yet")
        for item in v.unknown:
            st.text("○ " + item)


# ---------- 5: price history ----------

def price_history(v: ProductView) -> None:
    st.subheader("Price history")
    if v.history.message:
        with st.container(border=True):
            st.markdown("**Price history is not available yet**")
            st.text("DealLens needs more observed production runs before making historical price claims.")
            st.text(f"{_n(v.coverage.observed_days, 'observed calendar day')} · {_n(v.coverage.runs, 'production run')} · "
                    f"{_n(v.coverage.independent_sellers, 'independent seller')}")
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


# ---------- 6: why DealLens says this ----------

def _claim_card(c: ClaimView) -> None:
    with st.container(border=True):
        _kicker(c.title)
        st.text(c.text)
        runs = sorted({e.run_id for e in c.evidence})
        st.caption(f"Evidence {c.claim_id} · {c.kind} · Source: {c.source} · Run: {', '.join(runs)}")
        with st.expander("Evidence details"):
            st.dataframe(pd.DataFrame([{"Storefront": e.storefront, "Observed at (UTC)": e.fetched_at,
                                        "Day (IST)": e.observed_day, "Run": e.run_id, "Source": e.source,
                                        "Search id": e.search_id, "Raw response": e.raw_path,
                                        "SHA-256": e.raw_sha256[:12] + "…"} for e in c.evidence]), hide_index=True)


def why(v: ProductView) -> None:
    st.subheader("Why DealLens says this")
    st.caption("Every statement is a deterministic claim computed from observations DealLens collected. "
               "Full summary, exactly as generated:")
    st.text(v.summary)
    cols = st.columns(2)
    for i, c in enumerate(v.claims):
        with cols[i % 2]:
            _claim_card(c)


# ---------- retired evidence ----------

def retired_evidence(v: ProductView) -> None:
    if not v.plan.label:
        return
    with st.container(border=True):
        st.markdown(f"**{v.plan.label}**")
        st.caption("Shown for transparency only. It does not feed the decision above.")
        st.text(f"Independent sellers (latest run): {v.kpis.independent_sellers}")
        st.dataframe(pd.DataFrame([{"Storefront": m.storefront, "Listed price": m.listed_price,
                                    "Displayed list price": m.list_price, "Delivery": m.delivery, "Stock": m.stock,
                                    "Observed at (UTC)": m.observed_at} for m in v.market]), hide_index=True)
        st.text(v.summary)
        for c in v.claims:
            _claim_card(c)


# ---------- 7-8: coverage, collection, plan ----------

def coverage(v: ProductView, policy: Optional[dict], latest_observation_at: Optional[str]) -> None:
    st.subheader("Evidence coverage")
    c = v.coverage
    if not v.plan.is_current and v.plan.shown_ref:
        st.caption(f"Figures below are from {v.plan.shown_ref}, not the active plan.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Observed calendar days", c.observed_days)
    m2.metric("Production runs", c.runs)
    m3.metric("Independent sellers", c.independent_sellers)
    m4.metric("Valid observations", c.valid_observations)
    st.markdown(f"{c.level} · {_n(c.observed_days, 'observed calendar day')} · {_n(c.runs, 'run')} · "
                f"{_n(c.valid_observations, 'valid observation')} · {_n(c.independent_sellers, 'independent seller')}")
    if c.level_code != "sufficient_history":
        st.text("Historical conclusions require more observed production data.")
    if policy:
        st.caption(f"DealLens policy: history claims need at least {policy['limited_min_days']} observed calendar days and "
                   f"{policy['limited_min_runs']} runs; low/high/average need {policy['sufficient_min_days']} calendar days, "
                   f"{policy['sufficient_min_runs']} runs and {policy['sufficient_min_sellers']} independent sellers. "
                   "This is a product policy, not a statistical guarantee. Calendar days are counted in IST and say "
                   "on how many dates prices were observed, not how long a period is covered.")
    a, b = st.columns(2)
    with a:
        _kicker("Latest production observation")
        st.text(f"{latest_observation_at} UTC" if latest_observation_at else "—")
    with b:
        _kicker("Collection schedule")
        st.text(f"{SCHEDULE} · GitHub Actions · one Google Shopping call per slot")


def tracking_plan(v: ProductView, plans: list[dict]) -> None:
    with st.container(border=True):
        _kicker("Active tracking plan")
        st.text(f"{v.plan.active_ref or '—'} · Active")
        for p in plans:
            if p["plan_ref"] != v.plan.active_ref:
                st.text(f"{p['plan_ref']} · {p['status']} — not combined with the active plan")


# ---------- reference ----------

def overview(cards: list[Card]) -> None:
    with st.expander("All tracked products"):
        cols = st.columns(len(cards)) if cards else []
        for col, c in zip(cols, cards):
            with col.container(border=True):
                st.text(c.model_key)
                st.caption(c.display_name)
                st.text(f"Lowest listed price (latest run): {c.lowest_listed}")
                sellers = "—" if c.independent_sellers is None else c.independent_sellers
                st.caption(f"Independent sellers (observed window): {sellers} · {c.coverage} · {c.history}")


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
               "“Development probe” come from test searches made before scheduled collection began and never count.")
