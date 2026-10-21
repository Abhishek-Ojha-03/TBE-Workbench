"""
UI Module for Screen 1: Specification Upload & AI Extraction.
Activity 2 in Workflow Document:
- AI reads the whole specification and identifies items, requirements,
  qualification criteria, type tests, standards, mandatory documents and evaluation conditions.
"""
import streamlit as st
from sqlalchemy.orm import Session

from db.models import Tender, Document, Page
from reading.ingest import ingest_pdf_document, get_document_pages
from ai.extractor import process_specification_document
from db.baseline_service import get_latest_baseline


def render_specification_screen(db: Session, tender: Tender):
    st.markdown(f"## 📄 Tender Specification: `{tender.nit_no}`")
    st.caption(f"**Tender Description:** {tender.description}")

    # Check if a specification is already uploaded
    spec_doc = (
        db.query(Document)
        .filter(Document.bidder_id == None, Document.document_type == "Specification")
        .first()
    )

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Upload Specification PDF")
        uploaded_file = st.file_uploader(
            "Select Tender Technical Specification (.pdf)",
            type=["pdf"],
            key=f"spec_upload_{tender.id}"
        )

        if uploaded_file is not None:
            if st.button("🚀 Process Specification with AI", type="primary"):
                with st.spinner("Reading pages, checking scans with Vision OCR, and extracting clauses via Gemini..."):
                    pdf_bytes = uploaded_file.read()
                    
                    # 1. Ingest PDF page-by-page
                    doc_record = ingest_pdf_document(
                        db=db,
                        file_bytes=pdf_bytes,
                        file_name=uploaded_file.name,
                        document_type="Specification",
                        bidder_id=None
                    )

                    # 2. Extract requirements & create Baseline Version 1
                    baseline = process_specification_document(
                        db=db,
                        tender_id=tender.id,
                        specification_document_id=doc_record.id
                    )

                    st.success(f"Specification processed! Baseline Version {baseline.version_number} created with {len(baseline.requirements)} requirements.")
                    st.rerun()

    with col2:
        st.subheader("Ingestion Status")
        if spec_doc:
            pages = get_document_pages(db, spec_doc.id)
            latest_b = get_latest_baseline(db, tender.id)
            st.success(f"✅ Specification Uploaded: **{spec_doc.file_name}**")
            st.metric("Total Pages Ingested", len(pages))
            if latest_b:
                st.metric("Requirements Extracted", len(latest_b.requirements))
                st.info("Proceed to **2. Requirements / Qualification** from the sidebar to review and approve the baseline.")
        else:
            st.info("No specification uploaded yet for this tender.")

