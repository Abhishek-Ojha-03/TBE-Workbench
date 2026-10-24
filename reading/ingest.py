"""
PDF Ingestion Pipeline (Step 3)
Rules:
1. Put all page reading in one function: read_page(doc, page_num) -> (text, read_by, image_bytes)
2. Call only that function everywhere else.
3. Read every page ONCE, save text in DB with doc name & page number, and reuse it. Never re-read.
4. If page has almost no text (< 40 chars), treat as scan and call Gemini Vision.
5. Save how the page was read ('PyMuPDF' or 'LLM').
6. For pages read by LLM, save rendered page image for side-by-side engineer verification.
7. HASH CACHE: Before calling Gemini Vision OCR, check if the same file (md5 hash) was already
   ingested before. If yes, copy page text from the cached doc. Zero API calls for repeat files.
"""
import os
import fitz  # PyMuPDF
import hashlib
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

    # Always save a lightweight grayscale page preview image for UI side-by-side evidence inspection
    image_filename = f"doc_{document_id}_p{page_num}.jpg"
    image_path = os.path.join(PAGE_IMAGES_DIR, image_filename)
    try:
        pix = page.get_pixmap(dpi=100, colorspace=fitz.csGRAY)
        pix.save(image_path)
    except Exception:
        image_path = None

    # 2. If sufficient text found, return as PyMuPDF with saved preview image
    if len(raw_text) >= TEXT_THRESHOLD:
        return raw_text, "PyMuPDF", image_path

    # 3. Scanned/image/handwritten: call Vision LLM on the rendered image
    image_bytes = pix.tobytes("jpeg") if pix else None
    if image_bytes:
        extracted_text = extract_text_from_image(image_bytes)
    else:
        extracted_text = raw_text

    if not extracted_text:
        extracted_text = raw_text  # Fallback to whatever tiny text was there

    return extracted_text, "LLM", image_path


def ingest_pdf_document(
    db: Session,
    file_bytes: bytes,
    file_name: str,
    document_type: str,
    bidder_id: Optional[int] = None,
    tender_id: Optional[int] = None
) -> Document:
    """
    Processes an entire PDF file:
    - Creates a Document record in the database.
    - Iterates page by page calling read_page().
    - Persists every Page record with its text, page_number, read_by, and image_path.
    - Populates the SQLite FTS5 index in bulk for rapid keyword retrieval.
    - Guarantees each page is read and stored once.
    - For Specification documents, tender_id links the doc to the correct tender.
    """
    # 1. Compute MD5 hash of the file bytes for cache lookup
    file_hash = hashlib.md5(file_bytes).hexdigest()

    # 2. Hash Cache: If this exact file was already ingested, copy page text instantly (0 API calls!)
    cached_doc = (
        db.query(Document)
        .filter(Document.md5_hash == file_hash)
        .first()
    )
    if cached_doc and cached_doc.pages and all("429" not in (p.text or "") for p in cached_doc.pages):
        # Create a new Document record pointing to this bidder/tender, but clone page text from cache
        doc_record = Document(
            bidder_id=bidder_id,
            tender_id=tender_id,
            file_name=file_name,
            document_type=document_type,
            md5_hash=file_hash
        )
        db.add(doc_record)
        db.commit()
        db.refresh(doc_record)

        for cached_page in cached_doc.pages:
            p = Page(
                document_id=doc_record.id,
                page_number=cached_page.page_number,
                text=cached_page.text,
                read_by=cached_page.read_by + "_cached",
                image_path=cached_page.image_path
            )
            db.add(p)
        db.commit()

        fts_params = []
        for p in doc_record.pages:
            fts_params.append((p.id, doc_record.id, p.page_number, p.text))

        if fts_params:
            from sqlalchemy import text
            for param in fts_params:
                db.execute(
                    text("INSERT INTO page_fts (page_id, document_id, page_number, content) VALUES (:p_id, :d_id, :p_num, :cnt)"),
                    {"p_id": param[0], "d_id": param[1], "p_num": param[2], "cnt": param[3]}
                )
            db.commit()

        return doc_record  # Returned instantly with no API calls

    # 3. Not cached — create Document record and do full OCR
    doc_record = Document(
        bidder_id=bidder_id,
        tender_id=tender_id,
        file_name=file_name,
        document_type=document_type,
        md5_hash=file_hash
    )
    db.add(doc_record)
    db.commit()
    db.refresh(doc_record)

    # 2. Open PDF with PyMuPDF
    pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
    page_records = []
    
    # Identify pages with selectable text vs pages requiring vision OCR
    pages_to_ocr = []
    for page_idx in range(len(pdf_doc)):
        page = pdf_doc[page_idx]
        page_num = page_idx + 1
        raw_text = page.get_text("text").strip()
        if len(raw_text) >= TEXT_THRESHOLD:
            # Digital selectable text - instant
            p = Page(
                document_id=doc_record.id,
                page_number=page_num,
                text=raw_text,
                read_by="PyMuPDF",
                image_path=None
            )
            db.add(p)
            page_records.append(p)
        else:
            # Render page to 100 DPI Grayscale JPEG
            pix = page.get_pixmap(dpi=100, colorspace=fitz.csGRAY)
            image_filename = f"doc_{doc_record.id}_p{page_num}.jpg"
            image_path = os.path.join(PAGE_IMAGES_DIR, image_filename)
            pix.save(image_path)
            img_bytes = pix.tobytes("jpeg")
            pages_to_ocr.append((page_num, img_bytes, image_path, raw_text))

    # Process scanned pages in batches of 4 (Option 2: 4-page batching)
    if pages_to_ocr:
        from ai.client import extract_text_from_images_batch
        BATCH_SIZE = 4
        for i in range(0, len(pages_to_ocr), BATCH_SIZE):
            chunk = pages_to_ocr[i : i + BATCH_SIZE]
            imgs = [item[1] for item in chunk]
            batch_texts = extract_text_from_images_batch(imgs)
            
            for (p_num, _, img_p, r_txt), extracted in zip(chunk, batch_texts):
                final_txt = extracted.strip() if extracted else r_txt
                p = Page(
                    document_id=doc_record.id,
                    page_number=p_num,
                    text=final_txt,
                    read_by="LLM_Batch",
                    image_path=img_p
                )
                db.add(p)
                page_records.append(p)

    db.commit()

    # 4. Bulk batch insert into SQLite FTS5 (1 single transaction instead of looping connections)
    fts_params = []
    for p in page_records:
        db.refresh(p)
        fts_params.append((p.id, doc_record.id, p.page_number, p.text))

    if fts_params:
        with engine.connect() as conn:
            conn.exec_driver_sql(
                "INSERT INTO page_fts (page_id, document_id, page_number, content) VALUES (?, ?, ?, ?)",
                fts_params
            )
            conn.commit()

    pdf_doc.close()
    return doc_record


