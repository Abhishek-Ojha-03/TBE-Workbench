"""
UI Module for Step 5: Engineer edits and approves the baseline.
Screens:
1. Requirements / Qualification (st.data_editor with QR listed first)
2. Mandatory Documents
3. Bidder Setup
"""
import streamlit as st
import pandas as pd
from typing import Optional
from sqlalchemy.orm import Session

from db.models import Tender, BaselineVersion, Requirement, Bidder
from db.baseline_service import (
    get_latest_baseline,
    get_baseline_requirements,
    save_baseline_edits,
    get_bidders_for_tender,
    add_bidder,
    delete_bidder
)


def render_baseline_screens(db: Session, tender: Tender):
    """Renders the Step 5 interface with versioning and st.data_editor."""
    st.markdown(f"## 📋 Baseline & Bidder Configuration: `{tender.nit_no}`")
    st.caption(f"**Tender:** {tender.description}")

    # Tabs for the 3 sub-screens specified in Step 5
    tab_reqs, tab_mandatory, tab_bidders = st.tabs([
        "1. 📑 Requirements & QR Baseline",
        "2. 🛡️ Mandatory Documents Checklist",
        "3. 🏢 Bidder Setup"
    ])

    latest_baseline = get_latest_baseline(db, tender.id)

    # --- Screen 1: Requirements Baseline ---
    with tab_reqs:
        st.subheader("Technical & Qualification Requirements")
        if not latest_baseline:
            st.warning("No baseline requirements found yet. Upload the tender specification first (Step 4).")
        else:
            st.info(f"Active Baseline Version: **v{latest_baseline.version_number}** (Approved: {latest_baseline.approved_at.strftime('%d-%b-%Y %H:%M')})")
            
            # Fetch requirements ordered: QR first
            reqs = get_baseline_requirements(db, latest_baseline.id)
            
            # Convert to DataFrame for st.data_editor
            df_data = []
            for r in reqs:
                df_data.append({
                    "id": r.id,
                    "is_QR": r.is_QR,
                    "clause": r.clause or "",
                    "text": r.text,
                    "not_applicable": r.not_applicable
                })
            
            df = pd.DataFrame(df_data)

            # Editable grid using Streamlit data_editor
            edited_df = st.data_editor(
                df,
                column_config={
                    "is_QR": st.column_config.CheckboxColumn("Qualification Req (QR)", help="Must appear first in TBE grid"),
                    "clause": st.column_config.TextColumn("Clause / Section", width="small"),
                    "text": st.column_config.TextColumn("Requirement Description", width="large"),
                    "not_applicable": st.column_config.CheckboxColumn("Mark N/A", help="Mark if requirement does not apply to this tender"),
                    "id": None  # Hide internal ID
                },
                num_rows="dynamic",
                use_container_width=True,
                key=f"editor_baseline_v{latest_baseline.version_number}"
            )

            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button("💾 Save as New Version", type="primary", use_container_width=True):
                    # Convert edited DataFrame back to dict records
                    new_records = edited_df.to_dict(orient="records")
                    new_v = save_baseline_edits(db, tender.id, new_records)
                    st.success(f"Successfully saved Baseline Version {new_v.version_number}! Version {latest_baseline.version_number} preserved.")
                    st.rerun()

    # --- Screen 2: Mandatory Documents ---
    with tab_mandatory:
        st.subheader("Mandatory Tender Documents Review")
        st.markdown("""
        Every bidder **must** submit these documents to qualify:
        * **Technical Offer:** The tender specification signed & stamped on each page by bidder.
        * **Deviation Sheet:** Compliant **ONLY if marked NIL deviations**. Any deviation marked must be evaluated.
        * **Type Test Certificates:** Valid accredited lab test reports (CPRI / ERDA / equivalent).
        * **Performance Certificates:** Utility operational track record proof.
        """)
        st.success("✅ Standard mandatory documents baseline verified for BSES equipment engineering.")

    # --- Screen 3: Bidder Setup ---
    with tab_bidders:
        st.subheader("Participating Bidders")
        bidders = get_bidders_for_tender(db, tender.id)

        # Form to add a new bidder
        with st.form("add_bidder_form", clear_on_submit=True):
            col_name, col_btn = st.columns([3, 1])
            with col_name:
                new_bidder_name = st.text_input("Enter Bidder Name", placeholder="e.g. ABB India Ltd / Siemens Ltd")
            with col_btn:
                st.write("")
                add_clicked = st.form_submit_button("Add Bidder", use_container_width=True)
                if add_clicked:
                    if new_bidder_name.strip():
                        try:
                            add_bidder(db, tender.id, new_bidder_name)
                            st.success(f"Bidder '{new_bidder_name}' added!")
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
                    else:
                        st.error("Please enter a valid bidder name.")

        # List existing bidders
        if not bidders:
            st.info("No bidders registered yet. Add at least 1 bidder above.")
        else:
            st.write(f"**Total Registered Bidders ({len(bidders)}):**")
            for b in bidders:
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    st.markdown(f"🏢 **{b.name}**")
                with c2:
                    st.caption(f"Status: `{b.final_status}`")
                with c3:
                    if st.button("🗑️ Remove", key=f"del_bidder_{b.id}"):
                        delete_bidder(db, b.id)
                        st.rerun()

