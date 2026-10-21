"""
Audit Trail & Review Service (Step 9)
Rules:
1. Four actions per finding: Confirm, Override, Request Clarification, Flag for Review.
2. Override MUST ask for a reason.
3. Every action writes an immutable row to AuditLog with:
   who, what, old_value, new_value, reason, and timestamp.
4. Updates Finding and re-evaluates Bidder qualification status.
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from db.models import Finding, AuditLog, Bidder, Page, Evidence
from rules.rule_engine import update_bidder_qualification_status


def log_audit_entry(
    db: Session,
    finding_id: int,
    who: str,
    what_changed: str,
    old_value: Optional[str],
    new_value: Optional[str],
    reason: Optional[str] = None
) -> AuditLog:
    """Creates an immutable audit log entry for regulatory and engineering traceability."""
    entry = AuditLog(
        finding_id=finding_id,
        who=who,
        what_changed=what_changed,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        timestamp=datetime.utcnow()
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def confirm_finding(db: Session, finding_id: int, who: str = "Lead Engineer") -> Finding:
    """Engineer confirms the AI's suggested status."""
    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    if not finding:
        raise ValueError(f"Finding {finding_id} not found.")

    old_status = finding.engineer_status
    new_status = finding.ai_status

    finding.engineer_status = new_status
    db.commit()

    log_audit_entry(
        db=db,
        finding_id=finding.id,
        who=who,
        what_changed="engineer_status",
        old_value=old_status,
        new_value=new_status,
        reason="Engineer accepted and confirmed AI recommendation."
    )

    update_bidder_qualification_status(db, finding.bidder_id)
    db.refresh(finding)
    return finding


def override_finding(
    db: Session,
    finding_id: int,
    new_status: str,
    reason: str,
    who: str = "Lead Engineer"
) -> Finding:
    """
    Engineer overrides the status.
    Strict Rule: Reason is mandatory for any override.
    """
    if not reason or not reason.strip():
        raise ValueError("A documented technical reason is mandatory when overriding a finding.")

    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    if not finding:
        raise ValueError(f"Finding {finding_id} not found.")

    old_status = finding.engineer_status or finding.ai_status
    finding.engineer_status = new_status
    db.commit()

    log_audit_entry(
        db=db,
        finding_id=finding.id,
        who=who,
        what_changed="engineer_status",
        old_value=old_status,
        new_value=new_status,
        reason=reason.strip()
    )

    update_bidder_qualification_status(db, finding.bidder_id)
    db.refresh(finding)
    return finding


def flag_for_review(db: Session, finding_id: int, reason: str, who: str = "Lead Engineer") -> Finding:
    """Flags a finding as Needs Human Review."""
    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    if not finding:
        raise ValueError(f"Finding {finding_id} not found.")

    old_status = finding.engineer_status
    finding.engineer_status = "Needs Human Review"
    db.commit()

    log_audit_entry(
        db=db,
        finding_id=finding.id,
        who=who,
        what_changed="engineer_status",
        old_value=old_status,
        new_value="Needs Human Review",
        reason=reason or "Flagged for manual / site verification."
    )

    update_bidder_qualification_status(db, finding.bidder_id)
    db.refresh(finding)
    return finding


def get_audit_trail_for_finding(db: Session, finding_id: int) -> List[AuditLog]:
    """Retrieves chronological audit logs for a given matrix finding."""
    return (
        db.query(AuditLog)
        .filter(AuditLog.finding_id == finding_id)
        .order_by(AuditLog.timestamp.asc())
        .all()
    )

