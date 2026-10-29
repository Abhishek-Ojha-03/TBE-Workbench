"""
Commercial Evaluation Screen — Part 2 (Price Bid Opening)
=========================================================
Two-Envelope Rule:
  • Only technically QUALIFIED bidders appear here.
  • Price data NEVER leaks into Part-1 Technical screens.
  • L1 = lowest price, L2 = second lowest, …
  • Tie → both get same L-rank; committee must resolve manually.
"""
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session

from db.models import Tender, Bidder
from db.commercial_service import (
    get_qualified_bidders,
    save_price_for_bidder,
    compute_commercial_ranking,
)


def _fmt_price(price: float, currency: str) -> str:
    """Format price with currency symbol and thousands separator."""
    sym = "₹" if currency == "INR" else currency
    return f"{sym} {price:,.2f}"


def render_commercial_screen(db: Session, tender: Tender):
    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="background:#0e2a47;padding:16px 20px;border-radius:8px;color:#fff;margin-bottom:20px;">
            <h2 style="margin:0;font-size:22px;">💰 Commercial Evaluation — Part 2 (Price Bid Opening)</h2>
            <p style="margin:4px 0 0;color:#a0aec0;font-size:13px;">
                Two-Envelope System · Only Technically Qualified Bidders · L1/L2/L3 Ranking
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "📋 **Two-Envelope Rule:** Price bids are opened **only after** all technical "
        "evaluations are finalised. Unqualified bidders are automatically excluded from "
        "this stage per procurement policy.",
        icon="ℹ️",
    )

    # ── Qualified bidders ────────────────────────────────────────────────────
    qualified = get_qualified_bidders(db, tender.id)
    all_bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all()
    unqualified = [b for b in all_bidders if b.final_status != "Qualified"]

    if not qualified:
        st.warning(
            "⚠️ No bidders have been marked **Qualified** yet. "
            "Complete the Technical Evaluation and set Final Status to **Qualified** "
            "in the Reports & Completion screen before opening price bids.",
            icon="⚠️",
        )
        if unqualified:
            st.caption(
                f"Bidders currently in the pool: "
                + ", ".join(f"**{b.name}** ({b.final_status})" for b in all_bidders)
            )
        return

    st.success(
        f"✅ **{len(qualified)}** technically qualified bidder(s) are eligible for "
        f"commercial evaluation. "
        + (f"  ⛔ {len(unqualified)} excluded (not qualified)." if unqualified else ""),
        icon="✅",
    )

    st.divider()

    # ── Price Entry Form ─────────────────────────────────────────────────────
    st.subheader("📝 Enter Quoted Prices")
    st.caption("Enter the price exactly as quoted in each bidder's commercial (price) envelope.")

    currency_options = ["INR", "USD", "EUR", "GBP", "JPY", "SGD"]

    with st.form("commercial_price_form"):
        price_inputs = {}
        currency_inputs = {}

        for b in qualified:
            cols = st.columns([3, 2, 2])
            with cols[0]:
                st.markdown(f"**{b.name}**")
            with cols[1]:
                price_inputs[b.id] = st.number_input(
                    f"Quoted Price — {b.name}",
                    min_value=0.0,
                    value=float(b.quoted_price) if b.quoted_price is not None else 0.0,
                    step=1000.0,
                    format="%.2f",
                    label_visibility="collapsed",
                    key=f"price_{b.id}",
                )
            with cols[2]:
                default_cur = b.price_currency if b.price_currency in currency_options else "INR"
                currency_inputs[b.id] = st.selectbox(
                    f"Currency — {b.name}",
                    currency_options,
                    index=currency_options.index(default_cur),
                    label_visibility="collapsed",
                    key=f"cur_{b.id}",
                )

        submitted = st.form_submit_button("💾 Save Prices & Compute L1/L2/L3 Ranking", type="primary", use_container_width=True)

    if submitted:
        saved_any = False
        for b in qualified:
            raw_price = price_inputs[b.id]
            cur = currency_inputs[b.id]
            price_to_save = raw_price if raw_price > 0 else None
            save_price_for_bidder(db, b.id, price_to_save, cur)
            saved_any = True

        if saved_any:
            st.success("✅ Prices saved. Computing ranking…")
        st.rerun()

    # ── Ranking Table ────────────────────────────────────────────────────────
    ranking = compute_commercial_ranking(db, tender.id)

    if not ranking:
        st.info("Enter prices above and click **Save Prices** to generate the L1/L2/L3 ranking.")
        return

    st.divider()
    st.subheader("🏆 Commercial Ranking — L1 / L2 / L3")

    has_tie = any(r["tie"] for r in ranking)
    if has_tie:
        st.warning(
            "⚠️ **Tie detected:** Two or more bidders have quoted the same price. "
            "Both receive the same L-rank. The Procurement Committee must resolve "
            "this tie manually (e.g., re-bidding, negotiation, or lot allocation).",
            icon="⚠️",
        )

    # Build display DataFrame
    rows = []
    for r in ranking:
        tie_flag = " ⚠️ TIE" if r["tie"] else ""
        rows.append(
            {
                "Rank": f"{r['label']}{tie_flag}",
                "Bidder Name": r["name"],
                f"Quoted Price ({r['currency']})" : f"{r['currency']} {r['quoted_price']:,.2f}",
                "% Above L1": f"{r['pct_above_l1']:.2f}%" if r["pct_above_l1"] > 0 else "—  (Lowest)",
                "Recommendation": (
                    "✅ RECOMMEND — Lowest Bidder" if r["rank"] == 1
                    else f"📋 Alternative — {r['pct_above_l1']:.2f}% above L1"
                ),
            }
        )

    df = pd.DataFrame(rows)

    # Style the dataframe
    def highlight_rank(row):
        if "L1" in str(row["Rank"]):
            return ["background-color: #e2f5e2; font-weight:bold"] * len(row)
        elif "L2" in str(row["Rank"]):
            return ["background-color: #fff9e6"] * len(row)
        else:
            return ["background-color: #fce8e6"] * len(row)

    st.dataframe(
        df.style.apply(highlight_rank, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # ── Bar Chart ────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📊 Price Comparison Chart")

    chart_df = pd.DataFrame(
        {
            "Bidder": [r["name"] for r in ranking],
            "Quoted Price": [r["quoted_price"] for r in ranking],
        }
    ).set_index("Bidder")

    st.bar_chart(chart_df, use_container_width=True, color="#0e2a47")

    # ── Summary callout ──────────────────────────────────────────────────────
    st.divider()
    l1 = next((r for r in ranking if r["rank"] == 1), None)
    if l1:
        st.success(
            f"**Recommended Bidder (L1): {l1['name']}**  \n"
            f"Quoted Price: **{l1['currency']} {l1['quoted_price']:,.2f}**  \n"
            f"Subject to final approval by the Procurement Committee.",
            icon="🏆",
        )

    st.caption(
        "📌 This ranking is auto-generated from the prices entered above. "
        "It will be included in the next MOM document generated from **Reports & Completion**."
    )
