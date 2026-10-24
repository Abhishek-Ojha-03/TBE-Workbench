"""
Specification Extraction Engine (Step 4)
Builds:
- Function that reads saved specification pages and extracts:
  - Technical requirements
  - Qualification requirements (QR - strictly by tender headings)
  - Standards, type tests, mandatory documents
- Splits into sections, calls Gemini with Pydantic schema, aggregates and deduplicates.
"""
import json
from typing import List
from sqlalchemy.orm import Session

from db.models import Document, Page, BaselineVersion, Requirement
from reading.ingest import get_document_pages
from ai.client import get_all_clients, MODEL_NAME
from ai.prompts import SPEC_EXTRACTION_PROMPT
from ai.schemas import SpecificationExtractionResult, ExtractedRequirement


def extract_requirements_from_page(page: Page, custom_text: str = None) -> List[ExtractedRequirement]:
    """Sends a single specification page to Gemini and parses structured requirements."""
    clients = get_all_clients()
    raw_text = custom_text if custom_text is not None else page.text
    if not clients:
        # Fallback heuristic if API is not accessible
        return [
            ExtractedRequirement(
                clause="N/A",
                text=raw_text[:200],
                is_qualification_requirement="qualification" in raw_text.lower(),
                is_mandatory_document="mandatory" in raw_text.lower(),
                standards=[],
                page=page.page_number
            )
        ]

    prompt = SPEC_EXTRACTION_PROMPT.format(page_number=page.page_number, page_text=raw_text)

    import time
    for client in clients:
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": SpecificationExtractionResult
                }
            )
            data = json.loads(response.text)
            result = SpecificationExtractionResult.model_validate(data)
            return result.requirements
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                time.sleep(1.5)
                continue
            else:
                print(f"Error parsing page {page.page_number}: {e}")
                continue

    return []


def process_specification_document(
    db: Session,
    tender_id: int,
    specification_document_id: int
) -> BaselineVersion:
    """
    Parses all pages of the uploaded specification document,
    extracts requirements, saves them into a BaselineVersion (Version 1).
    Ensures QR items are flagged and ready for the engineer baseline review.
    """
    pages = get_document_pages(db, specification_document_id)
    all_extracted: List[ExtractedRequirement] = []

    # Stitch sentences across page boundaries if a page ends without terminal punctuation
    # e.g., Clause 2.3 at the bottom of Page 2 spilling into top of Page 3 after headers
    import re
    stitched_pages = []
    for i, p in enumerate(pages):
        text = p.text.strip()
        
        # If previous page ended abruptly without period/newline/colon
        if i > 0 and len(pages[i-1].text.strip()) > 0 and not pages[i-1].text.strip().endswith((".", ":", ";")):
            prev_tail = pages[i-1].text.strip().split("\n")[-1]
            # Strip standard running headers on current page so continuation text attaches directly
            header_clean = re.sub(r'^(?:[^\n]*(?:NIT|Specification|Page\s+\d+|BSES)[^\n]*\n*)+', '', text, flags=re.IGNORECASE).strip()
            # If current page starts without a new numbered clause (e.g. starts with lowercase or continuation)
            first_line = header_clean.split('\n')[0].strip() if header_clean else ''
            if first_line and not re.match(r'^(?:\d+\.|\([a-z0-9]\)|SECTION)', first_line, re.IGNORECASE):
                # Attach continuation sentence directly to previous page tail
                text = f"[Continued sentence from previous page: {prev_tail} {first_line}]\n{header_clean}"

        stitched_pages.append((p, text))

    for p, text in stitched_pages:
        # Skip pages with virtually no content
        if len(text.strip()) < 30:
            continue
        reqs = extract_requirements_from_page(p, custom_text=text)
        all_extracted.extend(reqs)

    # 1. Get or create BaselineVersion in database
    existing_b = db.query(BaselineVersion).filter(BaselineVersion.tender_id == tender_id).order_by(BaselineVersion.version_number.desc()).first()
    if existing_b and len(existing_b.requirements) == 0:
        baseline = existing_b
    else:
        v_num = (existing_b.version_number + 1) if existing_b else 1
        baseline = BaselineVersion(
            tender_id=tender_id,
            version_number=v_num
        )
        db.add(baseline)
        db.commit()
        db.refresh(baseline)

    # 2. Deduplicate requirements:
    # A requirement is a duplicate only if:
    # a) Its full normalized text is identical (e.g. document name extracted on two pages)
    # b) Or it is an exact repeat of (clause, text)
    # Never truncate or strip parameter prefixes (e.g. "Rated voltage: 11 kV" vs "Rated frequency: 50 Hz")
    import re
    seen_texts = set()
    unique_reqs = []
    for r in all_extracted:
        text_clean = (r.text or '').strip()
        # Filter out trivial fragments or empty strings
        if len(text_clean) < 5:
            continue
            
        # Normalize text by collapsing extra whitespace and converting to lower
        norm_key = re.sub(r'\s+', ' ', text_clean.lower())
        
        # If clause is given, include clause in key for bullet points/clauses,
        # but if clause is None/empty, match strictly by text
        if norm_key not in seen_texts:
            seen_texts.add(norm_key)
            unique_reqs.append(r)

    # 3. Save requirements: Qualification Requirements (QR) marked according to rules
    for r in unique_reqs:
        db_req = Requirement(
            baseline_version_id=baseline.id,
            clause=r.clause,
            text=r.text,
            is_QR=r.is_qualification_requirement,
            not_applicable=False
        )
        db.add(db_req)

    db.commit()
    db.refresh(baseline)
    return baseline

