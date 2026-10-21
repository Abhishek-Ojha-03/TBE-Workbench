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
from ai.client import get_client, MODEL_NAME
from ai.prompts import SPEC_EXTRACTION_PROMPT
from ai.schemas import SpecificationExtractionResult, ExtractedRequirement


def extract_requirements_from_page(page: Page) -> List[ExtractedRequirement]:
    """Sends a single specification page to Gemini and parses structured requirements."""
    client = get_client()
    if client is None:
        # Fallback heuristic if API is not accessible
        return [
            ExtractedRequirement(
                clause="N/A",
                text=page.text[:200],
                is_qualification_requirement="qualification" in page.text.lower(),
                is_mandatory_document="mandatory" in page.text.lower(),
                standards=[],
                page=page.page_number
            )
        ]

    prompt = SPEC_EXTRACTION_PROMPT.format(page_number=page.page_number, page_text=page.text)

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
        print(f"Error parsing page {page.page_number}: {e}")
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

    for page in pages:
        # Skip pages with virtually no content
        if len(page.text.strip()) < 30:
            continue
        reqs = extract_requirements_from_page(page)
        all_extracted.extend(reqs)

    # 1. Create BaselineVersion 1 in database
    baseline = BaselineVersion(
        tender_id=tender_id,
        version_number=1
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)

    # 2. Deduplicate requirements by text/clause
    seen = set()
    unique_reqs = []
    for r in all_extracted:
        key = (r.clause or "").strip().lower(), r.text.strip().lower()
        if key not in seen:
            seen.add(key)
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

