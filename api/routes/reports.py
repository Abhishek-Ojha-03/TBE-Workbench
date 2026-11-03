"""
Reports & Completion endpoints — compliance/risk matrix (same scoring
logic as ui/reports_view.py), clarification letter drafting, delta
re-verification, and tender completion. All wrap existing functions
unchanged.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import ComplianceRow, ClarificationLetterResponse, DeltaReverifyResponse, TenderResponse
from db.models import Bidder, Finding
from db.repository import get_tender_by_id, update_tender_status
from db.baseline_service import get_latest_baseline, get_baseline_requirements, get_bidders_for_tender
from ai.clarification_service import generate_clarification_letter, handle_clarification_response, recheck_flagged_findings
from rules.rule_engine import update_bidder_qualification_status

router = APIRouter(prefix="/tenders/{tender_id}", tags=["reports"])


@router.get("/compliance-matrix", response_model=List[ComplianceRow])
def compliance_matrix(tender_id: int, db: Session = Depends(get_db)):
    """
    Same scoring/risk logic as ui/reports_view.py's "Preview: Compliance
    Scores & Risk Matrix" expander — QR-clause failures are High Risk
    regardless of overall score, matching the original rule exactly.
    """
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    bidders = get_bidders_for_tender(db, tender_id)
    latest_b = get_latest_baseline(db, tender_id)
    reqs = get_baseline_requirements(db, latest_b.id) if latest_b else []
    req_ids = [r.id for r in reqs]
    total_reqs = len(reqs)
    qr_ids = {r.id for r in reqs if r.is_QR}

    rows: List[ComplianceRow] = []
    for b in bidders:
        findings = db.query(Finding).filter(Finding.bidder_id == b.id, Finding.requirement_id.in_(req_ids)).all()
        complied = sum(1 for f in findings if (f.engineer_status or f.ai_status or "").lower() == "complied")
        not_complied = sum(1 for f in findings if (f.engineer_status or f.ai_status or "").lower() == "not complied")
        reviews = sum(1 for f in findings if "review" in (f.engineer_status or f.ai_status or "").lower())
        score = round((complied / total_reqs * 100), 1) if total_reqs else 0.0

        qr_failures = sum(
            1 for f in findings
            if f.requirement_id in qr_ids and (f.engineer_status or f.ai_status or "").lower() == "not complied"
        )
        if qr_failures > 0 or b.final_status == "Not Qualified":
            risk = "High Risk"
        elif not_complied > 0 or reviews > 2:
            risk = "Medium Risk"
        elif reviews > 0:
            risk = "Low Risk"
        else:
            risk = "Clean"

        rows.append(
            ComplianceRow(
                bidder_id=b.id,
                bidder_name=b.name,
                total_clauses=total_reqs,
                complied=complied,
                not_complied=not_complied,
                under_review=reviews,
                score_pct=score,
                risk=risk,
                status=b.final_status or "Pending",
            )
        )
    return rows


@router.post("/bidders/{bidder_id}/clarification-letter", response_model=ClarificationLetterResponse)
def draft_clarification_letter(tender_id: int, bidder_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    bidder = db.query(Bidder).filter(Bidder.id == bidder_id, Bidder.tender_id == tender_id).first()
    if not bidder:
        raise HTTPException(status_code=404, detail="Bidder not found")

    flagged = (
        db.query(Finding)
        .filter(
            Finding.bidder_id == bidder_id,
            (Finding.ai_status == "Needs Human Review")
            | (Finding.engineer_status == "Needs Human Review")
            | (Finding.needs_recheck == True),  # noqa: E712
        )
        .all()
    )

    if not flagged:
        return ClarificationLetterResponse(letter="", flagged_count=0)

    letter = generate_clarification_letter(db, tender, bidder, flagged)
    return ClarificationLetterResponse(letter=letter, flagged_count=len(flagged))


@router.post("/bidders/{bidder_id}/clarification-reply", response_model=DeltaReverifyResponse)
async def upload_clarification_reply(
    tender_id: int, bidder_id: int, files: List[UploadFile] = File(...), db: Session = Depends(get_db)
):
    """Matches 'Upload Clarification Reply & Delta Re-Verify' — re-verifies
    ONLY the previously-flagged rows, not the whole tender."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    flagged = (
        db.query(Finding)
        .filter(
            Finding.bidder_id == bidder_id,
            (Finding.ai_status == "Needs Human Review")
            | (Finding.engineer_status == "Needs Human Review")
            | (Finding.needs_recheck == True),  # noqa: E712
        )
        .all()
    )
    affected_ids = [f.requirement_id for f in flagged]

    for f in files:
        file_bytes = await f.read()
        handle_clarification_response(db, bidder_id, file_bytes, f.filename, affected_ids)

    rechecked = recheck_flagged_findings(db, bidder_id)
    new_status = update_bidder_qualification_status(db, bidder_id)

    return DeltaReverifyResponse(
        rechecked_count=len(rechecked),
        new_status=new_status,
        clauses=[f.requirement.clause or "General" for f in rechecked],
    )


@router.post("/complete", response_model=TenderResponse)
def complete_tender(tender_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    updated = update_tender_status(db, tender_id, "completed")
    return TenderResponse(
        id=updated.id,
        description=updated.description,
        nit_no=updated.nit_no,
        status=updated.status,
        created_at=updated.created_at,
        bidder_count=len(updated.bidders),
    )
