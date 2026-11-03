"""
Baseline version endpoints — thin wrapper around db/baseline_service.py.

Matches the Requirements & Setup screen's version selector and
"Quick Add Single Requirement" flow. Mirrors the EXACT same semantics the
Streamlit app already uses (ui/baseline_view.py): saving anything — a
bulk edit or a single quick-add row — creates a brand new BaselineVersion
with the FULL requirement list, never edits a version in place. This is
not a simplification; it's the same versioning model, just exposed over
REST for the new frontend.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import (
    BaselineVersionResponse,
    BaselineVersionCreateRequest,
    RequirementResponse,
)
from db.models import BaselineVersion
from db.repository import get_tender_by_id
from db.baseline_service import get_latest_baseline, get_baseline_requirements, save_baseline_edits

router = APIRouter(prefix="/tenders/{tender_id}/baseline-versions", tags=["baseline"])


@router.get("", response_model=List[BaselineVersionResponse])
def list_baseline_versions(tender_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    latest = get_latest_baseline(db, tender_id)
    latest_num = latest.version_number if latest else None

    versions = (
        db.query(BaselineVersion)
        .filter(BaselineVersion.tender_id == tender_id)
        .order_by(BaselineVersion.version_number.desc())
        .all()
    )
    return [
        BaselineVersionResponse(
            version_number=v.version_number,
            approved_at=v.approved_at,
            is_latest=(v.version_number == latest_num),
        )
        for v in versions
    ]


@router.get("/{version_number}/requirements", response_model=List[RequirementResponse])
def get_requirements_for_version(tender_id: int, version_number: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    baseline = (
        db.query(BaselineVersion)
        .filter(BaselineVersion.tender_id == tender_id, BaselineVersion.version_number == version_number)
        .first()
    )
    if not baseline:
        raise HTTPException(status_code=404, detail=f"Baseline version {version_number} not found")

    requirements = get_baseline_requirements(db, baseline.id)
    return [RequirementResponse.model_validate(r) for r in requirements]


@router.post("", response_model=BaselineVersionResponse, status_code=201)
def create_baseline_version(
    tender_id: int, payload: BaselineVersionCreateRequest, db: Session = Depends(get_db)
):
    """
    Creates a new baseline version from the full requirement list sent by
    the frontend. Used both for the "Save Edits as New Version" flow and
    for "Quick Add Single Requirement" (frontend appends one row to the
    current list client-side, then posts the whole thing here) — exactly
    matching how ui/baseline_view.py's quick-add form calls
    save_baseline_edits with current_records + the new row appended.
    """
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    if not payload.requirements:
        raise HTTPException(status_code=400, detail="Cannot save an empty baseline.")

    edited = [r.model_dump() for r in payload.requirements]
    new_baseline = save_baseline_edits(db, tender_id, edited)

    return BaselineVersionResponse(
        version_number=new_baseline.version_number,
        approved_at=new_baseline.approved_at,
        is_latest=True,
    )
