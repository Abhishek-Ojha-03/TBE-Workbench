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
        
        # Version History Selector
        all_versions = (
            db.query(BaselineVersion)
            .filter(BaselineVersion.tender_id == tender.id)
            .order_by(BaselineVersion.version_number.desc())
            .all()
        )

        if not all_versions:
            st.warning("No baseline requirements found yet. Upload the tender specification first from the Specification screen.")
        else:
            c_v1, c_v2 = st.columns([2, 1])
            with c_v1:
                version_map = {v.version_number: v for v in all_versions}
                selected_v_num = st.selectbox(
                    "Select Baseline Version to View / Edit:",
                    options=list(version_map.keys()),
                    format_func=lambda num: f"Version {num} ({'Active / Latest' if num == latest_baseline.version_number else 'Archived History'}) — Approved: {version_map[num].approved_at.strftime('%d-%b-%Y %H:%M')}",
                    key="sel_baseline_version"
                )
                active_v_obj = version_map[selected_v_num]
            with c_v2:
                if selected_v_num == latest_baseline.version_number:
                    st.success(f"🟢 Active Baseline for Bidder Evaluation: **v{selected_v_num}**")
                else:
                    st.warning(f"🕒 Viewing Historical Version: **v{selected_v_num}** (Read/Branch)")

            # Fetch requirements ordered: QR first
            reqs = get_baseline_requirements(db, active_v_obj.id)
            
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

            st.caption("💡 **Tip:** Edit text in any cell, check/uncheck QR or Mark N/A, or click the **'+' button at the bottom of the table** to manually insert new requirements.")

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
                key=f"editor_baseline_v{active_v_obj.version_number}"
            )

            col1, col2 = st.columns([1, 3])
            with col1:
                save_label = f"💾 Save Edits as New Version (v{latest_baseline.version_number + 1})"
                if st.button(save_label, type="primary", use_container_width=True):
                    # Filter out empty rows added via '+'
                    new_records = [
                        r for r in edited_df.to_dict(orient="records")
                        if (r.get("text") and str(r.get("text")).strip())
                    ]
                    if not new_records:
                        st.error("Cannot save an empty baseline. Please enter requirement descriptions.")
                    else:
                        new_v = save_baseline_edits(db, tender.id, new_records)
                        st.success(f"Successfully saved Baseline Version {new_v.version_number}! Past version v{active_v_obj.version_number} is preserved in history.")
                        st.rerun()

            with col2:
                # Add Single Requirement Quick Form
                with st.expander("➕ Quick Add Single Requirement / Specification Clause", expanded=False):
                    with st.form("quick_add_req_form", clear_on_submit=True):
                        qa_col1, qa_col2 = st.columns([1, 3])
                        with qa_col1:
                            q_clause = st.text_input("Clause No.", placeholder="e.g. 6.1 or QR-4")
                            q_is_qr = st.checkbox("Qualification Req (QR)")
                        with qa_col2:
                            q_text = st.text_area("Requirement Text / Specification Description", placeholder="Enter full requirement clause...")
                        
                        if st.form_submit_button("➕ Append to Baseline"):
                            if not q_text.strip():
                                st.error("Requirement description cannot be empty.")
                            else:
                                current_records = edited_df.to_dict(orient="records")
                                current_records.append({
                                    "is_QR": q_is_qr,
                                    "clause": q_clause.strip(),
                                    "text": q_text.strip(),
                                    "not_applicable": False
                                })
                                new_v = save_baseline_edits(db, tender.id, current_records)
                                st.success(f"Added clause and created Baseline Version {new_v.version_number}!")
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

