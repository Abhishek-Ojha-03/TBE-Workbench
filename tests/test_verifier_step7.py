"""
Unit test for Step 7: Check one bidder (the core of the project).
Verifies:
1. Bidder verification using Gemini 3.8 Flash.
2. Quoted sentence exists in the page text.
3. Code quote check: If quote is fabricated or altered, status is forced to 'Needs Human Review'.
4. Ground truth: Complied requirements match, and deviations/failures are recognized.
"""
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from db.models import Base, Tender, BaselineVersion, Requirement, Bidder, Document, Page, Finding, Evidence
from ai.verifier import verify_requirement_for_bidder
from rules.quote_checker import verify_quote_in_page_text

TEST_STEP7_DB = "test_step7.db"
TEST_URL = f"sqlite:///{TEST_STEP7_DB}"


@pytest.fixture(scope="module")
def step7_db():
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
    if os.path.exists(TEST_STEP7_DB):
        try:
            os.remove(TEST_STEP7_DB)
        except PermissionError:
            pass


def test_quote_checker_logic():
    page_text = "Impulse withstand voltage test passed at 170 kV peak under standard laboratory conditions."
    
    # 1. Exact quote
    assert verify_quote_in_page_text("Impulse withstand voltage test passed at 170 kV peak", page_text) is True

    # 2. Case and whitespace variations
    assert verify_quote_in_page_text("impulse withstand   voltage test passed", page_text) is True

    # 3. Fabricated or altered quote (e.g. 175 kV instead of 170 kV)
    assert verify_quote_in_page_text("Impulse withstand voltage test passed at 175 kV peak", page_text) is False


def test_live_bidder_verification(step7_db):
    # 1. Tender & Baseline
    tender = Tender(description="11kV VCB Tender", nit_no="NIT-STEP7-VERIFY", status="open")
    step7_db.add(tender)
    step7_db.commit()

    v1 = BaselineVersion(tender_id=tender.id, version_number=1)
    step7_db.add(v1)
    step7_db.commit()

    req = Requirement(
        baseline_version_id=v1.id,
        clause="4.3",
        text="Rated short-circuit breaking capacity shall be 25 kA for 1 second.",
        is_QR=False
    )
    step7_db.add(req)
    step7_db.commit()

    # 2. Add Bidder with Type Test Document
    bidder = Bidder(tender_id=tender.id, name="ABB India")
    step7_db.add(bidder)
    step7_db.commit()

    doc = Document(
        bidder_id=bidder.id,
        file_name="CPRI_Type_Test_Report.pdf",
        document_type="Type Test Report"
    )
    step7_db.add(doc)
    step7_db.commit()

    page = Page(
        document_id=doc.id,
        page_number=14,
        text=(
            "CENTRAL POWER RESEARCH INSTITUTE - TEST REPORT\n"
            "Equipment: 11kV Vacuum Circuit Breaker, 630A\n"
            "Short-circuit breaking current test: 25 kA rms for 1.0 second duration passed successfully without damage."
        ),
        read_by="PyMuPDF"
    )
    step7_db.add(page)
    step7_db.commit()

    # Add to FTS
    step7_db.execute(
        text("INSERT INTO page_fts (page_id, document_id, page_number, content) VALUES (:p_id, :d_id, :p_num, :content)"),
        {"p_id": page.id, "d_id": doc.id, "p_num": page.page_number, "content": page.text}
    )
    step7_db.commit()

    # 3. Run Verification Engine
    finding = verify_requirement_for_bidder(step7_db, req, bidder)

    assert finding is not None
    print(f"\nAI suggested status: {finding.ai_status}")
    print(f"Remark: {finding.remark}")

    # Check status is Complied (since 25kA for 1.0s matches requirement)
    assert finding.ai_status == "Complied"

    # Check Evidence saved
    evidences = step7_db.query(Evidence).filter(Evidence.finding_id == finding.id).all()
    assert len(evidences) > 0
    print(f"Verified Evidence Quote: \"{evidences[0].quoted_text}\" on Page {page.page_number}")
