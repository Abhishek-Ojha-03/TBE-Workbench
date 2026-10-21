"""
Unit test for Step 1: Database creation and basic CRUD operations.
Specification test: Done when tables are created, and a test can add a tender with a bidder and read it back.
"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Tender, Bidder, BaselineVersion, Requirement, Finding
from db.connection import set_sqlite_pragma

TEST_DB = "test_tbe.db"
TEST_DATABASE_URL = f"sqlite:///{TEST_DB}"


@pytest.fixture(scope="module")
def test_db():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    
    yield db
    
    db.close()
    engine.dispose()
    Base.metadata.drop_all(bind=engine)
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except PermissionError:
            pass


def test_create_and_read_tender_with_bidder(test_db):
    # 1. Create Tender
    new_tender = Tender(
        description="Supply of 11kV Indoor VCB Switchgear Panels",
        nit_no="NIT-BSES-2026-001",
        status="open"
    )
    test_db.add(new_tender)
    test_db.commit()
    test_db.refresh(new_tender)

    assert new_tender.id is not None
    assert new_tender.nit_no == "NIT-BSES-2026-001"

    # 2. Add Bidder
    new_bidder = Bidder(
        tender_id=new_tender.id,
        name="Schneider Electric India Pvt Ltd",
        final_status="Pending"
    )
    test_db.add(new_bidder)
    test_db.commit()
    test_db.refresh(new_bidder)

    assert new_bidder.id is not None
    assert new_bidder.tender_id == new_tender.id
    assert new_bidder.name == "Schneider Electric India Pvt Ltd"

    # 3. Read it back
    fetched_tender = test_db.query(Tender).filter(Tender.nit_no == "NIT-BSES-2026-001").first()
    assert fetched_tender is not None
    assert len(fetched_tender.bidders) == 1
    assert fetched_tender.bidders[0].name == "Schneider Electric India Pvt Ltd"


def test_baseline_and_findings_relationships(test_db):
    tender = test_db.query(Tender).first()
    bidder = test_db.query(Bidder).first()

    # 1. Create Baseline Version 1
    baseline = BaselineVersion(tender_id=tender.id, version_number=1)
    test_db.add(baseline)
    test_db.commit()
    test_db.refresh(baseline)

    # 2. Add a Qualification Requirement (QR)
    req = Requirement(
        baseline_version_id=baseline.id,
        clause="QR-1.1",
        text="Bidder must have manufactured at least 500 units in last 3 years.",
        is_QR=True
    )
    test_db.add(req)
    test_db.commit()
    test_db.refresh(req)

    # 3. Add a Finding (Matrix cell)
    finding = Finding(
        requirement_id=req.id,
        bidder_id=bidder.id,
        ai_status="Needs Human Review",
        engineer_status=None
    )
    test_db.add(finding)
    test_db.commit()
    test_db.refresh(finding)

    assert finding.id is not None
    assert finding.requirement.clause == "QR-1.1"
    assert finding.bidder.name == "Schneider Electric India Pvt Ltd"
