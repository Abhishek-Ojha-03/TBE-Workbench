"""
Tender endpoints — thin wrapper around db/repository.py.

No business logic lives here. Every function below calls the SAME
create_tender / get_all_tenders / get_tender_by_id used by the existing
Streamlit UI (ui/*.py, app.py) — this is a second front door onto the same
logic, not a parallel implementation of it.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import TenderCreateRequest, TenderResponse
from db.repository import create_tender, get_all_tenders, get_tender_by_id

router = APIRouter(prefix="/tenders", tags=["tenders"])


def _to_response(tender) -> TenderResponse:
    return TenderResponse(
        id=tender.id,
        description=tender.description,
        nit_no=tender.nit_no,
        status=tender.status,
        created_at=tender.created_at,
        bidder_count=len(tender.bidders),
    )


@router.get("", response_model=List[TenderResponse])
def list_tenders(status: Optional[str] = None, db: Session = Depends(get_db)):
    """Matches the Home screen's Open/Completed tabs (?status=open|completed)."""
    tenders = get_all_tenders(db, status=status)
    return [_to_response(t) for t in tenders]


@router.post("", response_model=TenderResponse, status_code=201)
def create_new_tender(payload: TenderCreateRequest, db: Session = Depends(get_db)):
    """Matches the Home screen's 'Create New Tender' modal."""
    try:
        tender = create_tender(db, payload.description, payload.nit_no)
    except ValueError as e:
        # Duplicate NIT number, etc. — same validation already enforced
        # in db/repository.py, just surfaced as a proper HTTP error here.
        raise HTTPException(status_code=409, detail=str(e))
    return _to_response(tender)


@router.get("/{tender_id}", response_model=TenderResponse)
def get_tender(tender_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    return _to_response(tender)
