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
from typing import List, Optional, Dict
from sqlalchemy.orm import Session

from db.models import Requirement, Bidder, Page, Finding, Evidence
from reading.fts_indexer import search_candidate_pages
from rules.quote_checker import verify_quote_in_page_text
from ai.client import get_client, MODEL_NAME
from ai.prompts import BIDDER_VERIFICATION_PROMPT, BATCH_BIDDER_VERIFICATION_PROMPT
from ai.schemas import VerificationFinding, BatchVerificationResult


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
                    "response_schema": VerificationFinding,
                    "temperature": 0.0  # Deterministic: same data always gives same result
                }
            )
            break
        except Exception as api_err:
            last_err = api_err
            err_msg = str(api_err)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                # Quota backoff
                wait_time = 15 * (attempt + 1)
                time.sleep(wait_time)
            elif "500" in err_msg or "503" in err_msg or "UNAVAILABLE" in err_msg or "INTERNAL" in err_msg:
                # Transient Google server error: retry after brief backoff
                time.sleep(2 * (attempt + 1))
            else:
                raise api_err

    if response is None:
        finding.ai_status = "Needs Human Review"
        finding.remark = f"AI service temporarily unavailable (Server error 500/503): {str(last_err)}"
        db.commit()
        db.refresh(finding)
        return finding

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

        # 6. Quote check with 3-tier cascade and candidate page fallback
        quote_valid = False
        if matched_page and result.quote:
            quote_valid = _quote_found_normalized(result.quote, matched_page.text)
        
        # Candidate fallback: if AI cited wrong page number, scan candidate pages
        if not quote_valid and result.quote and candidate_pages:
            for cand_p in candidate_pages:
                if _quote_found_normalized(result.quote, cand_p.text):
                    matched_page = cand_p
                    quote_valid = True
                    break

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


