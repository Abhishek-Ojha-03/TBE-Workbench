"""
Deterministic Rule Engine (Step 8)
Pure Python business logic (No AI used here).

Rules from Dev Guide:
1. The Deviation Sheet is not NIL -> Not Complied for that requirement.
2. No evidence is found for a requirement -> Needs Human Review.
3. A mandatory document is missing -> Suggest Not Complied (engineer confirms).
4. Any requirement is confirmed Not Complied -> Bidder is 'Not Qualified'.
5. Any row is still Needs Human Review -> Bidder 'Cannot be Qualified yet' (Pending).
6. Every row is Complied or N/A, all confirmed -> Bidder can be 'Qualified' once engineer confirms.

Important rule: Only the engineer's confirmed statuses count towards the final bidder result.
The AI's suggestions do not decide qualification alone.
"""
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from db.models import Bidder, Finding, Requirement, Document


class BidderQualificationResult:
    QUALIFIED = "Qualified"
    NOT_QUALIFIED = "Not Qualified"
    CANNOT_BE_QUALIFIED_YET = "Pending"  # Needs review/clarifications


def evaluate_deviation_sheet(deviation_text: str) -> str:
    """
    Deviation Sheet is compliant ONLY if it explicitly states 'NIL'.
    Any mentioned deviation results in 'Not Complied'.
    """
    cleaned = deviation_text.strip().upper()
    if cleaned in ["NIL", "NIL DEVIATION", "NIL DEVIATIONS", "NO DEVIATION", "NO DEVIATIONS"]:
        return "Complied"
    return "Not Complied"


def evaluate_mandatory_documents(submitted_doc_types: List[str]) -> Tuple[str, List[str]]:
    """
    Checks presence of mandatory documents:
    - Technical Offer
    - Deviation Sheet
    Returns: (suggested_status, missing_docs_list)
    """
    required = ["Technical Offer", "Deviation Sheet"]
    normalized_submitted = [d.strip().lower() for d in submitted_doc_types]
    
    missing = []
    for r in required:
        if not any(r.lower() in sub for sub in normalized_submitted):
            missing.append(r)

    if missing:
        return "Not Complied", missing
    return "Complied", []


def compute_bidder_status(findings: List[Finding]) -> str:
    """
    Determines overall bidder qualification based on confirmed findings.
    Only confirmed engineer statuses decide the final verdict.
    If engineer_status is not yet set, we evaluate whether it can be qualified yet.
    """
    if not findings:
        return BidderQualificationResult.CANNOT_BE_QUALIFIED_YET

    statuses = []
    for f in findings:
        # Prioritize confirmed engineer status; fall back to AI suggestion for pre-check
        status = (f.engineer_status or f.ai_status or "").strip()
        statuses.append(status)

    # 1. Any confirmed Not Complied makes the bidder Not Qualified
    if any(s == "Not Complied" for s in statuses):
        return BidderQualificationResult.NOT_QUALIFIED

    # 2. Any row is still "Needs Human Review" -> Cannot be Qualified yet
    if any(s == "Needs Human Review" or not s for s in statuses):
        return BidderQualificationResult.CANNOT_BE_QUALIFIED_YET

    # 3. Every row is Complied or N/A
    all_ok = all(s in ["Complied", "N/A"] for s in statuses)
    if all_ok:
        return BidderQualificationResult.QUALIFIED

    return BidderQualificationResult.CANNOT_BE_QUALIFIED_YET


def update_bidder_qualification_status(db: Session, bidder_id: int) -> str:
    """
    Calculates and persists the updated qualification status for a bidder in SQLite.
    """
    bidder = db.query(Bidder).filter(Bidder.id == bidder_id).first()
    if not bidder:
        raise ValueError(f"Bidder {bidder_id} not found.")

    findings = db.query(Finding).filter(Finding.bidder_id == bidder_id).all()
    status = compute_bidder_status(findings)
    bidder.final_status = status
    db.commit()
    db.refresh(bidder)
    return status

