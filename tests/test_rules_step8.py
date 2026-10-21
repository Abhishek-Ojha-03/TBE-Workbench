"""
Unit tests for Step 8: The Rule Engine.
Done when: All rule tests pass, including odd cases:
- All rows N/A
- One row left in review
- One row overridden
- Deviation sheet not NIL
- Missing mandatory document
"""
import pytest
from rules.rule_engine import (
    evaluate_deviation_sheet,
    evaluate_mandatory_documents,
    compute_bidder_status,
    BidderQualificationResult
)
from db.models import Finding


class MockFinding:
    def __init__(self, ai_status, engineer_status=None):
        self.ai_status = ai_status
        self.engineer_status = engineer_status


def test_deviation_sheet_rules():
    # Only NIL is Complied
    assert evaluate_deviation_sheet("NIL") == "Complied"
    assert evaluate_deviation_sheet("NIL DEVIATION") == "Complied"
    assert evaluate_deviation_sheet("nil") == "Complied"

    # Any listed deviation is Not Complied
    assert evaluate_deviation_sheet("Busbar is Aluminium instead of Copper") == "Not Complied"
    assert evaluate_deviation_sheet("Paint shade 631 instead of 632") == "Not Complied"


def test_mandatory_documents_rules():
    # Both present
    status, missing = evaluate_mandatory_documents(["Technical Offer", "Deviation Sheet", "Type Test"])
    assert status == "Complied"
    assert len(missing) == 0

    # Missing Technical Offer
    status, missing = evaluate_mandatory_documents(["Deviation Sheet", "Type Test"])
    assert status == "Not Complied"
    assert "Technical Offer" in missing

    # Missing Deviation Sheet
    status, missing = evaluate_mandatory_documents(["Technical Offer"])
    assert status == "Not Complied"
    assert "Deviation Sheet" in missing


def test_bidder_qualification_logic():
    # Case 1: Fully compliant bidder
    findings = [
        MockFinding(ai_status="Complied", engineer_status="Complied"),
        MockFinding(ai_status="Complied", engineer_status="Complied"),
        MockFinding(ai_status="Complied", engineer_status="Complied")
    ]
    assert compute_bidder_status(findings) == BidderQualificationResult.QUALIFIED

    # Case 2: One row confirmed Not Complied -> Immediately Not Qualified
    findings_failed = [
        MockFinding(ai_status="Complied", engineer_status="Complied"),
        MockFinding(ai_status="Not Complied", engineer_status="Not Complied"),
        MockFinding(ai_status="Complied", engineer_status="Complied")
    ]
    assert compute_bidder_status(findings_failed) == BidderQualificationResult.NOT_QUALIFIED

    # Case 3: One row left in Needs Human Review -> Cannot be qualified yet (Pending)
    findings_pending = [
        MockFinding(ai_status="Complied", engineer_status="Complied"),
        MockFinding(ai_status="Needs Human Review", engineer_status=None),
        MockFinding(ai_status="Complied", engineer_status="Complied")
    ]
    assert compute_bidder_status(findings_pending) == BidderQualificationResult.CANNOT_BE_QUALIFIED_YET


def test_edge_cases():
    # Odd case A: All rows marked N/A
    all_na = [
        MockFinding(ai_status="Complied", engineer_status="N/A"),
        MockFinding(ai_status="Complied", engineer_status="N/A")
    ]
    assert compute_bidder_status(all_na) == BidderQualificationResult.QUALIFIED

    # Odd case B: One row overridden from AI 'Complied' to Engineer 'Not Complied'
    overridden = [
        MockFinding(ai_status="Complied", engineer_status="Complied"),
        MockFinding(ai_status="Complied", engineer_status="Not Complied")  # Overridden by engineer
    ]
    assert compute_bidder_status(overridden) == BidderQualificationResult.NOT_QUALIFIED

    # Odd case C: Overridden from AI 'Not Complied' to Engineer 'Complied'
    overridden_to_pass = [
        MockFinding(ai_status="Not Complied", engineer_status="Complied"),  # Engineer accepted explanation
        MockFinding(ai_status="Complied", engineer_status="Complied")
    ]
    assert compute_bidder_status(overridden_to_pass) == BidderQualificationResult.QUALIFIED

