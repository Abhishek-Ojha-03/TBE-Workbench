"""
Clarification & Delta Re-checking Service (Step 10)
Rules:
1. Platform drafts a formal clarification letter to the bidder for flagged points.
2. When bidder reply or new document is uploaded, set `needs_recheck = True` ONLY on affected Finding rows.
3. Re-run Step 7 verification EXCLUSIVELY for flagged rows.
4. Keep old results as history in AuditLog.
"""
from typing import List, Dict
from datetime import datetime
from sqlalchemy.orm import Session

from db.models import Finding, Bidder, Tender, Requirement, AuditLog, Document
from reading.ingest import ingest_pdf_document
from ai.verifier import verify_requirement_for_bidder
from ai.client import get_client, MODEL_NAME
from db.audit_service import log_audit_entry


def generate_clarification_letter(
    db: Session,
    tender: Tender,
    bidder: Bidder,
    flagged_findings: List[Finding]
) -> str:
    """
    Drafts an official BSES clarification letter to the bidder citing specific deficient clauses.
    Uses Gemini to compose professional utility correspondence.
    """
    items_text = []
    for f in flagged_findings:
        req = f.requirement
        items_text.append(f"- Clause {req.clause or 'General'}: {req.text} (Issue: {f.remark or 'Clarification requested on proof'})")

    checklist = "\n".join(items_text)

    client = get_client()
    if client is None:
        # Template fallback
        return f"""
BSES EQUIPMENT ENGINEERING DIVISION
TECHNICAL CLARIFICATION REQUEST

To: {bidder.name}
Tender: {tender.description} (NIT No: {tender.nit_no})
Date: {datetime.now().strftime('%d-%b-%Y')}

Dear Sir/Madam,

During the Technical Bid Evaluation of your offer for the subject tender, the following queries / deficiencies have been observed:

{checklist}

You are requested to submit your point-wise clarification along with supporting accredited laboratory test reports / documents within 3 working days.

Yours faithfully,
BSES Equipment Engineering
"""

    prompt = f"""
Draft a formal, professional Technical Clarification Request letter from BSES Equipment Engineering to a bidder.
Tender Description: {tender.description}
NIT Number: {tender.nit_no}
Bidder Name: {bidder.name}
Deficient Requirements / Clarification items:
{checklist}

The letter must specify a 3 working days response time and request authentic supporting documents/test reports.
"""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        return f"Error drafting letter: {e}"


def handle_clarification_response(
    db: Session,
    bidder_id: int,
    file_bytes: bytes,
    file_name: str,
    affected_requirement_ids: List[int]
) -> Document:
    """
    Uploads bidder response PDF document and marks only the affected rows as `needs_recheck = True`.
    """
    # 1. Ingest document (pages and FTS)
    doc = ingest_pdf_document(
        db=db,
        file_bytes=file_bytes,
        file_name=file_name,
        document_type="Clarification Reply",
        bidder_id=bidder_id
    )

    # 2. Flag affected rows only
    for req_id in affected_requirement_ids:
        finding = (
            db.query(Finding)
            .filter(Finding.bidder_id == bidder_id, Finding.requirement_id == req_id)
            .first()
        )
        if finding:
            finding.needs_recheck = True
            log_audit_entry(
                db=db,
                finding_id=finding.id,
                who="System / Ingestion",
                what_changed="needs_recheck",
                old_value="False",
                new_value="True",
                reason=f"New clarification document uploaded: {file_name}"
            )

    db.commit()
    return doc


def recheck_flagged_findings(db: Session, bidder_id: int) -> List[Finding]:
    """
    Re-verifies ONLY rows with needs_recheck == True for this bidder.
    Preserves audit history.
    """
    flagged = (
        db.query(Finding)
        .filter(Finding.bidder_id == bidder_id, Finding.needs_recheck == True)
        .all()
    )

    rechecked = []
    for f in flagged:
        req = f.requirement
        bidder = f.bidder
        old_ai_status = f.ai_status

        # Re-run Step 7 verification engine
        updated_finding = verify_requirement_for_bidder(db, req, bidder)
        updated_finding.needs_recheck = False

        log_audit_entry(
            db=db,
            finding_id=updated_finding.id,
            who="AI Re-verification Engine",
            what_changed="ai_status",
            old_value=old_ai_status,
            new_value=updated_finding.ai_status,
            reason="Re-evaluated with new clarification submission."
        )
        rechecked.append(updated_finding)

    db.commit()
    return rechecked

