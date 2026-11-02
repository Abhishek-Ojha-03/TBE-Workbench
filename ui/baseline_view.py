"""
UI Module for Step 5: Engineer edits and approves the baseline.
Screens:
1. Requirements / Qualification (st.data_editor with QR listed first)
2. Mandatory Documents
3. Bidder Setup
"""
import os
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
                    "page_number": getattr(r, "page_number", 1) or 1,
                    "text": r.text,
                    "not_applicable": r.not_applicable
                })
            
            df = pd.DataFrame(df_data)

            st.caption("💡 **Tip:** Edit text or page number in any cell, check/uncheck QR or Mark N/A, or click the **'+' button at the bottom of the table** to manually insert new requirements.")

            # Editable grid using Streamlit data_editor
            edited_df = st.data_editor(
                df,
                column_config={
                    "is_QR": st.column_config.CheckboxColumn("Qualification Req (QR)", help="Must appear first in TBE grid"),
                    "clause": st.column_config.TextColumn("Clause / Section", width="small"),
                    "page_number": st.column_config.NumberColumn("Spec Page No.", help="Page in tender specification document where this clause appears", width="small", min_value=1, format="%d"),
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
                        qa_col1, qa_col2, qa_col3 = st.columns([1, 1, 3])
                        with qa_col1:
                            q_clause = st.text_input("Clause No.", placeholder="e.g. 6.1 or QR-4")
                            q_is_qr = st.checkbox("Qualification Req (QR)")
                        with qa_col2:
                            q_page = st.number_input("Spec Page No.", min_value=1, value=1, step=1)
                        with qa_col3:
                            q_text = st.text_area("Requirement Text / Specification Description", placeholder="Enter full requirement clause...")
                        
                        if st.form_submit_button("➕ Append to Baseline"):
                            if not q_text.strip():
                                st.error("Requirement description cannot be empty.")
                            else:
                                current_records = edited_df.to_dict(orient="records")
                                current_records.append({
                                    "is_QR": q_is_qr,
                                    "clause": q_clause.strip(),
                                    "page_number": int(q_page),
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

        # Bulk add bidders from a ZIP (folder names become bidder names — same
        # ZIP is reused later in TBE Working Excel to ingest documents, so the
        # bidder names and the document folders always match exactly, by
        # construction, with no separate name-reconciliation step needed.
        with st.expander("📦 Add Bidders from ZIP (folder names become bidder names)", expanded=False):
            st.caption(
                "Upload a ZIP with one sub-folder per bidder (e.g. `siemens/`, `abb/`). "
                "Each top-level folder becomes a bidder here, and the same ZIP is reused "
                "in the TBE Working Excel screen to ingest documents — no re-upload, "
                "no name-matching needed, since the bidder names come directly from "
                "these same folder names."
            )
            setup_zip_file = st.file_uploader(
                "Upload ZIP of bidder folders",
                type=["zip"],
                key="bidder_setup_zip_uploader"
            )
            if setup_zip_file and st.button(
                "➕ Extract Bidder Names from ZIP & Save for Ingestion",
                key="btn_bidder_setup_zip"
            ):
                import zipfile as _zipfile
                import io as _io

                zip_bytes = setup_zip_file.read()
                try:
                    zf = _zipfile.ZipFile(_io.BytesIO(zip_bytes))
                except Exception as ze:
                    st.error(f"Could not open ZIP: {ze}")
                    st.stop()

                folder_names = set()
                for name in zf.namelist():
                    parts = [p for p in name.replace("\\", "/").split("/") if p]
                    if len(parts) >= 2 and parts[-1].lower().endswith(".pdf"):
                        folder_names.add(parts[-2])
                zf.close()

                if not folder_names:
                    st.error("No PDF files found inside sub-folders in the ZIP.")
                else:
                    added, skipped = [], []
                    for folder_name in sorted(folder_names):
                        try:
                            add_bidder(db, tender.id, folder_name)
                            added.append(folder_name)
                        except ValueError:
                            skipped.append(folder_name)

                    # Save the ZIP to disk so Working Excel can reuse it directly
                    zip_dir = os.path.join("data", "bidder_zips")
                    os.makedirs(zip_dir, exist_ok=True)
                    zip_save_path = os.path.join(zip_dir, f"tender_{tender.id}_bidders.zip")
                    with open(zip_save_path, "wb") as f:
                        f.write(zip_bytes)

                    msg = f"✅ Added {len(added)} bidder(s): {', '.join(added) if added else '—'}."
                    if skipped:
                        msg += f" Skipped {len(skipped)} already registered: {', '.join(skipped)}."
                    st.success(msg)
                    st.info(
                        "This ZIP is saved — go to **TBE Working Excel** and click "
                        "**Extract & Ingest ALL Bidders from ZIP** to ingest documents "
                        "for these bidders without uploading again."
                    )
                    st.rerun()

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