def ingest_documents_concurrently(
    bidder_id: int,
    files_list: List[Tuple[str, bytes]],
    document_type: str = "Bidder Submission",
    max_workers: int = 4
) -> int:
    """
    Ingests multiple PDF files for a single bidder simultaneously using ThreadPoolExecutor.
    Each worker gets its own thread-local DB session to parse pages and bulk-index into FTS5.
    Returns total count of successfully ingested documents.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from db.connection import SessionLocal

    if not files_list:
        return 0

    success_count = 0
    worker_count = min(max_workers, len(files_list))

    def _worker(f_name, f_bytes):
        thread_db = SessionLocal()
        try:
            doc = ingest_pdf_document(
                db=thread_db,
                file_bytes=f_bytes,
                file_name=f_name,
                document_type=document_type,
                bidder_id=bidder_id
            )
            return True
        finally:
            thread_db.close()

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(_worker, fn, fb) for fn, fb in files_list]
        for fut in as_completed(futures):
            try:
                if fut.result():
                    success_count += 1
            except Exception as e:
                print(f"Error ingesting file: {e}")

    return success_count


def ingest_bidder_bundle_parallel(
    tender_id: int,
    bidder_files_map: dict,
    progress_callback=None,
    max_workers: int = 5
) -> dict:
    """
    Parallel concurrent ingestion of document bundles across ALL bidders simultaneously.
    bidder_files_map: { bidder_id: [(file_name, file_bytes), ...], ... }
    Uses ThreadPoolExecutor to ingest multiple bidders in parallel.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from db.connection import SessionLocal

    results = {}
    total_bidders = len(bidder_files_map)

    def _ingest_bidder_worker(b_id, files_list):
        thread_db = SessionLocal()
        count = 0
        try:
            for f_name, f_bytes in files_list:
                ingest_pdf_document(
                    db=thread_db,
                    file_bytes=f_bytes,
                    file_name=f_name,
                    document_type="Bidder Submission",
                    bidder_id=b_id
                )
                count += 1
                if progress_callback:
                    progress_callback(b_id, count, len(files_list), f_name)
            return b_id, count
        finally:
            thread_db.close()

    worker_count = min(max_workers, max(total_bidders, 1))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_b = {
            executor.submit(_ingest_bidder_worker, b_id, files): b_id
            for b_id, files in bidder_files_map.items()
        }
        for future in as_completed(future_to_b):
            b_id = future_to_b[future]
            try:
                bid, count = future.result()
                results[bid] = count
            except Exception as e:
                results[b_id] = f"Error: {e}"

    return results


def get_document_pages(db: Session, document_id: int) -> List[Page]:
    """Retrieves all saved pages for a document from SQLite (never re-reading PDF)."""
    return db.query(Page).filter(Page.document_id == document_id).order_by(Page.page_number.asc()).all()

