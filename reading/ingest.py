"""
PDF Ingestion Pipeline (Step 3)
Rules:
1. Put all page reading in one function: read_page(doc, page_num) -> (text, read_by, image_bytes)
2. Call only that function everywhere else.
3. Read every page ONCE, save text in DB with doc name & page number, and reuse it. Never re-read.
4. If page has almost no text (< 40 chars), treat as scan and call Gemini Vision.
5. Save how the page was read ('PyMuPDF' or 'LLM').
6. For pages read by LLM, save rendered page image for side-by-side engineer verification.
"""
import os
import fitz  # PyMuPDF
from typing import Tuple, List, Optional
from sqlalchemy.orm import Session

from db.models import Document, Page
from db.connection import engine
from ai.client import extract_text_from_image

# Directory for storing rendered scan page images for side-by-side verification
PAGE_IMAGES_DIR = os.path.join("data", "page_images")
os.makedirs(PAGE_IMAGES_DIR, exist_ok=True)

TEXT_THRESHOLD = 40  # Under 40 characters indicates a scanned image/photo/handwritten page


def read_page(pdf_doc: fitz.Document, page_index: int, document_id: int) -> Tuple[str, str, Optional[str]]:
    """
    Reads a single page from a PDF document.
    Returns: (text, read_by, image_path)
    - If digital selectable text >= TEXT_THRESHOLD: uses PyMuPDF (instant, exact).
    - If scanned/image/handwriting: renders page to image and calls Gemini Vision LLM.
    """
    page = pdf_doc[page_index]
    page_num = page_index + 1  # 1-indexed

    # 1. Attempt digital text extraction with PyMuPDF
    raw_text = page.get_text("text").strip()

    # 2. If sufficient text found, return as PyMuPDF
    if len(raw_text) >= TEXT_THRESHOLD:
        return raw_text, "PyMuPDF", None

    # 3. Scanned/image/handwritten: render page to image
    pix = page.get_pixmap(dpi=150)
    image_bytes = pix.tobytes("png")
    
    # Save image for UI side-by-side verification
    image_filename = f"doc_{document_id}_p{page_num}.png"
    image_path = os.path.join(PAGE_IMAGES_DIR, image_filename)
    pix.save(image_path)

    # 4. Call Vision LLM
    extracted_text = extract_text_from_image(image_bytes)
    if not extracted_text:
        extracted_text = raw_text  # Fallback to whatever tiny text was there

    return extracted_text, "LLM", image_path


def ingest_pdf_document(
    db: Session,
    file_bytes: bytes,
    file_name: str,
    document_type: str,
    bidder_id: Optional[int] = None
) -> Document:
    """
    Processes an entire PDF file:
    - Creates a Document record in the database.
    - Iterates page by page calling read_page().
    - Persists every Page record with its text, page_number, read_by, and image_path.
    - Populates the SQLite FTS5 index for rapid keyword retrieval.
    - Guarantees each page is read and stored once.
    """
    # 1. Create Document record
    doc_record = Document(
        bidder_id=bidder_id,
        file_name=file_name,
        document_type=document_type
    )
    db.add(doc_record)
    db.commit()
    db.refresh(doc_record)

    # 2. Open PDF with PyMuPDF
    pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")

    # 3. Read every page once and store
    page_records = []
    fts_rows = []

    for page_idx in range(len(pdf_doc)):
        page_num = page_idx + 1
        text, read_by, img_path = read_page(pdf_doc, page_idx, doc_record.id)

        p = Page(
            document_id=doc_record.id,
            page_number=page_num,
            text=text,
            read_by=read_by,
            image_path=img_path
        )
        db.add(p)
        page_records.append(p)

    db.commit()

    # 4. Index into SQLite FTS5 for fast search
    for p in page_records:
        db.refresh(p)
        with engine.connect() as conn:
            conn.exec_driver_sql(
                "INSERT INTO page_fts (page_id, document_id, page_number, content) VALUES (?, ?, ?, ?)",
                (p.id, doc_record.id, p.page_number, p.text)
            )
            conn.commit()

    pdf_doc.close()
    return doc_record


def get_document_pages(db: Session, document_id: int) -> List[Page]:
    """Retrieves all saved pages for a document from SQLite (never re-reading PDF)."""
    return db.query(Page).filter(Page.document_id == document_id).order_by(Page.page_number.asc()).all()

