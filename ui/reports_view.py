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
        - **AI-synthesized Technical Compliance Scoring Table** (per-bidder %)
        - **Strategic Negotiation & Discussion Talking Points** for Committee
        - Signature blocks
        """)

        # --- Compliance Scores & Visual Comparison ---
        with st.expander("📊 Preview: Compliance Scores & Risk Matrix", expanded=False):
            from db.baseline_service import get_latest_baseline, get_baseline_requirements
            from db.models import Finding, Requirement
            import pandas as pd

            latest_b = get_latest_baseline(db, tender.id)
            reqs = get_baseline_requirements(db, latest_b.id) if latest_b else []
            req_ids = [r.id for r in reqs]
            total_reqs = len(reqs)

            if not bidders or not reqs:
                st.info("Complete bidder verification first to see scoring.")
            else:
                score_rows = []
                bidder_summaries = []
                for b in bidders:
                    findings = (
                        db.query(Finding)
                        .filter(Finding.bidder_id == b.id, Finding.requirement_id.in_(req_ids))
                        .all()
                    )
                    complied = sum(
                        1 for f in findings
                        if (f.engineer_status or f.ai_status or "").lower() == "complied"
                    )
                    not_complied = sum(
                        1 for f in findings
                        if (f.engineer_status or f.ai_status or "").lower() == "not complied"
                    )
                    reviews = sum(
                        1 for f in findings
                        if "review" in (f.engineer_status or f.ai_status or "").lower()
                    )
                    score = round((complied / total_reqs * 100), 1) if total_reqs else 0.0
                    status_val = b.final_status or "Pending"
                    if status_val == "Qualified":
                        emoji = "🟢"
                    elif status_val == "Not Qualified":
                        emoji = "🔴"
                    else:
                        emoji = "🟡"
                    # Check Risk / Severity Index:
                    # High Risk (Disqualifying): Any QR clause failed, or Type Test failed
                    # Medium Risk: Technical parameter mismatch or >2 under review
                    # Low Risk: 100% compliant or only minor non-QR reviews
                    qr_ids = [r.id for r in reqs if r.is_QR]
                    qr_failures = sum(
                        1 for f in findings
                        if f.requirement_id in qr_ids and (f.engineer_status or f.ai_status or "").lower() == "not complied"
                    )
                    
                    if qr_failures > 0 or (status_val == "Not Qualified"):
                        risk_level = "🔴 High Risk"
                    elif not_complied > 0 or reviews > 2:
                        risk_level = "🟡 Medium Risk"
                    elif reviews > 0:
                        risk_level = "🟢 Low Risk"
                    else:
                        risk_level = "🟢 Clean"

                    score_rows.append({
                        "Bidder": b.name,
                        "Total Clauses": total_reqs,
                        "✅ Complied": complied,
                        "❌ Not Complied": not_complied,
                        "🔍 Under Review": reviews,
                        "Score (%)": f"{score}%",
                        "Risk / Severity": risk_level,
                        "Status": f"{emoji} {status_val}"
                    })

                    dev_clauses = []
                    req_map = {r.id: r for r in reqs}
                    for f in findings:
                        st_val = (f.engineer_status or f.ai_status or "").lower()
                        if st_val == "not complied" or "review" in st_val:
                            req_obj = req_map.get(f.requirement_id)
                            dev_clauses.append({
                                "clause": req_obj.clause if req_obj else "General",
                                "text": ((req_obj.text[:80] + "...") if req_obj else ""),
                                "issue": f.remark or f.ai_reason or "Pending review"
                            })
                    bidder_summaries.append({
                        "name": b.name,
                        "status": status_val,
                        "score": score,
                        "deviations": not_complied,
                        "reviews": reviews,
                        "key_issues": dev_clauses[:4]
                    })

                st.markdown("**📊 Compliance Score & Risk Summary:**")
                st.dataframe(pd.DataFrame(score_rows), use_container_width=True)

                # Visual Side-by-Side Comparison Chart
                st.markdown("**📈 Bidder Technical Compliance Comparison:**")
                chart_df = pd.DataFrame([
                    {"Bidder": r["Bidder"], "Compliance Score (%)": float(r["Score (%)"].replace("%", ""))}
                    for r in score_rows
                ]).set_index("Bidder")
                st.bar_chart(chart_df, color="#0E2A47")

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

        with st.expander("📥 Upload Clarification Reply & Delta Re-Verify (Activity 12)", expanded=True):
            reply_files = st.file_uploader(
                "Upload Bidder's Clarification Response PDF(s)",
                type=["pdf"],
                accept_multiple_files=True,
                key=f"reply_files_{selected_b_id}"
            )
            if reply_files:
                n_flagged = len(flagged_items)
                btn_label = (
                    f"⚡ Run Delta Re-Verification ({len(reply_files)} files, {n_flagged} flagged clauses)"
                    if n_flagged > 0
                    else f"⚡ Run Delta Re-Verification on All Clauses ({len(reply_files)} file(s))"
                )
                if st.button(btn_label, type="primary", key=f"btn_delta_{selected_b_id}"):
                    with st.spinner(f"Indexing {len(reply_files)} clarification document(s) and re-verifying affected clauses..."):
                        from rules.rule_engine import update_bidder_qualification_status
                        affected_ids = [f.requirement_id for f in flagged_items] if flagged_items else None
                        for rf in reply_files:
                            handle_clarification_response(db, selected_b_id, rf.read(), rf.name, affected_ids or [])
                        rechecked = recheck_flagged_findings(db, selected_b_id)
                        new_status = update_bidder_qualification_status(db, selected_b_id)
                        
                        st.session_state[f"last_rechecked_{selected_b_id}"] = {
                            "count": len(rechecked),
                            "status": new_status,
                            "clauses": [f.requirement.clause or 'General' for f in rechecked]
                        }
                        st.success(f"Delta re-verification complete! Re-checked {len(rechecked)} clauses. Updated Bidder Status: [{new_status}]")
                        st.rerun()

            # Display Post-Reverification Result Summary Card if re-verification was run
            last_recheck = st.session_state.get(f"last_rechecked_{selected_b_id}")
            if last_recheck:
                s_color = "green" if last_recheck["status"] == "Qualified" else ("red" if last_recheck["status"] == "Not Qualified" else "orange")
                st.markdown(
                    f"""
                    <div style="background-color: #f8fafc; border-left: 5px solid {s_color}; padding: 12px 16px; border-radius: 6px; margin-top: 10px;">
                        <h4 style="margin: 0; color: #0f172a;">🎯 Re-Verification Result for {chosen_bidder.name}</h4>
                        <p style="margin: 6px 0 0 0; font-size: 14px;">
                            <b>Updated Qualification Status:</b> <span style="font-weight: bold; color: {s_color};">{last_recheck['status']}</span><br/>
                            <b>Clauses Re-Checked:</b> {last_recheck['count']} (Clauses: {', '.join(last_recheck['clauses'])})<br/>
                            <i>Full audit history and revised quoted evidence preserved in Step 9 Review.</i>
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

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

