"""
Specification Extraction Engine (Step 4)
Builds:
- Function that reads saved specification pages and extracts:
  - Technical requirements
  - Qualification requirements (QR - strictly by tender headings)
  - Standards, type tests, mandatory documents
- Splits into sections, calls Gemini with Pydantic schema, aggregates and deduplicates.
- For large PDFs (>10 pages): uses sequential processing with inter-page delay to stay
  within Gemini Free Tier RPM limits (15 RPM). Priority pages (GTP/Annexure/Technical)
  are processed first so critical specs are captured even if quota runs low.
"""
import json
import re
import time
from typing import List, Callable, Optional
from sqlalchemy.orm import Session

from db.models import Document, Page, BaselineVersion, Requirement
from reading.ingest import get_document_pages
from ai.client import get_all_clients, MODEL_NAME
from ai.prompts import SPEC_EXTRACTION_PROMPT
from ai.schemas import SpecificationExtractionResult, ExtractedRequirement

# ─────────────────────────────────────────────────────────────────────────────
# Rate-limit configuration
# ─────────────────────────────────────────────────────────────────────────────
# Threshold above which we switch from parallel to sequential processing
LARGE_DOC_THRESHOLD = 10

# Seconds to wait between sequential API calls.
# With 3 API keys pooled: each key sees 1 call per (INTER_PAGE_DELAY * 3) seconds.
# 2.0s delay → each key gets ~1 call every 6s → ~10 calls/min per key → well under 15 RPM.
INTER_PAGE_DELAY = 2.0

# ─────────────────────────────────────────────────────────────────────────────
# Priority keywords — pages containing these are processed FIRST.
# These sections hold the exact technical parameters and GTP tables.
# ─────────────────────────────────────────────────────────────────────────────
PRIORITY_KEYWORDS = [
    "gtp", "guaranteed technical", "annexure", "qualification requirement",
    "technical requirement", "type test", "rated voltage", "rated current",
    "technical parameter", "specific technical", "schedule of requirement",
    "schedule of quantities", "short circuit", "breaking capacity",
    "insulation level", "degree of protection",
]

# ─────────────────────────────────────────────────────────────────────────────
# Skip patterns — pages matching these are purely navigational/boilerplate
# and contain zero extractable requirements → skip them to save API quota.
# ─────────────────────────────────────────────────────────────────────────────
SKIP_PATTERNS = [
    r"^table of contents",
    r"^(?:contents|index)$",
    r"^(?:foreword|preface|preamble)$",
    r"^(?:abbreviations?|acronyms?)$",
    r"^\s*(?:\d+\s+){5,}",          # Pure digit-grid (TOC page numbers)
]


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
                    "response_schema": SpecificationExtractionResult,
                    "temperature": 0.0,
                    "seed": 42
                }
            )
            data = json.loads(response.text)
            result = SpecificationExtractionResult.model_validate(data)
            return result.requirements
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
                time.sleep(2.0)
                continue
            else:
                print(f"Error parsing page {page.page_number}: {e}")
                time.sleep(1.0)
                continue

    return []


def _is_skip_page(text: str) -> bool:
    """Returns True if a page is pure boilerplate (TOC, cover, foreword) with no extractable requirements."""
    lower = text.strip().lower()[:300]   # only check the first 300 chars for speed
    return any(re.search(pat, lower) for pat in SKIP_PATTERNS)


def _is_priority_page(text: str) -> bool:
    """Returns True if the page likely contains GTP/Technical/Annexure content."""
    lower = text.lower()
    return any(kw in lower for kw in PRIORITY_KEYWORDS)


