"""
Accuracy Benchmark & Audit Matrix endpoint — wraps
db/accuracy_service.py unchanged. Compares AI verdicts against
GROUND_TRUTH_ANSWER_KEY.csv for the synthetic benchmark bidder set;
same scope as ui/accuracy_matrix_view.py.
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import AccuracyMatrixResponse
from db.repository import get_tender_by_id
from db.accuracy_service import compute_accuracy_matrix

router = APIRouter(prefix="/tenders/{tender_id}", tags=["accuracy"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# Same preference order as ui/accuracy_matrix_view.py's download button —
# a static pre-written formal report, not something generated per-tender.
FORMAL_REPORT_CANDIDATES = [
    "TBE_Accuracy_Matrix_Formal_Report.docx",
    "TBE_Accuracy_Matrix_Documentation.docx",
]


@router.get("/accuracy-matrix", response_model=AccuracyMatrixResponse)
def accuracy_matrix(tender_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    result = compute_accuracy_matrix(db, tender)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Ground Truth Answer Key not found in test_data/ — this benchmark view requires the synthetic bidder test set.",
        )

    return AccuracyMatrixResponse(**result)


@router.post("/accuracy-matrix/formal-report")
def download_formal_report(tender_id: int, db: Session = Depends(get_db)):
    """Matches the Accuracy Matrix screen's 'Download Formal Audit Report
    (.docx)' button — serves the pre-written static report, same file
    ui/accuracy_matrix_view.py downloads, named per-tender on the way out."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    report_path = next((p for p in FORMAL_REPORT_CANDIDATES if os.path.exists(p)), None)
    if not report_path:
        raise HTTPException(status_code=404, detail="Formal audit report not found on the server.")

    return FileResponse(
        report_path,
        media_type=DOCX_MEDIA_TYPE,
        filename=f"TBE_50_Bidders_Accuracy_Formal_Report_NIT_{tender.nit_no}.docx",
    )
