"""
UI Module: Tender Archive (read-only summary for completed tenders).

Reached only via the Home screen's Completed Tenders tab -> "View Archive"
button. Deliberately does NOT appear in the normal workflow sidebar radio
(Specification / Working Excel / etc.) since those steps don't apply to a
tender that's already done.

Shows, in one place:
- Original specification PDF (download)
- Bidder summary table: status, quoted price, commercial rank
- Per-bidder "what they offered" (findings + evidence), with CSV download
- Per-bidder original submitted documents (download)
- Generated deliverables: Working Excel / MOM / TER (generate + download)
"""
import os
import io
import csv
import streamlit as st
from sqlalchemy.orm import Session

from db.models import Tender, Bidder, Document, Finding, Requirement, Evidence
from db.baseline_service import get_latest_baseline, get_baseline_requirements
from db.commercial_service import get_commercial_ranking
from outputs.excel_generator import WorkingExcelGenerator
from outputs.docx_generator import generate_tbe_mom, generate_tbe_report


def _status_badge(status: str) -> str:
    s = (status or "Pending").strip()
    if s == "Qualified":
        return "🟢 Qualified"
    if s == "Not Qualified":
        return "🔴 Not Qualified"
    return "🟡 Pending"


def render_archive_screen(db: Session, tender: Tender):
    st.markdown(f"## 📚 Tender Archive: `{tender.nit_no}` *(Completed, Read-Only)*")
    st.caption(f"**Description:** {tender.description}  |  **Created:** {tender.created_at.strftime('%d-%b-%Y %H:%M')}")
    st.info(
        "This is a read-only archive of a completed tender. Use it to find the original "
        "specification and exactly what each bidder offered, if a similar tender comes up again."
    )

    bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all()
    latest_baseline = get_latest_baseline(db, tender.id)
    requirements = get_baseline_requirements(db, latest_baseline.id) if latest_baseline else []
    req_map = {r.id: r for r in requirements}

    st.divider()

    # ── Section: Original Specification ────────────────────────────────────
    st.subheader("📄 Original Specification")
    spec_docs = (
        db.query(Document)
        .filter(Document.tender_id == tender.id, Document.bidder_id.is_(None))
        .all()
    )
    if not spec_docs:
        st.caption("No specification document found for this tender.")
    else:
        for d in spec_docs:
            if d.file_path and os.path.exists(d.file_path):
                with open(d.file_path, "rb") as f:
                    st.download_button(
                        label=f"💾 Download {d.file_name}",
                        data=f.read(),
                        file_name=d.file_name,
                        mime="application/pdf",
                        key=f"archive_spec_dl_{d.id}"
                    )
            else:
                st.caption(f"⚠️ {d.file_name} — original file no longer on disk.")

    st.divider()

    # ── Section: Bidder Summary Table ──────────────────────────────────────
    st.subheader("🏢 Bidder Summary — Status, Price & Rank")
    if not bidders:
        st.caption("No bidders were registered for this tender.")
    else:
        ranking = get_commercial_ranking(db, tender.id)
        rank_by_bidder = {r["bidder_id"]: r for r in ranking}

        import pandas as pd
        rows = []
        for b in bidders:
            rank_info = rank_by_bidder.get(b.id)
            if b.quoted_price is not None:
                price_display = f"{b.price_currency or 'INR'} {b.quoted_price:,.2f}"
            else:
                price_display = "—"
            rank_label = rank_info["label"] if rank_info else "—"
            rows.append({
                "Bidder": b.name,
                "Final Status": _status_badge(b.final_status),
                "Quoted Price": price_display,
                "Commercial Rank": rank_label,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.divider()

    # ── Section: Per-Bidder Detail (what they offered + their documents) ──
    st.subheader("📋 What Each Bidder Offered")
    for b in bidders:
        with st.expander(f"{_status_badge(b.final_status)} — {b.name}", expanded=False):
            findings = (
                db.query(Finding)
                .filter(Finding.bidder_id == b.id)
                .all()
            )

            detail_rows = []
            for f in findings:
                req = req_map.get(f.requirement_id)
                evidence = db.query(Evidence).filter(Evidence.finding_id == f.id).first()
                detail_rows.append({
                    "Clause": req.clause if req else "—",
                    "Requirement": req.text if req else "—",
                    "Status": f.engineer_status or f.ai_status or "—",
                    "Bidder Offered (Quote)": evidence.quoted_text if evidence else "—",
                    "Remark": f.remark or "",
                })

            if detail_rows:
                import pandas as pd
                detail_df = pd.DataFrame(detail_rows)
                st.dataframe(detail_df, use_container_width=True)

                csv_buf = io.StringIO()
                writer = csv.DictWriter(csv_buf, fieldnames=list(detail_rows[0].keys()))
                writer.writeheader()
                writer.writerows(detail_rows)
                st.download_button(
                    label=f"💾 Download {b.name}'s Findings (CSV)",
                    data=csv_buf.getvalue(),
                    file_name=f"{tender.nit_no}_{b.name}_findings.csv".replace(" ", "_"),
                    mime="text/csv",
                    key=f"archive_findings_csv_{b.id}"
                )
            else:
                st.caption("No findings recorded for this bidder.")

            # Original submitted documents
            st.markdown("**Original Submitted Documents:**")
            bidder_docs = db.query(Document).filter(Document.bidder_id == b.id).all()
            if not bidder_docs:
                st.caption("No documents on file for this bidder.")
            else:
                for d in bidder_docs:
                    if d.file_path and os.path.exists(d.file_path):
                        with open(d.file_path, "rb") as f:
                            st.download_button(
                                label=f"💾 {d.file_name} ({d.document_type or 'Document'})",
                                data=f.read(),
                                file_name=d.file_name,
                                mime="application/pdf",
                                key=f"archive_bidder_doc_dl_{d.id}"
                            )
                    else:
                        st.caption(f"⚠️ {d.file_name} — original file no longer on disk.")

    st.divider()

    # ── Section: Generated Deliverables ────────────────────────────────────
    st.subheader("📦 Generated Deliverables")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📊 Generate & Download Working Excel", use_container_width=True, key="archive_gen_excel"):
            excel_gen = WorkingExcelGenerator()
            out_path, _ = excel_gen.generate_working_excel(db, tender)
            with open(out_path, "rb") as f:
                st.download_button(
                    label="💾 Click to Download .xlsx",
                    data=f.read(),
                    file_name=os.path.basename(out_path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key="archive_excel_dl"
                )

    with col2:
        if st.button("📄 Generate & Download MOM", use_container_width=True, key="archive_gen_mom"):
            with st.spinner("Generating MOM document..."):
                # No venue/attendees override here — uses the function's sensible
                # defaults, since this is a re-generation for the archive, not a
                # fresh meeting being scheduled.
                mom_file = generate_tbe_mom(db, tender)
                with open(mom_file, "rb") as f:
                    st.download_button(
                        label="💾 Click to Download MOM (.docx)",
                        data=f.read(),
                        file_name=os.path.basename(mom_file),
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                        key="archive_mom_dl"
                    )

    with col3:
        if st.button("📑 Generate & Download TER", use_container_width=True, key="archive_gen_ter"):
            with st.spinner("Generating TER report..."):
                ter_file = generate_tbe_report(db, tender)
                with open(ter_file, "rb") as f:
                    st.download_button(
                        label="💾 Click to Download TER (.docx)",
                        data=f.read(),
                        file_name=os.path.basename(ter_file),
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                        key="archive_ter_dl"
                    )
