"""
Unit test for Step 10: Clarifications and re-checking.
Done when: You upload one extra document, and only the related rows are re-checked.
Verifies:
1. Generation of formal clarification letter.
2. Flagging affected finding rows as needs_recheck.
3. Delta re-verification executing exclusively on flagged rows while unflagged rows remain untouched.
4. Full audit log history tracking the transition.
"""
import os
import fitz
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Tender, BaselineVersion, Requirement, Bidder, Finding, AuditLog
from ai.clarification_service import (
    generate_clarification_letter,
    handle_clarification_response,
    recheck_flagged_findings
)

TEST_STEP10_DB = "test_step10.db"
TEST_URL = f"sqlite:///{TEST_STEP10_DB}"


@pytest.fixture(scope="module")
def step10_db():
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
    if os.path.exists(TEST_STEP10_DB):
        try:
            os.remove(TEST_STEP10_DB)
        except PermissionError:
            pass


def create_clarification_reply_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    text = (
        "BIDDER CLARIFICATION SUBMISSION\n"
        "Regarding Clause 4.4 Impulse Withstand Voltage:\n"
        "Please find enclosed CPRI test certificate: Rated lightning impulse withstand voltage rating tested and verified at 75 kV peak."
    )
    page.insert_text((50, 72), text, fontsize=11)
    b = doc.tobytes()
    doc.close()
    return b


def test_clarification_workflow_and_delta_recheck(step10_db):
    # 1. Setup tender and 2 requirements
    tender = Tender(description="VCB Clarification Tender", nit_no="NIT-STEP10-CLAR", status="open")
    step10_db.add(tender)
    step10_db.commit()

    baseline = BaselineVersion(tender_id=tender.id, version_number=1)
    step10_db.add(baseline)
    step10_db.commit()

    req_ok = Requirement(baseline_version_id=baseline.id, clause="4.1", text="Rated voltage 11kV", is_QR=False)
    req_deficient = Requirement(baseline_version_id=baseline.id, clause="4.4", text="Lightning impulse withstand rating 75 kV peak", is_QR=False)
    step10_db.add_all([req_ok, req_deficient])

    bidder = Bidder(tender_id=tender.id, name="L&T Electrical")
    step10_db.add(bidder)
    step10_db.commit()

    # Finding 1: Already Complied
    f1 = Finding(requirement_id=req_ok.id, bidder_id=bidder.id, ai_status="Complied", engineer_status="Complied", needs_recheck=False)
    # Finding 2: Needs Clarification
    f2 = Finding(requirement_id=req_deficient.id, bidder_id=bidder.id, ai_status="Needs Human Review", remark="Test report missing", needs_recheck=False)
    step10_db.add_all([f1, f2])
    step10_db.commit()

    # 2. Test Letter Generation
    letter = generate_clarification_letter(step10_db, tender, bidder, [f2])
    assert len(letter) > 50
    assert "75 kV" in letter or "Clause 4.4" in letter or "L&T" in letter

    # 3. Upload Clarification Response for only req_deficient
    reply_pdf = create_clarification_reply_pdf()
    handle_clarification_response(
        db=step10_db,
        bidder_id=bidder.id,
        file_bytes=reply_pdf,
        file_name="L&T_Clarification_Reply_Impulse.pdf",
        affected_requirement_ids=[req_deficient.id]
    )

    # Verify only f2 is flagged for recheck, f1 is untouched
    step10_db.refresh(f1)
    step10_db.refresh(f2)
    assert f1.needs_recheck is False
    assert f2.needs_recheck is True

    # 4. Re-check flagged findings exclusively
    rechecked_findings = recheck_flagged_findings(step10_db, bidder.id)
    assert len(rechecked_findings) == 1
    assert rechecked_findings[0].id == f2.id
    assert rechecked_findings[0].needs_recheck is False

    # Check updated status
    print(f"\nRe-evaluated finding status: {rechecked_findings[0].ai_status}")
    print(f"Remark: {rechecked_findings[0].remark}")
    assert rechecked_findings[0].ai_status in ["Complied", "Needs Human Review"]

    # Check audit log trail for the transition
    logs = step10_db.query(AuditLog).filter(AuditLog.finding_id == f2.id).all()
    assert len(logs) >= 2  # One for flagging, one for AI re-evaluation

