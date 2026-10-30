"""
Baseline and Bidder Services for Step 5.
Rules:
1. Show Qualification Requirements (QR) first.
2. Saving creates Baseline Version 1.
3. If engineer edits anything later, increment to Version 2 without overwriting Version 1.
4. Bidder setup: add/delete any number of bidders.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from db.models import Tender, BaselineVersion, Requirement, Bidder


def get_latest_baseline(db: Session, tender_id: int) -> Optional[BaselineVersion]:
    """Retrieves the latest baseline version for a tender."""
    return (
        db.query(BaselineVersion)
        .filter(BaselineVersion.tender_id == tender_id)
        .order_by(BaselineVersion.version_number.desc())
        .first()
    )


def get_baseline_requirements(db: Session, baseline_id: int) -> List[Requirement]:
    """
    Returns requirements ordered with QR first, then clause / id.
    Strict rule from Dev Guide: Qualification requirements must be listed first.
    """
    return (
        db.query(Requirement)
        .filter(Requirement.baseline_version_id == baseline_id)
        .order_by(Requirement.is_QR.desc(), Requirement.clause.asc(), Requirement.id.asc())
        .all()
    )


def save_baseline_edits(
    db: Session,
    tender_id: int,
    edited_requirements: List[Dict[str, Any]]
) -> BaselineVersion:
    """
    Saves edited requirements by creating a new Baseline Version increment.
    Preserves all previous versions immutably.
    """
    latest = get_latest_baseline(db, tender_id)
    next_version = (latest.version_number + 1) if latest else 1

    new_baseline = BaselineVersion(
        tender_id=tender_id,
        version_number=next_version,
        approved_at=datetime.utcnow()
    )
    db.add(new_baseline)
    db.commit()
    db.refresh(new_baseline)

    for item in edited_requirements:
        req = Requirement(
            baseline_version_id=new_baseline.id,
            clause=item.get("clause"),
            text=item.get("text", "").strip(),
            page_number=int(item.get("page_number", 1)) if item.get("page_number") is not None else 1,
            is_QR=bool(item.get("is_QR", False)),
            not_applicable=bool(item.get("not_applicable", False))
        )
        db.add(req)

    db.commit()
    db.refresh(new_baseline)
    return new_baseline


def get_bidders_for_tender(db: Session, tender_id: int) -> List[Bidder]:
    """Fetch all bidders for a tender."""
    return db.query(Bidder).filter(Bidder.tender_id == tender_id).all()


def add_bidder(db: Session, tender_id: int, name: str) -> Bidder:
    """Add a new bidder to a tender."""
    name = name.strip()
    if not name:
        raise ValueError("Bidder name cannot be empty.")
    
    existing = db.query(Bidder).filter(Bidder.tender_id == tender_id, Bidder.name == name).first()
    if existing:
        raise ValueError(f"Bidder '{name}' is already registered for this tender.")
    
    bidder = Bidder(tender_id=tender_id, name=name, final_status="Pending")
    db.add(bidder)
    db.commit()
    db.refresh(bidder)
    return bidder


def delete_bidder(db: Session, bidder_id: int) -> None:
    """Remove a bidder from a tender."""
    bidder = db.query(Bidder).filter(Bidder.id == bidder_id).first()
    if bidder:
        db.delete(bidder)
        db.commit()

