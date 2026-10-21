"""
Unit test for Step 2: Home Page logic and persistence.
Done when: You create a tender, close the browser, open it again, and the tender is still there.
(Verified programmatically by creating via repository in one session, closing the session, and reading back in an independent session).
"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Tender
from db.repository import create_tender, get_all_tenders, update_tender_status, get_tender_by_nit

TEST_DB_STEP2 = "test_step2_home.db"
TEST_URL = f"sqlite:///{TEST_DB_STEP2}"


@pytest.fixture(scope="module")
def step2_engine():
    engine = create_engine(TEST_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    if os.path.exists(TEST_DB_STEP2):
        try:
            os.remove(TEST_DB_STEP2)
        except PermissionError:
            pass


def test_tender_creation_persists_across_sessions(step2_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=step2_engine)

    # Session 1: User fills the form on Home Page and creates Tender
    db1 = Session()
    created = create_tender(
        db1,
        description="Supply of 66kV Power Transformers",
        nit_no="NIT-BSES-STEP2-001"
    )
    assert created.id is not None
    assert created.status == "open"
    db1.close()  # Simulates closing the browser / session teardown

    # Session 2: User opens the browser afresh
    db2 = Session()
    open_tenders = get_all_tenders(db2, status="open")
    assert len(open_tenders) >= 1
    found = any(t.nit_no == "NIT-BSES-STEP2-001" for t in open_tenders)
    assert found is True

    # Check tender properties
    tender = get_tender_by_nit(db2, "NIT-BSES-STEP2-001")
    assert tender.description == "Supply of 66kV Power Transformers"
    assert tender.status == "open"
    db2.close()


def test_completed_tender_archival(step2_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=step2_engine)

    db = Session()
    tender = get_tender_by_nit(db, "NIT-BSES-STEP2-001")
    # Mark tender completed
    update_tender_status(db, tender.id, "completed")
    db.close()

    # Re-query in a fresh session
    db_fresh = Session()
    completed = get_all_tenders(db_fresh, status="completed")
    open_tenders = get_all_tenders(db_fresh, status="open")

    assert any(t.nit_no == "NIT-BSES-STEP2-001" for t in completed)
    assert not any(t.nit_no == "NIT-BSES-STEP2-001" for t in open_tenders)
    db_fresh.close()

