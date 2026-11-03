"""
Deliverable endpoints — thin wrapper around outputs/excel_generator.py and
outputs/docx_generator.py, unchanged. These generate a real file on disk
(same as the Streamlit app already does) and stream it back as the HTTP
response, so the frontend's "Download" buttons produce a real file instead
of being visual-only placeholders.
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from api.deps import get_db
from db.repository import get_tender_by_id
from outputs.excel_generator import WorkingExcelGenerator
from outputs.docx_generator import generate_tbe_mom, generate_tbe_report

router = APIRouter(prefix="/tenders/{tender_id}", tags=["deliverables"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/working-excel")
def download_working_excel(tender_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    excel_gen = WorkingExcelGenerator()
    try:
        out_path, _ = excel_gen.generate_working_excel(db, tender)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FileResponse(
        out_path,
        media_type=XLSX_MEDIA_TYPE,
        filename=os.path.basename(out_path),
    )


@router.post("/mom")
def download_mom(tender_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    # No venue/attendees override — uses the function's own sensible
    # defaults, same as the archive-view's re-generation does.
    mom_path = generate_tbe_mom(db, tender)

    return FileResponse(
        mom_path,
        media_type=DOCX_MEDIA_TYPE,
        filename=os.path.basename(mom_path),
    )


@router.post("/ter")
def download_ter(tender_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    ter_path = generate_tbe_report(db, tender)

    return FileResponse(
        ter_path,
        media_type=DOCX_MEDIA_TYPE,
        filename=os.path.basename(ter_path),
    )
