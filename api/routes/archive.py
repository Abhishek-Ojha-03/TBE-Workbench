"""
Tender Archive endpoints — read-only summary for a completed tender,
wrapping the same data ui/archive_view.py shows: original specification,
bidder summary (status/price/rank), per-bidder findings + their
submitted documents, plus raw file downloads for both.

Not restricted to tenders with status=="completed" at the API level —
same as ui/archive_view.py, which is only ever navigated to for a
completed tender but doesn't re-check status itself. The frontend route
is what gates this to the Completed Tenders tab.
"""
import csv
import io
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import (
    ArchiveResponse,
    ArchiveDocument,
    ArchiveBidderSummary,
    ArchiveBidderDetail,
    ArchiveFindingRow,
    TenderResponse,
)
from db.models import Bidder, Document, Finding, Evidence
from db.repository import get_tender_by_id
from db.baseline_service import get_latest_baseline, get_baseline_requirements
from db.commercial_service import get_commercial_ranking

router = APIRouter(tags=["archive"])


def _to_archive_document(d: Document) -> ArchiveDocument:
    return ArchiveDocument(
        id=d.id,
        file_name=d.file_name,
        document_type=d.document_type,
        available=bool(d.file_path and os.path.exists(d.file_path)),
    )


@router.get("/tenders/{tender_id}/archive", response_model=ArchiveResponse)
def get_archive(tender_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    bidders = db.query(Bidder).filter(Bidder.tender_id == tender_id).all()
    latest_baseline = get_latest_baseline(db, tender_id)
    requirements = get_baseline_requirements(db, latest_baseline.id) if latest_baseline else []
    req_map = {r.id: r for r in requirements}

    spec_docs = (
        db.query(Document)
        .filter(Document.tender_id == tender_id, Document.bidder_id.is_(None))
        .all()
    )

    ranking = get_commercial_ranking(db, tender_id)
    rank_by_bidder = {r["bidder_id"]: r for r in ranking}

    bidders_summary: List[ArchiveBidderSummary] = []
    bidder_details: List[ArchiveBidderDetail] = []

    for b in bidders:
        rank_info = rank_by_bidder.get(b.id)
        bidders_summary.append(
            ArchiveBidderSummary(
                bidder_id=b.id,
                name=b.name,
                final_status=b.final_status or "Pending",
                quoted_price=b.quoted_price,
                currency=b.price_currency or "INR",
                commercial_rank_label=rank_info["label"] if rank_info else "—",
            )
        )

        findings = db.query(Finding).filter(Finding.bidder_id == b.id).all()
        finding_rows: List[ArchiveFindingRow] = []
        for f in findings:
            req = req_map.get(f.requirement_id)
            evidence = db.query(Evidence).filter(Evidence.finding_id == f.id).first()
            finding_rows.append(
                ArchiveFindingRow(
                    clause=(req.clause if req else None) or "—",
                    requirement_text=(req.text if req else None) or "—",
                    status=f.engineer_status or f.ai_status or "—",
                    offered_value=(evidence.quoted_text if evidence else None) or "—",
                    remark=f.remark or "",
                )
            )

        bidder_docs = db.query(Document).filter(Document.bidder_id == b.id).all()

        bidder_details.append(
            ArchiveBidderDetail(
                bidder_id=b.id,
                name=b.name,
                final_status=b.final_status or "Pending",
                findings=finding_rows,
                documents=[_to_archive_document(d) for d in bidder_docs],
            )
        )

    return ArchiveResponse(
        tender=TenderResponse(
            id=tender.id,
            description=tender.description,
            nit_no=tender.nit_no,
            status=tender.status,
            created_at=tender.created_at,
            bidder_count=len(bidders),
        ),
        spec_documents=[_to_archive_document(d) for d in spec_docs],
        bidders_summary=bidders_summary,
        bidder_details=bidder_details,
    )


@router.get("/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db)):
    """Matches the archive screen's per-file download buttons for the
    original specification and each bidder's submitted documents."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="Original file no longer on disk")

    return FileResponse(doc.file_path, media_type="application/pdf", filename=doc.file_name)


@router.get("/tenders/{tender_id}/bidders/{bidder_id}/archive-findings-csv")
def download_bidder_findings_csv(tender_id: int, bidder_id: int, db: Session = Depends(get_db)):
    """Matches the archive screen's per-bidder 'Download Findings (CSV)' button."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    bidder = db.query(Bidder).filter(Bidder.id == bidder_id, Bidder.tender_id == tender_id).first()
    if not bidder:
        raise HTTPException(status_code=404, detail="Bidder not found")

    latest_baseline = get_latest_baseline(db, tender_id)
    requirements = get_baseline_requirements(db, latest_baseline.id) if latest_baseline else []
    req_map = {r.id: r for r in requirements}

    findings = db.query(Finding).filter(Finding.bidder_id == bidder_id).all()
    rows = []
    for f in findings:
        req = req_map.get(f.requirement_id)
        evidence = db.query(Evidence).filter(Evidence.finding_id == f.id).first()
        rows.append(
            {
                "Clause": (req.clause if req else None) or "—",
                "Requirement": (req.text if req else None) or "—",
                "Status": f.engineer_status or f.ai_status or "—",
                "Bidder Offered (Quote)": (evidence.quoted_text if evidence else None) or "—",
                "Remark": f.remark or "",
            }
        )

    buf = io.StringIO()
    fieldnames = ["Clause", "Requirement", "Status", "Bidder Offered (Quote)", "Remark"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)

    file_name = f"{tender.nit_no}_{bidder.name}_findings.csv".replace(" ", "_")
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )
