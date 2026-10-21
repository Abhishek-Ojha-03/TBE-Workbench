"""
Unit test for Step 5: Engineer edits and approves the baseline.
Done when: You edit a requirement, save, reload the page, and see the change. Version 1 is still stored.
"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Tender, BaselineVersion, Requirement, Bidder
from db.baseline_service import (
    get_latest_baseline,
    get_baseline_requirements,
    save_baseline_edits,
    add_bidder,
    get_bidders_for_tender
)

TEST_STEP5_DB = "test_step5.db"
TEST_URL = f"sqlite:///{TEST_STEP5_DB}"


@pytest.fixture(scope="module")
def step5_db():
    engine = create_engine(TEST_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    yield db
    db.close()
    engine.dispose()
    if os.path.exists(TEST_STEP5_DB):
        try:
            os.remove(TEST_STEP5_DB)
        except PermissionError:
            pass


def test_baseline_versioning_and_edits(step5_db):
    # 1. Setup tender
    tender = Tender(description="Baseline Test Tender", nit_no="NIT-STEP5-001", status="open")
    step5_db.add(tender)
    step5_db.commit()

    # 2. Create initial Baseline Version 1
    v1 = BaselineVersion(tender_id=tender.id, version_number=1)
    step5_db.add(v1)
    step5_db.commit()

    req1 = Requirement(baseline_version_id=v1.id, clause="QR-1", text="Must have 5 yrs experience", is_QR=True)
    req2 = Requirement(baseline_version_id=v1.id, clause="4.1", text="11kV rated voltage", is_QR=False)
    step5_db.add_all([req1, req2])
    step5_db.commit()

    # Verify Version 1
    latest = get_latest_baseline(step5_db, tender.id)
    assert latest.version_number == 1
    v1_reqs = get_baseline_requirements(step5_db, latest.id)
    assert len(v1_reqs) == 2
    assert v1_reqs[0].is_QR is True  # QR must be listed first

    # 3. Engineer edits requirements and saves -> creates Version 2
    edited_data = [
        {"clause": "QR-1", "text": "Must have 7 yrs experience (updated)", "is_QR": True, "not_applicable": False},
        {"clause": "4.1", "text": "11kV rated voltage", "is_QR": False, "not_applicable": False},
        {"clause": "4.2", "text": "630A busbar rating (new)", "is_QR": False, "not_applicable": False}
    ]
    v2 = save_baseline_edits(step5_db, tender.id, edited_data)
    assert v2.version_number == 2

    # Verify Version 2 is now active
    active = get_latest_baseline(step5_db, tender.id)
    assert active.version_number == 2
    v2_reqs = get_baseline_requirements(step5_db, active.id)
    assert len(v2_reqs) == 3
    assert v2_reqs[0].text == "Must have 7 yrs experience (updated)"

    # Verify Version 1 is STILL preserved in the database
    old_v1 = step5_db.query(BaselineVersion).filter(BaselineVersion.tender_id == tender.id, BaselineVersion.version_number == 1).first()
    assert old_v1 is not None
    assert len(old_v1.requirements) == 2
    assert old_v1.requirements[0].text == "Must have 5 yrs experience"


def test_bidder_setup(step5_db):
    tender = step5_db.query(Tender).filter(Tender.nit_no == "NIT-STEP5-001").first()

    # Add 3 bidders
    b1 = add_bidder(step5_db, tender.id, "Bidder A - Compliant Ltd")
    b2 = add_bidder(step5_db, tender.id, "Bidder B - Deviation Corp")
    b3 = add_bidder(step5_db, tender.id, "Bidder C - Missing Docs Ltd")

    bidders = get_bidders_for_tender(step5_db, tender.id)
    assert len(bidders) == 3
    names = [b.name for b in bidders]
    assert "Bidder A - Compliant Ltd" in names
    assert "Bidder B - Deviation Corp" in names
    assert "Bidder C - Missing Docs Ltd" in names

