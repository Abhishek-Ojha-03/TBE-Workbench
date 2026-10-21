"""
UI Module for Screen 7 & 8: TBE MOM & TBE Report Exports.
Activities 15, 16, 17 in Workflow Document:
- Generate TBE MOM (.docx)
- Generate TBE Report (.docx)
- Complete Tender
"""
import os
import streamlit as st
from sqlalchemy.orm import Session

from db.models import Tender, Bidder
from outputs.docx_generator import generate_tbe_mom, generate_tbe_report
from db.repository import update_tender_status


def render_reports_screen(db: Session, tender: Tender):
    st.markdown(f"## 📝 Official Deliverables & Completion: `{tender.nit_no}`")
    st.caption(f"**Tender:** {tender.description}")

    bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Generate TBE MOM (.docx)")
        st.markdown("""
        Compiles the official **Minutes of Meeting** in BSES standard format:
        - Meeting committee members and venue
        - AI-synthesized executive proceeding summary
        - Technical qualification outcomes table
        - Signature blocks
        """)

        with st.expander("⚙️ Edit Committee Members & Venue", expanded=False):
            venue = st.text_input("Meeting Venue", value="Conference Room 2, Engineering Division, BSES Bhawan, Nehru Place, New Delhi", key="mom_venue")
            members_text = st.text_area(
                "Committee Members (one per line)",
                value="Sh. R.K. Sharma (Head - Equipment Engineering)\nSh. Amit Verma (Sr. Manager - Substation Design)\nEr. P. K. Singh (Dy. Manager - Technical Evaluation)",
                help="Enter real officer names and designations for the official minutes",
                key="mom_members"
            )

        if st.button("📄 Generate TBE MOM", type="primary", use_container_width=True):
            with st.spinner("Generating MOM document..."):
                attendees_list = [m.strip() for m in members_text.splitlines() if m.strip()]
                mom_file = generate_tbe_mom(db, tender, attendees=attendees_list, meeting_venue=venue)
                with open(mom_file, "rb") as f:
                    st.download_button(
                        label="💾 Download MOM (.docx)",
                        data=f.read(),
                        file_name=os.path.basename(mom_file),
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )

    with col2:
        st.subheader("Generate TBE Report (.docx)")
        st.markdown("""
        Compiles the full **Technical Evaluation Report (TER)**:
        - Cover page & index
        - Executive technical summary
        - Full comparison matrix (clauses, specified ratings vs bidder offerings)
        - Final qualification recommendation
        """)
        if st.button("📊 Generate TER Report", type="primary", use_container_width=True):
            with st.spinner("Generating TER report..."):
                ter_file = generate_tbe_report(db, tender)
                with open(ter_file, "rb") as f:
                    st.download_button(
                        label="💾 Download TER (.docx)",
                        data=f.read(),
                        file_name=os.path.basename(ter_file),
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )

    # Clarification Letters & Delta Re-Verification Section (Activities 11 & 12)
    st.divider()
    st.subheader("📬 Clarification Management & Delta Re-Verification")
    st.markdown("""
    When bidders have missing documents or unresolved queries, draft formal utility clarification letters, 
    upload their replies, and **re-verify ONLY the affected rows** without re-evaluating the whole tender.
    """)

    from ai.clarification_service import generate_clarification_letter, handle_clarification_response, recheck_flagged_findings
    from db.models import Finding

    bidder_options = {b.id: b.name for b in bidders}
    c_bid, c_act = st.columns([1, 2])
    with c_bid:
        selected_b_id = st.selectbox("Select Bidder for Clarification:", list(bidder_options.keys()), format_func=lambda x: bidder_options[x], key="clar_bidder_select")
        chosen_bidder = db.query(Bidder).filter(Bidder.id == selected_b_id).first()

    with c_act:
        flagged_items = (
            db.query(Finding)
            .filter(Finding.bidder_id == selected_b_id)
            .filter((Finding.ai_status == "Needs Human Review") | (Finding.engineer_status == "Needs Human Review") | (Finding.needs_recheck == True))
            .all()
        )
        st.write(f"**Flagged / Review Items for {chosen_bidder.name}:** `{len(flagged_items)} items`")

        if st.button("📝 Draft Official Clarification Letter via Gemini", key=f"btn_draft_{selected_b_id}"):
            if not flagged_items:
                st.info("No items currently flagged for review for this bidder.")
            else:
                with st.spinner("AI drafting formal BSES Clarification Letter..."):
                    letter = generate_clarification_letter(db, tender, chosen_bidder, flagged_items)
                    st.session_state[f"draft_letter_{selected_b_id}"] = letter

        if f"draft_letter_{selected_b_id}" in st.session_state:
            active_letter = st.session_state[f"draft_letter_{selected_b_id}"]
            
            # Sub-tabs for Editable Raw Text vs Clean Letter Preview
            tab_preview, tab_raw = st.tabs(["👁️ Formal Letter Preview (Clean)", "✏️ Edit Letter Content"])
            
            with tab_preview:
                st.markdown(
                    """
                    <div style="background-color: #ffffff; color: #1e293b; padding: 28px 36px; border-radius: 8px; border: 1px solid #cbd5e1; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6;">
                    """,
                    unsafe_allow_html=True
                )
                st.markdown(active_letter)
                st.markdown("</div>", unsafe_allow_html=True)
                
            with tab_raw:
                st.caption("You can edit the raw text or markdown formatting below if needed:")
                edited_letter = st.text_area(
                    "Clarification Letter Text",
                    value=active_letter,
                    height=280,
                    key=f"txt_letter_{selected_b_id}"
                )
                if edited_letter != active_letter:
                    st.session_state[f"draft_letter_{selected_b_id}"] = edited_letter

        with st.expander("📥 Upload Clarification Reply & Delta Re-Verify (Activity 12)", expanded=False):
            reply_file = st.file_uploader("Upload Bidder's Clarification Response PDF", type=["pdf"], key=f"reply_file_{selected_b_id}")
            if reply_file and flagged_items:
                if st.button("⚡ Run Delta Re-Verification on Affected Rows Only", key=f"btn_delta_{selected_b_id}"):
                    with st.spinner("Indexing response and re-verifying only affected rows..."):
                        affected_ids = [f.requirement_id for f in flagged_items]
                        handle_clarification_response(db, selected_b_id, reply_file.read(), reply_file.name, affected_ids)
                        rechecked = recheck_flagged_findings(db, selected_b_id)
                        st.success(f"Delta re-verification complete! Re-checked {len(rechecked)} affected clauses. Old audit trail preserved.")
                        st.rerun()

    st.divider()

    # Step 17: Complete Tender
    st.subheader("Mark Tender as Completed")
    if tender.status == "completed":
        st.success("✅ This tender is already marked as Completed. It is archived in read-only mode.")
    else:
        st.warning("Once marked Completed, the evaluation baseline is locked and archived to the Home Page.")
        if st.button("🔒 Complete & Archive Tender", type="secondary"):
            update_tender_status(db, tender.id, "completed")
            st.success("Tender marked as Completed! Returning to Home Page...")
            del st.session_state["active_tender_id"]
            st.rerun()

