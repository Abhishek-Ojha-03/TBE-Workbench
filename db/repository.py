"""
Tender Repository: Encapsulates all persistent database operations for Tenders.
Strict rule: State is ALWAYS stored and retrieved from the database, never ephemeral session state.
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from db.models import Tender, Bidder, BaselineVersion, Requirement


def get_all_tenders(db: Session, status: Optional[str] = None) -> List[Tender]:
    """Retrieve all tenders, optionally filtered by status ('open' or 'completed')."""
    query = db.query(Tender)
    if status:
        query = query.filter(Tender.status == status)
    return query.order_by(Tender.created_at.desc()).all()


def get_tender_by_id(db: Session, tender_id: int) -> Optional[Tender]:
    """Retrieve a single tender by its primary key ID."""
    return db.query(Tender).filter(Tender.id == tender_id).first()


def get_tender_by_nit(db: Session, nit_no: str) -> Optional[Tender]:
    """Retrieve a tender by NIT number."""
    return db.query(Tender).filter(Tender.nit_no == nit_no).first()


def create_tender(db: Session, description: str, nit_no: str) -> Tender:
    """Create a new tender with status 'open'."""
    existing = get_tender_by_nit(db, nit_no)
    if existing:
        raise ValueError(f"Tender with NIT No. '{nit_no}' already exists.")

    new_tender = Tender(
        description=description.strip(),
        nit_no=nit_no.strip(),
        status="open"
    )
    db.add(new_tender)
    db.commit()
    db.refresh(new_tender)
    return new_tender


def update_tender_status(db: Session, tender_id: int, status: str) -> Tender:
    """Update tender status, e.g. marking it 'completed'."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise ValueError(f"Tender with ID {tender_id} not found.")
    
    tender.status = status
    db.commit()
    db.refresh(tender)
    return tender