def verify_requirements_batch_for_bidder(
    db: Session,
    requirements: List[Requirement],
    bidder: Bidder
) -> List[Finding]:
    """
    Evaluates a batch of requirements (typically 5-8 related items) for ONE bidder
    in a SINGLE LLM prompt call. Slashes total API latency by 4x-5x while preserving
    strict quote verification guardrails and evidence mapping.
    """
    if not requirements:
        return []

    # 1. Retrieve candidate pages across all requirements in this batch via FTS5
    all_candidate_pages: List[Page] = []
    seen_page_ids = set()
    page_by_docpage: Dict[tuple, Page] = {}
    page_by_num: Dict[int, Page] = {}

    for req in requirements:
        pages = search_candidate_pages(db, bidder.id, req.text, limit=3)
        for p in pages:
            if p.id not in seen_page_ids:
                seen_page_ids.add(p.id)
                all_candidate_pages.append(p)
                doc_name = p.document.file_name if p.document else f"doc_{p.document_id}"
                page_by_docpage[(doc_name.lower(), p.page_number)] = p
                page_by_num[p.page_number] = p

    # Format candidate pages text context
    pages_context_list = []
    for p in all_candidate_pages:
        doc_name = p.document.file_name if p.document else f"doc_{p.document_id}"
        pages_context_list.append(
            f"--- Document: {doc_name} | Page: {p.page_number} ---\n{p.text}\n"
        )
    candidates_text = "\n".join(pages_context_list)

    # 2. Get or create findings for each requirement
    findings_map: Dict[str, Finding] = {}
    req_by_tag: Dict[str, Requirement] = {}
    req_batch_lines = []

    for i, req in enumerate(requirements):
        tag = f"REQ-{i+1}"
        req_by_tag[tag] = req
        req_batch_lines.append(f"[{tag}] Clause: {req.clause or 'General'} -> \"{req.text}\"")

        # Database finding record
        f = db.query(Finding).filter(
            Finding.bidder_id == bidder.id,
            Finding.requirement_id == req.id
        ).first()
        if not f:
            f = Finding(
                bidder_id=bidder.id,
                requirement_id=req.id,
                ai_status="Pending",
                needs_recheck=False
            )
            db.add(f)
        findings_map[tag] = f

    # Commit initial creation quickly so transaction lock is released immediately
    db.commit()
    for tag, f in findings_map.items():
        db.refresh(f)

    # If no candidate pages at all, mark all as Needs Human Review
    if not all_candidate_pages:
        for tag, finding in findings_map.items():
            finding.ai_status = "Needs Human Review"
            finding.remark = "No relevant documents found in bidder submission."
            finding.needs_recheck = False
        db.commit()
        return list(findings_map.values())

    # 3. Call Gemini Model with batch schema
    client = get_client()
    if client is None:
        for tag, finding in findings_map.items():
            finding.ai_status = "Needs Human Review"
            finding.remark = "Gemini client not initialized."
            finding.needs_recheck = False
        db.commit()
        return list(findings_map.values())

    prompt = BATCH_BIDDER_VERIFICATION_PROMPT.format(
        num_requirements=len(requirements),
        requirements_batch_text="\n".join(req_batch_lines),
        candidate_pages_text=candidates_text
    )

    import time
    from ai.client import MODEL_NAME, get_all_clients
    clients_pool = get_all_clients() or ([client] if client else [])
    response = None
    last_err = None

    for active_client in clients_pool:
        # Skip clients that are already known to be exhausted for the day
        if getattr(active_client, "_daily_exhausted", False):
            continue

        for attempt in range(2):
            try:
                response = active_client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": BatchVerificationResult,
                        "temperature": 0.0  # Deterministic: same data always gives same result
                    }
                )
                break
            except Exception as api_err:
                last_err = api_err
                err_msg = str(api_err)
                if "per day limit exceeded" in err_msg or "daily" in err_msg.lower():
                    # Flag this client as permanently daily exhausted so we don't retry it
                    setattr(active_client, "_daily_exhausted", True)
                    break
                elif "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    # Momentary rate limit (RPM); brief backoff
                    time.sleep(2.5)
                    break
                elif "500" in err_msg or "503" in err_msg or "UNAVAILABLE" in err_msg:
                    time.sleep(1 * (attempt + 1))
                else:
                    raise api_err
        if response is not None:
            break

    # If first pass across all keys hit temporary 429 burst, give one final cooldown attempt on healthy keys
    if response is None and last_err and ("429" in str(last_err) or "RESOURCE_EXHAUSTED" in str(last_err)):
        time.sleep(3)
        for active_client in clients_pool:
            if getattr(active_client, "_daily_exhausted", False):
                continue
            try:
                response = active_client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": BatchVerificationResult,
                        "temperature": 0.0
                    }
                )
                if response is not None:
                    break
            except Exception as retry_err:
                last_err = retry_err

    if response is None:
        for tag, finding in findings_map.items():
            finding.ai_status = "Needs Human Review"
            finding.remark = f"AI service temporarily unavailable: {str(last_err)}"
            finding.needs_recheck = False
        db.commit()
        return list(findings_map.values())

    # 4. Parse batch evaluations and apply strict quote verification guardrails
    evaluations_dict: Dict[str, VerificationFinding] = {}
    try:
        data = json.loads(response.text)
        batch_res = BatchVerificationResult.model_validate(data)
        for ev in batch_res.evaluations:
            # Map by tag (REQ-1, REQ-2) or by clause
            c_id = (ev.clause_id or "").strip()
            evaluations_dict[c_id] = ev
    except Exception as parse_err:
        print(f"Error parsing batch response: {parse_err}")

    for tag, req in req_by_tag.items():
        finding = findings_map[tag]
        # Match evaluation by tag, clause, or fallback
        ev = evaluations_dict.get(tag) or evaluations_dict.get(req.clause or "")
        if not ev:
            # Try fuzzy match on tag inside clause_id
            for k, val in evaluations_dict.items():
                if tag in k or (req.clause and req.clause in k):
                    ev = val
                    break

        if not ev:
            finding.ai_status = "Needs Human Review"
            finding.remark = "AI did not return specific verdict for this clause in batch."
            finding.needs_recheck = False
            continue

        # Step 1: Resolve matched page
        matched_page: Optional[Page] = None
        ai_doc_lower = (ev.document or "").lower()

        for (d_name, p_num), p_obj in page_by_docpage.items():
            if ai_doc_lower and (ai_doc_lower in d_name or d_name in ai_doc_lower):
                if p_num == ev.page:
                    matched_page = p_obj
                    break

        if not matched_page and ev.page in page_by_num:
            matched_page = page_by_num[ev.page]
        if not matched_page and all_candidate_pages:
            matched_page = all_candidate_pages[0]

        # Step 2: Quote verification check (3-Tier Cascade)
        quote_valid = False
        if matched_page and ev.quote:
            quote_valid = _quote_found_normalized(ev.quote, matched_page.text)

        # Candidate fallback: if AI cited wrong doc/page number, scan all candidate pages
        if not quote_valid and ev.quote and all_candidate_pages:
            for cand_p in all_candidate_pages:
                if _quote_found_normalized(ev.quote, cand_p.text):
                    matched_page = cand_p
                    quote_valid = True
                    break

        # Step 3: Apply verdict guardrails
        if ev.status == "complied":
            if not quote_valid:
                finding.ai_status = "Needs Human Review"
                finding.remark = f"AI suggested Complied, but quote not verified on cited page {ev.page}."
            else:
                finding.ai_status = "Complied"
                finding.remark = ev.reason
                db.query(Evidence).filter(Evidence.finding_id == finding.id).delete()
                evidence = Evidence(
                    finding_id=finding.id,
                    page_id=matched_page.id,
                    quoted_text=ev.quote
                )
                db.add(evidence)
        elif ev.status == "not_complied":
            finding.ai_status = "Not Complied"
            finding.remark = ev.reason
            if matched_page and ev.quote:
                db.query(Evidence).filter(Evidence.finding_id == finding.id).delete()
                evidence = Evidence(
                    finding_id=finding.id,
                    page_id=matched_page.id,
                    quoted_text=ev.quote
                )
                db.add(evidence)
        else:
            finding.ai_status = "Needs Human Review"
            finding.remark = ev.reason or "Needs manual verification."

        finding.needs_recheck = False

    db.commit()
    for f in findings_map.values():
        db.refresh(f)

    return list(findings_map.values())


