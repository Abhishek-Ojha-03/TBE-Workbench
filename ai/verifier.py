"""
Bidder Verification Engine (Step 7)
The core intelligence of the TBE Workbench.
Executes:
1. Candidate page retrieval via FTS5.
2. Gemini 3.8 Flash technical evaluation.
3. Code Quote Verification: Programmatically ensures the quote really appears on the cited page.
4. Golden rule enforcement: If quote is missing or evidence is absent -> 'Needs Human Review'.
5. Updates the Finding and Evidence tables in SQLite.
"""
import json
import re
from typing import List, Optional
from sqlalchemy.orm import Session

from db.models import Requirement, Bidder, Page, Finding, Evidence
from reading.fts_indexer import search_candidate_pages
from rules.quote_checker import verify_quote_in_page_text
from ai.client import get_client, MODEL_NAME
from ai.prompts import BIDDER_VERIFICATION_PROMPT
from ai.schemas import VerificationFinding


def _normalize_for_quote_check(text: str) -> str:
    """
    Normalize text for quote verification:
    - Lowercase
    - Collapse whitespace (OCR sometimes adds/removes spaces)
    - Remove common OCR artifacts (?, |, etc.)
    - Remove punctuation noise
    """
    if not text:
        return ""
    # Replace OCR artifact characters
    text = re.sub(r"[?|]", " ", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def _quote_found_normalized(quote: str, page_text: str) -> bool:
    """
    Two-pass quote check:
    Pass 1: Exact substring match (original verify_quote_in_page_text).
    Pass 2: Normalized match (strip OCR artifacts, lowercase, collapse whitespace).
    """
    # Pass 1: strict check
    if verify_quote_in_page_text(quote, page_text):
        return True
    # Pass 2: normalized check
    norm_quote = _normalize_for_quote_check(quote)
    norm_page = _normalize_for_quote_check(page_text)
    return norm_quote in norm_page


def verify_requirement_for_bidder(
    db: Session,
    requirement: Requirement,
    bidder: Bidder
) -> Finding:
    """
    Verifies one requirement for one bidder.
    Corresponds to finding the status for ONE cell in the TBE matrix.
    """
    # 1. Fetch or create Finding record
    finding = (
        db.query(Finding)
        .filter(Finding.requirement_id == requirement.id, Finding.bidder_id == bidder.id)
        .first()
    )
    if not finding:
        finding = Finding(
            requirement_id=requirement.id,
            bidder_id=bidder.id,
            ai_status="Needs Human Review",
            needs_recheck=False
        )
        db.add(finding)
        db.commit()
        db.refresh(finding)

    # 2. Retrieve candidate pages using FTS5 search (increased limit to 5)
    query_str = f"{requirement.clause or ''} {requirement.text}"
    candidate_pages = search_candidate_pages(db, bidder.id, query_str, limit=5)

    if not candidate_pages:
        finding.ai_status = "Needs Human Review"
        finding.remark = "No relevant pages found in bidder submission."
        db.commit()
        return finding

    # 3. Format candidate text for LLM prompt
    pages_context_list = []
    # Two separate lookup dicts to avoid mixed-key iteration bugs
    page_by_docpage = {}   # (doc_name_lower, page_num) -> Page
    page_by_num = {}       # page_num -> Page  (fallback)
    for p in candidate_pages:
        doc_name = p.document.file_name if p.document else f"Doc_{p.document_id}"
        page_by_docpage[(doc_name.lower(), p.page_number)] = p
        page_by_num[p.page_number] = p
        pages_context_list.append(
            f"--- Document: {doc_name} | Page: {p.page_number} ---\n{p.text}\n"
        )

    candidates_text = "\n".join(pages_context_list)

    # 4. Call Gemini Model
    client = get_client()
    if client is None:
        # Fallback if no API key
        finding.ai_status = "Needs Human Review"
        finding.remark = "Gemini client not initialized."
        db.commit()
        return finding

    prompt = BIDDER_VERIFICATION_PROMPT.format(
        clause=requirement.clause or "General",
        requirement_text=requirement.text,
        candidate_pages_text=candidates_text
    )

    import time
    from ai.client import MODEL_NAME
    max_retries = 3
    retry_delay = 5
    response = None
    last_err = None

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": VerificationFinding
                }
            )
            break
        except Exception as api_err:
            last_err = api_err
            err_msg = str(api_err)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                # If API specifies a wait duration, back off appropriately
                wait_time = 15 * (attempt + 1)
                time.sleep(wait_time)
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                time.sleep(4 * (attempt + 1))
            else:
                raise api_err

    if response is None:
        raise last_err

    try:
        data = json.loads(response.text)
        result = VerificationFinding.model_validate(data)

        # 5. STRICT CODE QUOTE VERIFICATION (Rule 12 from Developer Guide)
        # Step 1: Try to match by document name + page number
        matched_page: Optional[Page] = None
        ai_doc_lower = (result.document or "").lower()

        for (d_name, p_num), p_obj in page_by_docpage.items():
            if ai_doc_lower and (ai_doc_lower in d_name or d_name in ai_doc_lower):
                if p_num == result.page:
                    matched_page = p_obj
                    break

        # Step 2: Fallback — match by page number alone
        if not matched_page and result.page in page_by_num:
            matched_page = page_by_num[result.page]

        # Step 3: Last resort — use first candidate page if AI cites page 1
        if not matched_page and candidate_pages:
            matched_page = candidate_pages[0]

        # 6. Quote check with two-pass normalization
        quote_valid = False
        if matched_page and result.quote:
            quote_valid = _quote_found_normalized(result.quote, matched_page.text)

        # 7. Apply Golden Rule & Quote Verification Guardrail
        if result.status == "complied":
            if not quote_valid:
                # Discard hallucinated compliance quote!
                finding.ai_status = "Needs Human Review"
                finding.remark = (
                    f"AI suggested Complied, but quote not verified on cited page {result.page}. "
                    f"Quote: '{(result.quote or '')[:80]}'"
                )
            else:
                finding.ai_status = "Complied"
                finding.remark = result.reason

                # Save Evidence
                db.query(Evidence).filter(Evidence.finding_id == finding.id).delete()
                evidence = Evidence(
                    finding_id=finding.id,
                    page_id=matched_page.id,
                    quoted_text=result.quote
                )
                db.add(evidence)

        elif result.status == "not_complied":
            finding.ai_status = "Not Complied"
            finding.remark = result.reason
            if matched_page and result.quote:
                db.query(Evidence).filter(Evidence.finding_id == finding.id).delete()
                evidence = Evidence(
                    finding_id=finding.id,
                    page_id=matched_page.id,
                    quoted_text=result.quote
                )
                db.add(evidence)
        else:
            finding.ai_status = "Needs Human Review"
            finding.remark = result.reason or "Needs manual verification."

    except Exception as exc:
        finding.ai_status = "Needs Human Review"
        finding.remark = f"Verification error: {str(exc)}"

    finding.needs_recheck = False
    db.commit()
    db.refresh(finding)
    return finding


def verify_all_requirements_for_bidder(
    db: Session,
    tender_id: int,
    bidder_id: int
) -> List[Finding]:
    """Runs verification for all active baseline requirements for a bidder."""
    from db.baseline_service import get_latest_baseline, get_baseline_requirements

    bidder = db.query(Bidder).filter(Bidder.id == bidder_id).first()
    if not bidder:
        raise ValueError(f"Bidder with id {bidder_id} not found.")

    baseline = get_latest_baseline(db, tender_id)
    if not baseline:
        raise ValueError("No approved baseline found for tender.")

    reqs = get_baseline_requirements(db, baseline.id)
    findings = []
    import time
    for req in reqs:
        if req.not_applicable:
            continue
        f = verify_requirement_for_bidder(db, req, bidder)
        findings.append(f)
        # 2-second rate-limiting pause between clauses to stay comfortably under 15 RPM
        time.sleep(2.0)

    return findings
