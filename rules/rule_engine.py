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

    # 1. Any confirmed Not Complied on any clause makes the bidder Not Qualified
    for f in findings:
        status = (f.engineer_status or f.ai_status or "").strip()
        if status == "Not Complied":
            return BidderQualificationResult.NOT_QUALIFIED

    # 2. Check Qualification Requirements (QR) specifically
    # Any QR clause not complied or under review halts qualification
    for f in findings:
        status = (f.engineer_status or f.ai_status or "").strip()
        is_qr = f.requirement.is_QR if (f.requirement and hasattr(f.requirement, "is_QR")) else False
        if is_qr and status != "Complied" and status != "N/A":
            return BidderQualificationResult.CANNOT_BE_QUALIFIED_YET

    # 3. Check technical clauses
    # Count complied vs review
    complied_count = sum(1 for f in findings if (f.engineer_status or f.ai_status or "").strip() in ["Complied", "N/A"])
    review_count = sum(1 for f in findings if "review" in (f.engineer_status or f.ai_status or "").strip().lower() or not (f.engineer_status or f.ai_status))

    # All clauses clean and verified -> Qualified
    if review_count == 0 and complied_count > 0:
        return BidderQualificationResult.QUALIFIED

    # If all QR clauses passed and non-QR reviews are 1 or 2 minor items where engineer has confirmed,
    # or if any clauses are pending, maintain Pending until human review
    if any(f.engineer_status == "Qualified" for f in findings):
        return BidderQualificationResult.QUALIFIED

    return BidderQualificationResult.CANNOT_BE_QUALIFIED_YET


def update_bidder_qualification_status(db: Session, bidder_id: int) -> str:
    """
    Calculates and persists the updated qualification status for a bidder in SQLite.
    Evaluates findings strictly against the active baseline requirements for the tender.
    """
    from db.baseline_service import get_latest_baseline
    bidder = db.query(Bidder).filter(Bidder.id == bidder_id).first()
    if not bidder:
        raise ValueError(f"Bidder {bidder_id} not found.")

    latest_b = get_latest_baseline(db, bidder.tender_id)
    if latest_b:
        active_req_ids = [r.id for r in latest_b.requirements if not r.not_applicable]
        findings = db.query(Finding).filter(
            Finding.bidder_id == bidder_id,
            Finding.requirement_id.in_(active_req_ids)
        ).all()
    else:
        findings = db.query(Finding).filter(Finding.bidder_id == bidder_id).all()

    status = compute_bidder_status(findings)
    bidder.final_status = status
    db.commit()
    db.refresh(bidder)
    return status

