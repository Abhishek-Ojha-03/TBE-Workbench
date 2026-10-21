"""
Unit test for Step 11: Create the final documents and complete tender.
Done when: The three files open correctly in Excel and Word and look like the templates.
The tender appears under Completed on the home page and can still be opened.
Verifies:
1. Final TBE Excel generation via openpyxl.
2. Final TBE MOM (.docx) generation via python-docx.
3. Final TBE TER Report (.docx) generation via python-docx.
4. Marking tender as Completed and verifying persistent archival status.
"""
import os
import openpyxl
from docx import Document as DocxDocument
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Tender, BaselineVersion, Requirement, Bidder, Finding
from outputs.excel_generator import WorkingExcelGenerator
from outputs.docx_generator import generate_tbe_mom, generate_tbe_report
from db.repository import update_tender_status, get_all_tenders

TEST_STEP11_DB = "test_step11.db"
TEST_URL = f"sqlite:///{TEST_STEP11_DB}"


@pytest.fixture(scope="module")
def step11_db():
    engine = create_engine(TEST_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    yield db
    db.close()
    engine.dispose()
    if os.path.exists(TEST_STEP11_DB):
        try:
            os.remove(TEST_STEP11_DB)
        except PermissionError:
            pass


def test_final_documents_and_tender_completion(step11_db):
    # 1. Setup Complete Tender
    tender = Tender(
        description="Supply of 11kV Indoor VCB Switchgear",
        nit_no="NIT-BSES-FINAL-PKG",
        status="open"
    )
    step11_db.add(tender)
    step11_db.commit()

    v1 = BaselineVersion(tender_id=tender.id, version_number=1)
    step11_db.add(v1)
    step11_db.commit()

    r1 = Requirement(baseline_version_id=v1.id, clause="QR-1", text="5 yrs OEM track record", is_QR=True)
    r2 = Requirement(baseline_version_id=v1.id, clause="4.1", text="Rated voltage 11kV", is_QR=False)
    step11_db.add_all([r1, r2])

    b1 = Bidder(tender_id=tender.id, name="ABB India Ltd", final_status="Qualified")
    b2 = Bidder(tender_id=tender.id, name="Siemens Ltd", final_status="Not Qualified")
    step11_db.add_all([b1, b2])
    step11_db.commit()

    # Confirmed findings
    f1 = Finding(requirement_id=r1.id, bidder_id=b1.id, ai_status="Complied", engineer_status="Complied")
    f2 = Finding(requirement_id=r2.id, bidder_id=b1.id, ai_status="Complied", engineer_status="Complied")
    f3 = Finding(requirement_id=r1.id, bidder_id=b2.id, ai_status="Not Complied", engineer_status="Not Complied")
    f4 = Finding(requirement_id=r2.id, bidder_id=b2.id, ai_status="Complied", engineer_status="Complied")
    step11_db.add_all([f1, f2, f3, f4])
    step11_db.commit()

    # 2. Generate File 1: Final TBE Excel
    excel_gen = WorkingExcelGenerator()
    excel_path, _ = excel_gen.generate_working_excel(step11_db, tender, output_filename="Final_TBE_BSES.xlsx")
    assert os.path.exists(excel_path)
    wb = openpyxl.load_workbook(excel_path)
    assert wb.active["B2"].value == "NIT-BSES-FINAL-PKG"
    wb.close()

    # 3. Generate File 2: TBE MOM (.docx)
    mom_path = generate_tbe_mom(step11_db, tender)
    assert os.path.exists(mom_path)
    mom_doc = DocxDocument(mom_path)
    text_mom = " ".join(p.text for p in mom_doc.paragraphs)
    assert "MINUTES OF MEETING" in text_mom
    assert "NIT-BSES-FINAL-PKG" in text_mom

    # 4. Generate File 3: TBE Report (.docx)
    report_path = generate_tbe_report(step11_db, tender)
    assert os.path.exists(report_path)
    rep_doc = DocxDocument(report_path)
    text_rep = " ".join(p.text for p in rep_doc.paragraphs)
    assert "TECHNICAL EVALUATION REPORT" in text_rep
    assert len(rep_doc.tables) >= 1

    # 5. Mark tender Completed
    updated = update_tender_status(step11_db, tender.id, "completed")
    assert updated.status == "completed"

    # Verify tender appears under Completed and remains openable
    completed_list = get_all_tenders(step11_db, status="completed")
    assert any(t.nit_no == "NIT-BSES-FINAL-PKG" for t in completed_list)