def process_specification_document(
    db: Session,
    tender_id: int,
    specification_document_id: int,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> BaselineVersion:
    """
    Parses all pages of the uploaded specification document,
    extracts requirements, saves them into a BaselineVersion (Version 1).
    Ensures QR items are flagged and ready for the engineer baseline review.

    Args:
        db: SQLAlchemy session.
        tender_id: ID of the tender this document belongs to.
        specification_document_id: ID of the uploaded specification Document.
        progress_callback: Optional callable(current_page, total_pages, extracted_so_far).
            Used by Streamlit UI to show a progress spinner for large PDFs.
    """
    pages = get_document_pages(db, specification_document_id)
    all_extracted: List[ExtractedRequirement] = []

    # ── 1. Stitch sentences across page boundaries ───────────────────────────
    # e.g., Clause 2.3 at the bottom of Page 2 spilling into top of Page 3
    stitched_pages = []
    for i, p in enumerate(pages):
        text = p.text.strip()

        if i > 0 and len(pages[i-1].text.strip()) > 0 and not pages[i-1].text.strip().endswith((".", ":", ";")):
            prev_tail = pages[i-1].text.strip().split("\n")[-1]
            header_clean = re.sub(
                r'^(?:[^\n]*(?:NIT|Specification|Page\s+\d+|BSES)[^\n]*\n*)+', '',
                text, flags=re.IGNORECASE
            ).strip()
            first_line = header_clean.split('\n')[0].strip() if header_clean else ''
            if first_line and not re.match(r'^(?:\d+\.|\([a-z0-9]\)|SECTION)', first_line, re.IGNORECASE):
                text = f"[Continued sentence from previous page: {prev_tail} {first_line}]\n{header_clean}"

        stitched_pages.append((p, text))

    # ── 2. Filter out empty / boilerplate pages ───────────────────────────────
    valid_pages = [
        (p, text) for p, text in stitched_pages
        if len(text.strip()) >= 30 and not _is_skip_page(text)
    ]

    skipped = len(stitched_pages) - len(valid_pages)
    if skipped:
        print(f"[extractor] Skipped {skipped} boilerplate/TOC page(s).")

    # ── 3. Priority ordering for large PDFs ───────────────────────────────────
    # Move GTP / Technical / Annexure pages to the front so that even if the
    # API quota runs out mid-way, the most important specs are captured first.
    is_large = len(valid_pages) > LARGE_DOC_THRESHOLD
    if is_large:
        priority_pages = [(p, t) for p, t in valid_pages if _is_priority_page(t)]
        normal_pages   = [(p, t) for p, t in valid_pages if not _is_priority_page(t)]
        ordered_pages  = priority_pages + normal_pages
        print(
            f"[extractor] Large PDF detected ({len(valid_pages)} pages). "
            f"Priority pages: {len(priority_pages)}, Normal pages: {len(normal_pages)}. "
            f"Using sequential mode with {INTER_PAGE_DELAY}s inter-page delay."
        )
    else:
        ordered_pages = valid_pages

    # ── 4a. SMALL DOC (≤10 pages): original parallel executor ─────────────────
    page_results: dict = {}

    if not is_large:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _process_page(item):
            p, text = item
            return (p.page_number, extract_requirements_from_page(p, custom_text=text))

        max_workers = min(len(ordered_pages), 3) if ordered_pages else 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_page, item): item for item in ordered_pages}
            for future in as_completed(futures):
                try:
                    pg_num, reqs = future.result()
                    page_results[pg_num] = reqs
                except Exception as e:
                    print(f"[extractor] Error extracting page in parallel: {e}")

    # ── 4b. LARGE DOC (>10 pages): sequential with rate-limit pacing ──────────
    else:
        total = len(ordered_pages)
        for idx, (p, text) in enumerate(ordered_pages, start=1):
            print(f"[extractor] Processing page {p.page_number} ({idx}/{total}) …")
            try:
                reqs = extract_requirements_from_page(p, custom_text=text)
                page_results[p.page_number] = reqs
                if progress_callback:
                    progress_callback(idx, total, sum(len(v) for v in page_results.values()))
            except Exception as e:
                print(f"[extractor] Page {p.page_number} failed: {e}")
                page_results[p.page_number] = []

            # Pace API calls: sleep between every page to stay under 15 RPM.
            # Skip the sleep after the very last page.
            if idx < total:
                time.sleep(INTER_PAGE_DELAY)

    # ── 5. Reassemble in original page order ──────────────────────────────────
    for p, _ in valid_pages:
        if p.page_number in page_results:
            all_extracted.extend(page_results[p.page_number])

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
    seen_texts = set()
    unique_reqs = []

    # Patterns for pure headings, lead-in phrases, and boilerplate to exclude
    EXCLUDED_PATTERNS = [
        r"^the following (?:type )?tests shall have been carried out",
        r"^the equipment shall comply with the following (?:technical )?parameters",
        r"^any deviation from the (?:above )?parameters shall be listed",
        r"^a deviation sheet marked nil shall be taken to mean",
        r"^(?:section|annexure|chapter|schedule)\s*[\d\.:\-]+$",
        r"^(?:technical specifications|qualification requirements|scope of work):?$",
    ]

    for r in all_extracted:
        text_clean = (r.text or '').strip()
        # Filter out trivial fragments or empty strings
        if len(text_clean) < 5:
            continue

        # Filter out lead-in sentences and pure section headings
        lower_t = text_clean.lower()
        if any(re.search(pat, lower_t) for pat in EXCLUDED_PATTERNS):
            continue

        # If text ends with a colon and is short (likely a header/lead-in line)
        if text_clean.endswith(":") and len(text_clean.split()) <= 12 and not any(p in lower_t for p in ["voltage:", "current:", "frequency:", "degree:", "rating:"]):
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
            page_number=r.page if hasattr(r, 'page') and r.page else 1,
            is_QR=r.is_qualification_requirement,
            not_applicable=False
        )
        db.add(db_req)

    db.commit()
    db.refresh(baseline)
    return baseline

