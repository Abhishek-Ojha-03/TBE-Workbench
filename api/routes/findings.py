"""
Finding endpoints — thin wrapper around db/audit_service.py, unchanged.
Matches the Verification Results screen: list findings for a bidder,
Confirm / Override / Flag actions, and manual bidder qualify/disqualify.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import (
    FindingResponse,
    EvidenceResponse,
    AuditLogResponse,
    OverrideRequest,
    FlagRequest,
    QualifyRequest,
    BidderResponse,
)
from db.models import Bidder, Finding
from db.repository import get_tender_by_id
from db.baseline_service import get_latest_baseline
from db.audit_service import confirm_finding, override_finding, flag_for_review, get_audit_trail_for_finding

tenders_router = APIRouter(prefix="/tenders/{tender_id}", tags=["findings"])
findings_router = APIRouter(prefix="/findings", tags=["findings"])


def _to_finding_response(db: Session, f: Finding) -> FindingResponse:
    req = f.requirement
    evidence = f.evidences[0] if f.evidences else None
    audit_logs = get_audit_trail_for_finding(db, f.id)

    return FindingResponse(
        id=f.id,
        requirement_id=f.requirement_id,
        clause=req.clause if req else None,
        requirement_text=req.text if req else "",
        ai_status=f.ai_status,
        engineer_status=f.engineer_status,
        remark=f.remark,
        evidence=(
            EvidenceResponse(
                quoted_text=evidence.quoted_text,
                page_number=evidence.page.page_number if evidence.page else None,
            )
            if evidence
            else None
        ),
        audit_history=[
            AuditLogResponse(
                timestamp=log.timestamp,
                who=log.who,
                what_changed=log.what_changed,
                old_value=log.old_value,
                new_value=log.new_value,
                reason=log.reason,
            )
            for log in audit_logs
        ],
    )


@tenders_router.get("/bidders/{bidder_id}/findings", response_model=List[FindingResponse])
def list_findings(tender_id: int, bidder_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    latest_b = get_latest_baseline(db, tender_id)
    if not latest_b:
        return []

    active_req_ids = [r.id for r in latest_b.requirements if not r.not_applicable]
    findings = (
        db.query(Finding)
        .filter(Finding.bidder_id == bidder_id, Finding.requirement_id.in_(active_req_ids))
        .all()
    )
    return [_to_finding_response(db, f) for f in findings]


@tenders_router.post("/bidders/{bidder_id}/qualify", response_model=BidderResponse)
def qualify_bidder(tender_id: int, bidder_id: int, payload: QualifyRequest, db: Session = Depends(get_db)):
    """Matches the manual 'Mark as Qualified' / 'Mark Not Qualified' sign-off buttons."""
    if payload.status not in ("Qualified", "Not Qualified"):
        raise HTTPException(status_code=400, detail="status must be 'Qualified' or 'Not Qualified'")

    bidder = db.query(Bidder).filter(Bidder.id == bidder_id, Bidder.tender_id == tender_id).first()
    if not bidder:
        raise HTTPException(status_code=404, detail="Bidder not found")

    bidder.final_status = payload.status
    db.commit()
    db.refresh(bidder)
    return BidderResponse.model_validate(bidder)


@findings_router.post("/{finding_id}/confirm", response_model=FindingResponse)
def confirm(finding_id: int, db: Session = Depends(get_db)):
    finding = confirm_finding(db, finding_id, who="Engineer")
    return _to_finding_response(db, finding)


@findings_router.post("/{finding_id}/override", response_model=FindingResponse)
def override(finding_id: int, payload: OverrideRequest, db: Session = Depends(get_db)):
    try:
        finding = override_finding(db, finding_id, payload.status, payload.reason, who="Engineer")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _to_finding_response(db, finding)


@findings_router.post("/{finding_id}/flag", response_model=FindingResponse)
def flag(finding_id: int, payload: FlagRequest, db: Session = Depends(get_db)):
    finding = flag_for_review(db, finding_id, reason=payload.reason, who="Engineer")
    return _to_finding_response(db, finding)
