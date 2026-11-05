"""
Bidder endpoints — thin wrapper around db/baseline_service.py's
get_bidders_for_tender / add_bidder / delete_bidder, unchanged.

Matches the Requirements & Setup screen's Bidder Setup card.
"""
import os
import io
import zipfile
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import BidderCreateRequest, BidderResponse, BulkZipBidderResponse
from db.repository import get_tender_by_id
from db.baseline_service import get_bidders_for_tender, add_bidder, delete_bidder
from db.storage import storage_enabled, upload_file

router = APIRouter(prefix="/tenders/{tender_id}/bidders", tags=["bidders"])


@router.get("", response_model=List[BidderResponse])
def list_bidders(tender_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    return [BidderResponse.model_validate(b) for b in get_bidders_for_tender(db, tender_id)]


@router.post("", response_model=BidderResponse, status_code=201)
def create_bidder(tender_id: int, payload: BidderCreateRequest, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    try:
        bidder = add_bidder(db, tender_id, payload.name)
    except ValueError as e:
        # Duplicate name / empty name — same validation already enforced
        # in db/baseline_service.py, surfaced here as a proper HTTP error.
        raise HTTPException(status_code=409, detail=str(e))
    return BidderResponse.model_validate(bidder)


@router.delete("/{bidder_id}", status_code=204)
def remove_bidder(tender_id: int, bidder_id: int, db: Session = Depends(get_db)):
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    delete_bidder(db, bidder_id)
    return None


@router.post("/bulk-zip", response_model=BulkZipBidderResponse)
async def bulk_add_bidders_from_zip(
    tender_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    """
    Matches ui/baseline_view.py's "Add Bidders from ZIP" feature EXACTLY:
    each top-level folder containing PDFs becomes a bidder (named after the
    folder), and the ZIP itself is saved to data/bidder_zips/ so the
    TBE Working Excel screen can later reuse it for document ingestion
    without asking for a second upload — same reasoning as the Streamlit
    version: bidder names and folder names come from the same source, so
    there's never a name-matching problem between the two screens.
    """
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are accepted")

    zip_bytes = await file.read()

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not open ZIP: {e}")

    folder_names = set()
    for name in zf.namelist():
        parts = [p for p in name.replace("\\", "/").split("/") if p]
        if len(parts) >= 2 and parts[-1].lower().endswith(".pdf"):
            folder_names.add(parts[-2])
    zf.close()

    if not folder_names:
        raise HTTPException(status_code=400, detail="No PDF files found inside sub-folders in the ZIP.")

    added: List[str] = []
    skipped: List[str] = []
    for folder_name in sorted(folder_names):
        try:
            add_bidder(db, tender_id, folder_name)
            added.append(folder_name)
        except ValueError:
            skipped.append(folder_name)

    # Save the ZIP so Working Excel can reuse it directly — same path
    # convention the Streamlit app already uses, so either UI can pick it
    # up. On a host with no persistent disk (e.g. Render free tier), save
    # to Supabase Storage instead so it survives a restart.
    zip_filename = f"tender_{tender_id}_bidders.zip"
    saved_to_storage = storage_enabled() and upload_file(zip_bytes, f"bidder_zips/{zip_filename}", "application/zip")
    if not saved_to_storage:
        zip_dir = os.path.join("data", "bidder_zips")
        os.makedirs(zip_dir, exist_ok=True)
        with open(os.path.join(zip_dir, zip_filename), "wb") as f:
            f.write(zip_bytes)

    return BulkZipBidderResponse(added=added, skipped=skipped)
