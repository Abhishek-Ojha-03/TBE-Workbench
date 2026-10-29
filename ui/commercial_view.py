"""
Commercial Evaluation Screen — Part 2 (Price Bid Opening)
=========================================================
Two-Envelope Rule:
  • Only technically QUALIFIED bidders appear here.
  • AI automatically extracts quoted price from uploaded documents.
  • If price is not mentioned, it clearly displays "Price Not Mentioned".
  • L1 = lowest price, L2 = second lowest, …
  • No graph, only clean professional ranking table.
"""
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session

from db.models import Tender, Bidder
from db.commercial_service import (
    get_qualified_bidders,
    extract_bidder_price_with_ai,
    save_price_for_bidder,
    compute_commercial_ranking,
)


def render_commercial_screen(db: Session, tender: Tender):
    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="background:#0e2a47;padding:16px 20px;border-radius:8px;color:#fff;margin-bottom:20px;">
            <h2 style="margin:0;font-size:22px;">💰 Commercial Evaluation — Part 2 (Price Bid Opening)</h2>
            <p style="margin:4px 0 0;color:#a0aec0;font-size:13px;">
                Two-Envelope System · AI Auto-Fetched Quotations · L1/L2/L3 Ranking
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        "📋 **Two-Envelope Rule:** Commercial price evaluation opens **only for technically qualified bidders**. "
        "AI scans bidder documents for commercial price bids and computes the official L1/L2/L3 ranking.",
        icon="ℹ️",
    )

    # ── Qualified Bidders Check ──────────────────────────────────────────────
    qualified = get_qualified_bidders(db, tender.id)
    all_bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all()
    unqualified = [b for b in all_bidders if b.final_status != "Qualified"]

    if not qualified:
        st.warning(
            "⚠️ No bidders have been marked **Qualified** yet. "
            "Complete the Technical Evaluation and set Final Status to **Qualified** "
            "in the Reports & Completion screen before opening commercial evaluation.",
            icon="⚠️",
        )
        if unqualified:
            st.caption(
                f"Bidders currently in the pool: "
                + ", ".join(f"**{b.name}** ({b.final_status})" for b in all_bidders)
            )
        return

    st.success(
        f"✅ **{len(qualified)}** technically qualified bidder(s) are eligible for commercial evaluation. "
        + (f"⛔ {len(unqualified)} unqualified bidder(s) excluded." if unqualified else ""),
        icon="✅",
    )

    # ── Action Bar: AI Price Extraction ──────────────────────────────────────
    col_act1, col_act2 = st.columns([2, 1])
    with col_act1:
        st.markdown("### 🤖 AI Commercial Price Fetching")
        st.caption("AI analyzes bidder commercial submissions, quotations, and schedules to retrieve quoted prices.")
    with col_act2:
        st.write("")
        if st.button("⚡ Fetch Prices with AI", type="primary", use_container_width=True):
            with st.spinner("AI is scanning qualified bidder documents for quotation prices..."):
                for b in qualified:
                    price, currency, reason = extract_bidder_price_with_ai(db, b)
                    save_price_for_bidder(db, b.id, price, currency)
                st.success("✅ AI price scanning complete!")
                st.rerun()

    st.divider()

    # ── Ranking Table ────────────────────────────────────────────────────────
    ranking = compute_commercial_ranking(db, tender.id)

    if not ranking:
        st.info("No qualified bidders found.")
        return

    st.subheader("🏆 Commercial Evaluation & Ranking Table")

    has_tie = any(r.get("tie") for r in ranking if r.get("rank"))
    if has_tie:
        st.warning(
            "⚠️ **Tie detected:** Two or more qualified bidders have quoted the exact same price. "
            "Both receive the same L-rank. The Procurement Committee must resolve "
            "this tie manually per BSES procurement policy.",
            icon="⚠️",
        )

    # Build display rows
    rows = []
    for r in ranking:
        tie_flag = " ⚠️ TIE" if r.get("tie") else ""
        rank_str = f"{r['label']}{tie_flag}" if r.get("rank") else "—"

        if r.get("quoted_price") is not None and r["quoted_price"] > 0:
            price_display = f"{r['currency']} {r['quoted_price']:,.2f}"
            pct_display = f"{r['pct_above_l1']:.2f}%" if r["pct_above_l1"] > 0 else "0.00% (Lowest)"
            rec_display = "✅ RECOMMEND (L1 Lowest Bidder)" if r["rank"] == 1 else f"Alternative (L{r['rank']})"
        else:
            price_display = "Price Not Mentioned"
            pct_display = "—"
            rec_display = "⚠️ Price Not Mentioned in Documents"

        rows.append(
            {
                "Rank": rank_str,
                "Bidder Name": r["name"],
                "Quoted Price": price_display,
                "% Above L1": pct_display,
                "Recommendation / Status": rec_display,
            }
        )

    df = pd.DataFrame(rows)

    def highlight_rank(row):
        rank_val = str(row["Rank"])
        price_val = str(row["Quoted Price"])
        if "Price Not Mentioned" in price_val:
            return ["background-color: #fff2cc; color: #7f6000;"] * len(row)
        elif "L1" in rank_val:
            return ["background-color: #e2f5e2; font-weight: bold; color: #1e4620;"] * len(row)
        elif "L2" in rank_val:
            return ["background-color: #f0f7ff; color: #1a365d;"] * len(row)
        else:
            return ["background-color: #fdf2f2; color: #742a2a;"] * len(row)

    st.dataframe(
        df.style.apply(highlight_rank, axis=1),
        use_container_width=True,
        hide_index=True,
    )

    # ── Summary Callout ──────────────────────────────────────────────────────
    st.divider()
    l1_entry = next((r for r in ranking if r.get("rank") == 1), None)
    unpriced_count = sum(1 for r in ranking if r.get("quoted_price") is None)

    if l1_entry:
        st.success(
            f"**Recommended L1 Bidder: {l1_entry['name']}**  \n"
            f"Quoted Price: **{l1_entry['currency']} {l1_entry['quoted_price']:,.2f}**  \n"
            f"Evaluated as lowest qualified commercial offer for Committee approval.",
            icon="🏆",
        )
    elif unpriced_count == len(ranking):
        st.warning(
            "⚠️ All qualified bidders currently show **'Price Not Mentioned'**. "
            "Click **'⚡ Fetch Prices with AI'** above to extract quotations from bidder documents, "
            "or ensure price schedule files have been uploaded for these bidders.",
            icon="ℹ️",
        )

    st.caption(
        "📌 Only the commercial table is included in official evaluation proceedings. "
        "The ranking will automatically be reflected in Section 5 of the generated MOM document."
    )
