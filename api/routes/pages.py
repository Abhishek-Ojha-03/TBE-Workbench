"""
Page image endpoint — serves the rendered page screenshot
(db/models.py Page.image_path) so the frontend can show the same
"Original Document Preview" next to cited evidence that
ui/review_view.py shows in Streamlit (st.image(page.image_path)).
"""
import os
import mimetypes
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from api.deps import get_db
from db.models import Page

router = APIRouter(prefix="/pages", tags=["pages"])


@router.get("/{page_id}/image")
def get_page_image(page_id: int, db: Session = Depends(get_db)):
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if not page.image_path or not os.path.exists(page.image_path):
        raise HTTPException(status_code=404, detail="Page image not available")

    media_type = mimetypes.guess_type(page.image_path)[0] or "image/jpeg"
    return FileResponse(page.image_path, media_type=media_type)
