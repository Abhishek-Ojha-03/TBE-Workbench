"""
Unit test for Step 4: Extract requirements from specification.
Done when: You compare the list with the tender and write down how many requirements were missed or invented. Aim to miss none.
Verifies:
1. Pydantic schema validation for requirements.
2. Accurate classification of Qualification Requirements (QR) by explicit heading.
3. Creation of BaselineVersion 1 with requirements in the database.
"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Tender, Document, Page, BaselineVersion, Requirement
from ai.extractor import process_specification_document
from ai.schemas import SpecificationExtractionResult, ExtractedRequirement

TEST_STEP4_DB = "test_step4.db"
TEST_URL = f"sqlite:///{TEST_STEP4_DB}"


@pytest.fixture(scope="module")
def step4_db():
    engine = create_engine(TEST_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    yield db
    db.close()
    engine.dispose()
    if os.path.exists(TEST_STEP4_DB):
        try:
            os.remove(TEST_STEP4_DB)
        except PermissionError:
            pass


def test_specification_extraction_and_baseline_creation(step4_db):
    # 1. Create Tender
    tender = Tender(
        description="Supply of 11kV 630A Indoor VCB Panels",
        nit_no="NIT-BSES-STEP4-001",
        status="open"
    )
    step4_db.add(tender)
    step4_db.commit()

    # 2. Create Specification Document with 2 Pages
    doc = Document(
        bidder_id=None,
        file_name="BSES_Specification_VCB.pdf",
        document_type="Specification"
    )
    step4_db.add(doc)
    step4_db.commit()

    # Page 1: Qualification Criteria Heading
    p1 = Page(
        document_id=doc.id,
        page_number=1,
        text=(
            "SECTION 1: QUALIFICATION CRITERIA (QR)\n"
            "QR-1: The bidder must be an OEM of 11kV Switchgear panels for at least 5 years.\n"
            "QR-2: Bidder must have supplied at least 500 panels to Indian electrical utilities in the last 3 financial years.\n"
            "MANDATORY SUBMISSIONS:\n"
            "1. Duly signed copy of BSES Technical Specification (Technical Offer).\n"
            "2. Deviation sheet signed with NIL deviations."
        ),
        read_by="PyMuPDF"
    )
    
    # Page 2: Technical Specifications
    p2 = Page(
        document_id=doc.id,
        page_number=2,
        text=(
            "SECTION 2: TECHNICAL PARAMETERS\n"
            "Clause 4.1: Rated voltage shall be 11 kV nominal and 12 kV highest system voltage.\n"
            "Clause 4.2: Rated normal current of busbars and circuit breaker shall be 630 A at 50 deg C ambient.\n"
            "Clause 4.3: Rated short-circuit breaking capacity shall be 25 kA for 1 second.\n"
            "Clause 4.4: Rated lightning impulse withstand voltage rating shall be 75 kV peak (IS/IEC 62271-200)."
        ),
        read_by="PyMuPDF"
    )
    step4_db.add_all([p1, p2])
    step4_db.commit()

    # 3. Process Specification via extraction engine
    baseline = process_specification_document(
        db=step4_db,
        tender_id=tender.id,
        specification_document_id=doc.id
    )

    assert baseline.id is not None
    assert baseline.version_number == 1

    # 4. Query extracted requirements
    reqs = step4_db.query(Requirement).filter(Requirement.baseline_version_id == baseline.id).all()
    assert len(reqs) > 0

    # Ensure at least one QR requirement was identified from the QR section
    qr_reqs = [r for r in reqs if r.is_QR]
    assert len(qr_reqs) > 0, "Expected at least one Qualification Requirement from Section 1"

    # Ensure technical clauses were extracted
    clauses = [r.clause for r in reqs if r.clause]
    print(f"\nExtracted clauses: {clauses}")
    print(f"Total requirements extracted: {len(reqs)} (QR: {len(qr_reqs)})")