def verify_all_requirements_for_bidder(
    db: Session,
    tender_id: int,
    bidder_id: int,
    progress_callback=None
) -> List[Finding]:
    """
    Runs high-speed batch verification for all active baseline requirements for a bidder.
    Groups requirements into logical batches of 5-6 items, reducing 24 sequential calls
    down to ~4 rapid batch calls.
    """
    from db.baseline_service import get_latest_baseline, get_baseline_requirements

    bidder = db.query(Bidder).filter(Bidder.id == bidder_id).first()
    if not bidder:
        raise ValueError(f"Bidder with id {bidder_id} not found.")

    baseline = get_latest_baseline(db, tender_id)
    if not baseline:
        raise ValueError("No approved baseline found for tender.")

    reqs = get_baseline_requirements(db, baseline.id)
    active_reqs = [r for r in reqs if not r.not_applicable]
    findings = []
    
    # Split into chunks of 6 requirements per batch call
    BATCH_SIZE = 6
    total_active = len(active_reqs)
    
    for b_start in range(0, total_active, BATCH_SIZE):
        batch = active_reqs[b_start : b_start + BATCH_SIZE]
        batch_findings = verify_requirements_batch_for_bidder(db, batch, bidder)
        findings.extend(batch_findings)
        
        if progress_callback:
            curr_done = min(b_start + len(batch), total_active)
            last_clause = batch[-1].clause or f"Item {curr_done}"
            progress_callback(curr_done, total_active, last_clause)

        # Brief pacing delay to stay safely under Gemini 15 RPM per-minute burst limit
        if b_start + BATCH_SIZE < total_active:
            import time
            time.sleep(1.5)

    return findings



def verify_all_bidders(
    db: Session,
    tender_id: int,
    progress_callback=None,
    max_workers: int = 5
) -> Dict[int, str]:
    """
    Evaluates ALL bidders for the tender concurrently using ThreadPoolExecutor.
    Multiple bidders evaluate simultaneously across worker threads.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from db.connection import SessionLocal
    from db.baseline_service import get_bidders_for_tender
    from rules.rule_engine import update_bidder_qualification_status

    bidders = get_bidders_for_tender(db, tender_id)
    results = {}
    total_bidders = len(bidders)

    if not bidders:
        return results

    completed_count = 0

    def _worker_task(b_id, b_name):
        # Create thread-local session to ensure thread safety
        thread_db = SessionLocal()
        try:
            def _local_progress(cur, tot, clause):
                if progress_callback:
                    progress_callback(b_name, cur, tot, clause)

            verify_all_requirements_for_bidder(thread_db, tender_id, b_id, progress_callback=_local_progress)
            status = update_bidder_qualification_status(thread_db, b_id)
            return b_id, status
        finally:
            thread_db.close()

    # Launch parallel threads
    worker_count = min(max_workers, total_bidders)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_bidder = {
            executor.submit(_worker_task, b.id, b.name): b for b in bidders
        }
        for future in as_completed(future_to_bidder):
            b = future_to_bidder[future]
            completed_count += 1
            try:
                bid, st_res = future.result()
                results[bid] = st_res
                if progress_callback:
                    progress_callback(b.name, 100, 100, f"Completed ({completed_count}/{total_bidders} bidders)")
            except Exception as e:
                results[b.id] = f"Error: {str(e)}"

    return results
