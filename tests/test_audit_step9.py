"""
Unit test for Step 9: Review Screen and Audit Trail.
Done when: Someone else can review one bidder using only this screen, and every change appears in the audit log.
Verifies:
1. Confirm action updates engineer_status and logs audit trail.
2. Override action strictly enforces a reason and updates audit trail.
3. Every action records: who, what, old value, new value, reason, and timestamp.
"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, Tender, BaselineVersion, Requirement, Bidder, Finding, AuditLog
from db.audit_service import confirm_finding, override_finding, flag_for_review, get_audit_trail_for_finding

TEST_STEP9_DB = "test_step9.db"
TEST_URL = f"sqlite:///{TEST_STEP9_DB}"


@pytest.fixture(scope="module")
def step9_db():
    engine = create_engine(TEST_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()
    yield db
    db.close()
    engine.dispose()
    if os.path.exists(TEST_STEP9_DB):
        try:
            os.remove(TEST_STEP9_DB)
        except PermissionError:
            pass


def test_review_actions_and_audit_trail(step9_db):
    # 1. Setup tender, requirement, bidder, finding
    tender = Tender(description="Audit Test Tender", nit_no="NIT-STEP9-AUDIT", status="open")
    step9_db.add(tender)
    step9_db.commit()

    baseline = BaselineVersion(tender_id=tender.id, version_number=1)
    step9_db.add(baseline)
    step9_db.commit()

    req = Requirement(baseline_version_id=baseline.id, clause="5.1", text="Impulse withstand 170 kV", is_QR=False)
    bidder = Bidder(tender_id=tender.id, name="Test Bidder Corp")
    step9_db.add_all([req, bidder])
    step9_db.commit()

    finding = Finding(
        requirement_id=req.id,
        bidder_id=bidder.id,
        ai_status="Complied",
        engineer_status=None,
        remark="Test report verified"
    )
    step9_db.add(finding)
    step9_db.commit()

    # 2. Test Confirm Action
    confirmed_finding = confirm_finding(step9_db, finding.id, who="Lead Engineer John")
    assert confirmed_finding.engineer_status == "Complied"

    logs = get_audit_trail_for_finding(step9_db, finding.id)
    assert len(logs) == 1
    assert logs[0].who == "Lead Engineer John"
    assert logs[0].old_value is None
    assert logs[0].new_value == "Complied"
    assert "accepted and confirmed" in logs[0].reason

    # 3. Test Override Action without reason (Must Fail)
    with pytest.raises(ValueError, match="mandatory"):
        override_finding(step9_db, finding.id, new_status="Not Complied", reason="")

    # 4. Test Override Action with valid reason
    overridden_finding = override_finding(
        step9_db,
        finding.id,
        new_status="Not Complied",
        reason="Impulse report is older than 5 years; invalid under tender clause 2.3",
        who="Sr Manager Alice"
    )
    assert overridden_finding.engineer_status == "Not Complied"

    # 5. Verify Audit Log Trail
    all_logs = get_audit_trail_for_finding(step9_db, finding.id)
    assert len(all_logs) == 2
    assert all_logs[1].who == "Sr Manager Alice"
    assert all_logs[1].old_value == "Complied"
    assert all_logs[1].new_value == "Not Complied"
    assert "older than 5 years" in all_logs[1].reason

    # 6. Verify Bidder status updated automatically to Not Qualified
    step9_db.refresh(bidder)
    assert bidder.final_status == "Not Qualified"

