"""
TBE Workbench - Streamlit Application
Full Multi-Screen Workbench integrating all 8 Screens & 17 Activities from the Workflow Document.
"""
import streamlit as st
import pandas as pd
from datetime import datetime

from db.connection import SessionLocal, init_db
from db.repository import get_all_tenders, create_tender, get_tender_by_id
from ui.specification_view import render_specification_screen
from ui.baseline_view import render_baseline_screens
from ui.working_excel_view import render_working_excel_screen
from ui.review_view import render_review_screen
from ui.reports_view import render_reports_screen

# Page configuration
st.set_page_config(
    page_title="TBE Workbench - BSES Equipment Engineering",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Ensure database tables exist
init_db()


def get_db_session():
    return SessionLocal()


def render_home_page():
    # Top banner & branding
    st.markdown("""
        <div style="background-color: #0e2a47; padding: 18px 24px; border-radius: 8px; color: white; margin-bottom: 24px;">
            <h1 style="margin: 0; font-size: 26px; color: #ffffff;">⚡ TBE Workbench</h1>
            <p style="margin: 4px 0 0 0; color: #a0aec0; font-size: 14px;">
                AI-Assisted Technical Bid Evaluation | BSES Equipment Engineering
            </p>
        </div>
    """, unsafe_allow_html=True)

    db = get_db_session()
    try:
        # Create Tender Card
        with st.expander("➕ **Create New Tender (Phase-1)**", expanded=False):
            with st.form("create_tender_form", clear_on_submit=True):
                st.subheader("New Tender Details")
                col1, col2 = st.columns([2, 1])
                with col1:
                    description = st.text_input(
                        "Tender Description *",
                        placeholder="e.g. Supply of 11kV 630A Indoor VCB Switchgear Panels",
                        help="Full technical description of the equipment tender."
                    )
                with col2:
                    nit_no = st.text_input(
                        "NIT Number *",
                        placeholder="e.g. NIT-BSES-2026-PKG-01",
                        help="Notice Inviting Tender unique reference number."
                    )
                
                submitted = st.form_submit_button("Create Tender", type="primary", use_container_width=True)
                if submitted:
                    if not description.strip() or not nit_no.strip():
                        st.error("Both Tender Description and NIT Number are required.")
                    else:
                        try:
                            new_tender = create_tender(db, description=description, nit_no=nit_no)
                            st.success(f"Tender '{new_tender.nit_no}' created successfully and saved to database!")
                            st.rerun()
                        except ValueError as err:
                            st.error(str(err))

        st.divider()

        # Query tenders fresh from SQLite
        open_tenders = get_all_tenders(db, status="open")
        completed_tenders = get_all_tenders(db, status="completed")

        tab_open, tab_completed = st.tabs([
            f"📂 Open Tenders ({len(open_tenders)})",
            f"✅ Completed Tenders ({len(completed_tenders)})"
        ])

        with tab_open:
            if not open_tenders:
                st.info("No active open tenders found. Click **'+ Create New Tender'** above to begin.")
            else:
                for tender in open_tenders:
                    with st.container():
                        col_info, col_bidders, col_action = st.columns([3, 1, 1])
                        with col_info:
                            st.markdown(f"### {tender.description}")
                            st.caption(f"**NIT No:** `{tender.nit_no}` | **Created:** {tender.created_at.strftime('%d-%b-%Y %H:%M')}")
                        with col_bidders:
                            st.metric(label="Bidders", value=len(tender.bidders))
                        with col_action:
                            st.write("")
                            if st.button("Open Tender ➔", key=f"open_{tender.id}", use_container_width=True):
                                st.session_state["active_tender_id"] = tender.id
                                st.session_state["current_step"] = "Specification"
                                st.rerun()
                        st.markdown("---")

        with tab_completed:
            if not completed_tenders:
                st.info("No completed tenders yet.")
            else:
                for tender in completed_tenders:
                    with st.container():
                        col_info, col_bidders, col_action = st.columns([3, 1, 1])
                        with col_info:
                            st.markdown(f"### {tender.description} *(Completed)*")
                            st.caption(f"**NIT No:** `{tender.nit_no}` | **Created:** {tender.created_at.strftime('%d-%b-%Y %H:%M')}")
                        with col_bidders:
                            st.metric(label="Bidders", value=len(tender.bidders))
                        with col_action:
                            st.write("")
                            if st.button("View Archive 👁️", key=f"view_{tender.id}", use_container_width=True):
                                st.session_state["active_tender_id"] = tender.id
                                st.session_state["current_step"] = "Reports & Completion"
                                st.rerun()
                        st.markdown("---")

    finally:
        db.close()


def main():
    active_tender_id = st.session_state.get("active_tender_id")
    
    with st.sidebar:
        st.header("⚡ TBE Navigation")
        if active_tender_id:
            db = get_db_session()
            active_tender = get_tender_by_id(db, active_tender_id)
            db.close()
            
            if active_tender:
                st.success(f"**Tender:** `{active_tender.nit_no}`")
                st.caption(active_tender.description)
                if st.button("⬅️ Switch Tender", use_container_width=True):
                    del st.session_state["active_tender_id"]
                    if "current_step" in st.session_state:
                        del st.session_state["current_step"]
                    st.rerun()
                st.divider()

                menu_options = [
                    "Specification",
                    "Requirements & Setup",
                    "TBE Working Excel",
                    "Verification Results",
                    "Reports & Completion"
                ]

                default_idx = 0
                if "current_step" in st.session_state and st.session_state["current_step"] in menu_options:
                    default_idx = menu_options.index(st.session_state["current_step"])

                selected_screen = st.radio(
                    "Select Workflow Screen:",
                    menu_options,
                    index=default_idx
                )
                st.session_state["current_step"] = selected_screen
        else:
            st.info("Select or create a tender to access the evaluation steps.")

    # Main Body Router
    if not active_tender_id:
        render_home_page()
    else:
        db = get_db_session()
        tender = get_tender_by_id(db, active_tender_id)
        if not tender:
            st.error("Tender not found.")
            st.session_state.clear()
            st.rerun()

        screen = st.session_state.get("current_step", "Specification")
        try:
            if screen == "Specification":
                render_specification_screen(db, tender)
            elif screen == "Requirements & Setup":
                render_baseline_screens(db, tender)
            elif screen == "TBE Working Excel":
                render_working_excel_screen(db, tender)
            elif screen == "Verification Results":
                render_review_screen(db, tender)
            elif screen == "Reports & Completion":
                render_reports_screen(db, tender)
        finally:
            db.close()


if __name__ == "__main__":
    main()

