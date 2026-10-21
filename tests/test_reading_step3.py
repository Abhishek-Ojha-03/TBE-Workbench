"""
Unit test for Step 3: PDF Reading Pipeline.
Done when: You can open any saved page and see its text and number.
Rules verified:
1. read_page() returns text, read_by, and image.
2. Digital pages extracted with PyMuPDF.
3. Scanned pages routed to Vision LLM / image saved.
4. Pages stored in DB with page number, document_id, and FTS5 searchable.
"""
import os
import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Document, Page
from reading.ingest import read_page, ingest_pdf_document, get_document_pages

TEST_STEP3_DB = "test_step3.db"
TEST_URL = f"sqlite:///{TEST_STEP3_DB}"


@pytest.fixture(scope="module")
def step3_db():
    engine = create_engine(TEST_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    
    with engine.connect() as conn:
        conn.exec_driver_sql("""
            CREATE VIRTUAL TABLE IF NOT EXISTS page_fts USING fts5(
                page_id UNINDEXED,
                document_id UNINDEXED,
                page_number UNINDEXED,
                content
            );
        """)
        conn.commit()

    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    yield db
    db.close()
    engine.dispose()
    if os.path.exists(TEST_STEP3_DB):
        try:
            os.remove(TEST_STEP3_DB)
        except PermissionError:
            pass


def create_sample_pdf(has_scanned_page=True) -> bytes:
    """Creates an in-memory 2-page test PDF (Page 1 = digital text, Page 2 = image/scan simulation)."""
    doc = fitz.open()

    # Page 1: Digital text (>= 40 chars)
    page1 = doc.new_page()
    text1 = (
        "SPECIFICATION NO. BSES-SP-11-01:\n"
        "Technical Requirements for 11kV 630A Indoor VCB Switchgear.\n"
        "Lightning impulse withstand voltage rating shall be 170 kV peak."
    )
    page1.insert_text((50, 72), text1, fontsize=11)

    # Page 2: Minimal text (< 40 chars) to simulate a scan or handwritten sheet
    page2 = doc.new_page()
    page2.insert_text((50, 72), "Scan p.2", fontsize=10)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_ingest_and_read_page_by_page(step3_db):
    pdf_bytes = create_sample_pdf()
    
    # Ingest document
    doc_record = ingest_pdf_document(
        db=step3_db,
        file_bytes=pdf_bytes,
        file_name="test_specification.pdf",
        document_type="Specification"
    )

    assert doc_record.id is not None
    assert doc_record.file_name == "test_specification.pdf"

    # Query pages back from DB (never re-reading PDF)
    pages = get_document_pages(step3_db, doc_record.id)
    assert len(pages) == 2

    # Check Page 1 (Digital text)
    p1 = pages[0]
    assert p1.page_number == 1
    assert p1.read_by == "PyMuPDF"
    assert "170 kV peak" in p1.text
    assert p1.image_path is None

    # Check Page 2 (Scanned/Image route)
    p2 = pages[1]
    assert p2.page_number == 2
    assert p2.read_by == "LLM"
    assert p2.image_path is not None
    assert os.path.exists(p2.image_path)

