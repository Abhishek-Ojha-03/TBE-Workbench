"""
UI Module for Screen 5: TBE Working Excel (Core Engine View).
Activities 6, 7, 8, 10, 12, 13, 14 in Workflow Document:
- Generate Working Excel
- Upload Bidder Documents all together
- Verify Bidder (AI extracts evidence & fills cells)
- Human Verification direct entry
- Re-verification of flagged rows
- Confirm Technical Status
- Download final TBE Excel
"""
import os
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session

from db.models import Tender, Bidder, Document, Finding, Requirement
from db.baseline_service import get_latest_baseline, get_baseline_requirements, get_bidders_for_tender
from reading.ingest import ingest_pdf_document
from ai.verifier import verify_all_requirements_for_bidder
from rules.rule_engine import update_bidder_qualification_status
from outputs.excel_generator import WorkingExcelGenerator


def render_working_excel_screen(db: Session, tender: Tender):
    st.markdown(f"## 📊 TBE Working Excel & Bidder Dossiers: `{tender.nit_no}`")

    latest_baseline = get_latest_baseline(db, tender.id)
    bidders = get_bidders_for_tender(db, tender.id)

    if not latest_baseline:
        st.warning("Please approve the requirements baseline first in Screen 2.")
        return

    if not bidders:
        st.warning("Please set up at least one bidder in Screen 4.")
        return

    # Section A: Generate Working Excel
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Working TBE Master Matrix")
        st.caption("Layout: Qualification Requirements (QR) first, blank separator row, then technical specs.")
    with col2:
        if st.button("📥 Generate & Download Working Excel", type="primary", use_container_width=True):
            excel_gen = WorkingExcelGenerator()
            out_path, _ = excel_gen.generate_working_excel(db, tender)
            with open(out_path, "rb") as f:
                st.download_button(
                    label="💾 Click to Download .xlsx",
                    data=f.read(),
                    file_name=os.path.basename(out_path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

    st.divider()

    # Section B: Upload Bidder Documents & Run AI Verification
    st.subheader("Bidder Document Ingestion & AI Verification")
    
    tabs = st.tabs([f"🏢 {b.name} ({b.final_status})" for b in bidders])

    for idx, bidder in enumerate(bidders):
        with tabs[idx]:
            c_up, c_run = st.columns([2, 1])
            with c_up:
                uploaded_files = st.file_uploader(
                    f"Upload all documents for {bidder.name} (PDFs)",
                    type=["pdf"],
                    accept_multiple_files=True,
                    key=f"bidder_docs_{bidder.id}"
                )
                if uploaded_files:
                    if st.button(f"📥 Ingest {len(uploaded_files)} Documents for {bidder.name}", key=f"btn_ingest_{bidder.id}"):
                        with st.spinner("Ingesting pages, indexing into FTS5, and caching scans..."):
                            for uf in uploaded_files:
                                ingest_pdf_document(
                                    db=db,
                                    file_bytes=uf.read(),
                                    file_name=uf.name,
                                    document_type="Bidder Submission",
                                    bidder_id=bidder.id
                                )
                            st.success(f"Ingested {len(uploaded_files)} documents successfully!")
                            st.rerun()

            with c_run:
                st.write("")
                st.write("")
                if st.button(f"🤖 Run AI Verification for {bidder.name}", type="primary", key=f"run_verify_{bidder.id}", use_container_width=True):
                    with st.spinner(f"AI evaluating {bidder.name} against baseline requirements with quote verification..."):
                        findings = verify_all_requirements_for_bidder(db, tender.id, bidder.id)
                        status = update_bidder_qualification_status(db, bidder.id)
                        st.success(f"Verification complete! Bidder Status: {status}")
                        st.rerun()

            # Display uploaded files
            docs = db.query(Document).filter(Document.bidder_id == bidder.id).all()
            if docs:
                st.write(f"**Submitted Files ({len(docs)}):**")
                cols = st.columns(3)
                for d_i, d in enumerate(docs):
                    cols[d_i % 3].caption(f"📄 {d.file_name} ({len(d.pages)} pages)")

            # Live Grid View of findings & Direct Human Verification (Activity 10 & 13)
            findings = db.query(Finding).filter(Finding.bidder_id == bidder.id).all()
            if findings:
                # Calculate Parameter Match Accuracy Metrics
                total_clauses = len(findings)
                complied_count = sum(1 for f in findings if (f.engineer_status == "Complied" or (not f.engineer_status and f.ai_status == "Complied")))
                not_complied_count = sum(1 for f in findings if (f.engineer_status == "Not Complied" or (not f.engineer_status and f.ai_status == "Not Complied")))
                review_count = total_clauses - complied_count - not_complied_count
                accuracy_pct = round((complied_count / total_clauses) * 100, 1) if total_clauses > 0 else 0.0

                # Parameter Accuracy Summary KPI Row
                m_c1, m_c2, m_c3, m_c4 = st.columns(4)
                m_c1.metric("🎯 Parameter Match Accuracy", f"{accuracy_pct}%", help="Calculated as (Complied Parameters / Total Evaluated Parameters) * 100")
                m_c2.metric("✅ Complied (100% Match)", f"{complied_count} / {total_clauses}")
                m_c3.metric("❌ Not Complied (0% Match)", f"{not_complied_count}")
                m_c4.metric("⚠️ Needs Review", f"{review_count}")

                st.write(f"**Evaluation & Accuracy Matrix for {bidder.name}:**")
                table_rows = []
                for f in findings:
                    effective_status = f.engineer_status or f.ai_status
                    # Parameter accuracy score
                    if effective_status == "Complied":
                        acc_score = "100%"
                    elif effective_status == "Not Complied":
                        acc_score = "0%"
                    else:
                        acc_score = "Pending Review"

                    # Offered value / citation if available
                    offered_text = ""
                    if f.evidences:
                        ev = f.evidences[0]
                        p_no = ev.page.page_number if ev.page else "?"
                        doc_name = ev.page.document.file_name if (ev.page and ev.page.document) else "Doc"
                        offered_text = f'"{ev.quoted_text[:50]}..." [{doc_name} p.{p_no}]' if ev.quoted_text else ""

                    table_rows.append({
                        "Clause": f.requirement.clause or "-",
                        "Category": "QR" if f.requirement.is_QR else "Technical",
                        "Specification Requirement": f.requirement.text[:65] + "...",
                        "Bidder Offered Quote": offered_text or "(No quote found)",
                        "Status": effective_status,
                        "Parameter Accuracy": acc_score,
                        "Remarks": f.remark or ""
                    })
                df_matrix = pd.DataFrame(table_rows)

                def highlight_status(val):
                    if val == "Complied":
                        return "background-color: #d4edda; color: #155724; font-weight: bold;"
                    elif val == "Not Complied":
                        return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
                    elif "Review" in str(val):
                        return "background-color: #fff3cd; color: #856404; font-weight: bold;"
                    return ""

                def highlight_acc(val):
                    if val == "100%":
                        return "background-color: #e8f5e9; color: #2e7d32; font-weight: bold;"
                    elif val == "0%":
                        return "background-color: #ffebee; color: #c62828; font-weight: bold;"
                    elif "Pending" in str(val):
                        return "background-color: #fffde7; color: #f57f17; font-weight: bold;"
                    return ""

                styled_df = df_matrix.style.map(highlight_status, subset=["Status"]).map(highlight_acc, subset=["Parameter Accuracy"])
                st.dataframe(styled_df, use_container_width=True)

                # Direct Human Verification & Manual Cell Editing (Activity 10 & 13)
                with st.expander("✍️ Direct Engineer Human Verification (Quick Cell Update)", expanded=False):
                    c_sel, c_stat, c_btn = st.columns([2, 1, 1])
                    with c_sel:
                        f_options = {f.id: f"Clause {f.requirement.clause or '-'}: {f.requirement.text[:55]}... [AI: {f.ai_status}]" for f in findings}
                        selected_f_id = st.selectbox("Select Clause to verify/update:", options=list(f_options.keys()), format_func=lambda x: f_options[x], key=f"sel_dir_{bidder.id}")
                    with c_stat:
                        new_dir_status = st.selectbox("Engineer Status:", ["Complied", "Not Complied", "Needs Human Review"], key=f"stat_dir_{bidder.id}")
                    with c_btn:
                        st.write("")
                        st.write("")
                        if st.button("💾 Save Cell Status", key=f"btn_save_dir_{bidder.id}", use_container_width=True):
                            from db.audit_service import confirm_finding, override_finding
                            f_obj = db.query(Finding).filter(Finding.id == selected_f_id).first()
                            if new_dir_status == f_obj.ai_status:
                                confirm_finding(db, f_obj.id, who="Lead Engineer (Direct)")
                            else:
                                override_finding(db, f_obj.id, new_status=new_dir_status, reason="Direct engineer verification entered in TBE cell", who="Lead Engineer (Direct)")
                            update_bidder_qualification_status(db, bidder.id)
                            st.success(f"Updated status for Clause {f_obj.requirement.clause} to {new_dir_status}!")
                            st.rerun()

