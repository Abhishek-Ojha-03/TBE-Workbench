"""
UI Module for Step 9: Review Screen and Audit Trail.
Features:
- Lists each requirement with AI's result, evidence quote, cited page number.
- For scanned pages, displays original image side-by-side with text.
- Four interactive action buttons:
  [Confirm] | [Override] | [Request Clarification] | [Flag for Review]
- Enforces mandatory reason modal/text for Override.
- Displays the complete chronological Audit Trail.
"""
import os
import streamlit as st
from sqlalchemy.orm import Session
from PIL import Image

from db.models import Tender, Bidder, Finding, Requirement, Evidence, AuditLog, Page
from db.audit_service import (
    confirm_finding,
    override_finding,
    flag_for_review,
    get_audit_trail_for_finding
)


def render_review_screen(db: Session, tender: Tender):
    st.markdown(f"## 🔍 Verification Results & Audit Review: `{tender.nit_no}`")

    bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all()
    if not bidders:
        st.warning("No bidders found for this tender.")
        return

    # Select bidder to review
    bidder_names = [b.name for b in bidders]
    selected_name = st.selectbox("Select Bidder to Review:", bidder_names)
    selected_bidder = next(b for b in bidders if b.name == selected_name)

    st.info(f"**Bidder:** {selected_bidder.name} | **Current Qualification Status:** `{selected_bidder.final_status}`")

    findings = (
        db.query(Finding)
        .filter(Finding.bidder_id == selected_bidder.id)
        .all()
    )

    if not findings:
        st.info("No findings evaluated yet. Run Step 7 (Verify Bidder) first.")
        return

    # Render each requirement review card
    for f in findings:
        req = f.requirement
        evidences = f.evidences

        badge_color = "green" if f.ai_status == "Complied" else ("red" if f.ai_status == "Not Complied" else "orange")
        status_label = f.engineer_status if f.engineer_status else f"AI Suggested: {f.ai_status}"

        with st.expander(f"**Clause {req.clause or 'General'}**: {req.text[:70]}... — `[{status_label}]`", expanded=(f.engineer_status is None)):
            col_info, col_evidence = st.columns([1, 1])

            with col_info:
                st.markdown(f"**Requirement:** {req.text}")
                st.markdown(f"**AI Recommendation:** :{badge_color}[**{f.ai_status}**]")
                if f.remark:
                    st.caption(f"**Technical Note:** {f.remark}")

                if f.engineer_status:
                    st.success(f"**Confirmed Status by Engineer:** {f.engineer_status}")

            with col_evidence:
                if evidences:
                    ev = evidences[0]
                    page = ev.page
                    st.markdown(f"📄 **Cited Evidence (Page {page.page_number if page else 'N/A'}):**")
                    st.info(f'"{ev.quoted_text}"')

                    # Side-by-side image verification rule if read by Vision LLM
                    if page and page.read_by == "LLM" and page.image_path and os.path.exists(page.image_path):
                        st.caption("🔍 **Original Document Scan (Check numbers & units):**")
                        st.image(page.image_path, width=320)
                else:
                    st.warning("No verifiable quote found in submitted documents.")

            st.divider()

            # Actions row
            c1, c2, c3, c4 = st.columns([1, 1.5, 1.5, 1])
            with c1:
                if st.button("✅ Confirm", key=f"conf_{f.id}"):
                    confirm_finding(db, f.id, who="BSES Lead Engineer")
                    st.rerun()

            with c2:
                # Override input
                override_choice = st.selectbox(
                    "Override to:",
                    ["Complied", "Not Complied", "N/A"],
                    key=f"ov_choice_{f.id}"
                )
                override_reason = st.text_input(
                    "Reason for override (Mandatory) *",
                    placeholder="e.g. Deviation accepted as per Tech Spec addendum",
                    key=f"ov_reason_{f.id}"
                )
                if st.button("⚠️ Submit Override", key=f"ov_btn_{f.id}"):
                    if not override_reason.strip():
                        st.error("Technical reason is mandatory for override.")
                    else:
                        override_finding(db, f.id, override_choice, override_reason, who="BSES Lead Engineer")
                        st.success("Override saved.")
                        st.rerun()

            with c3:
                clar_reason = st.text_input("Clarification Note", placeholder="e.g. Request test certificate page 3", key=f"clar_{f.id}")
                if st.button("❓ Request Clarification", key=f"clar_btn_{f.id}"):
                    flag_for_review(db, f.id, reason=f"Clarification Needed: {clar_reason}", who="BSES Lead Engineer")
                    st.rerun()

            with c4:
                if st.button("🚩 Flag Review", key=f"flag_{f.id}"):
                    flag_for_review(db, f.id, reason="Marked for manual site inspection", who="BSES Lead Engineer")
                    st.rerun()

            # Audit Trail Display (Use clean container to avoid Streamlit nested expander restriction)
            audit_logs = get_audit_trail_for_finding(db, f.id)
            if audit_logs:
                st.markdown("**📜 Audit History:**")
                for log in audit_logs:
                    st.caption(f"🕒 `[{log.timestamp.strftime('%d-%b-%Y %H:%M:%S')}]` **{log.who}**: Changed {log.what_changed} from *'{log.old_value}'* ➔ *'{log.new_value}'*. Reason: *{log.reason}*")

