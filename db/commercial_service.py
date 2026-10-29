"""
Commercial Evaluation Service (Part 2 — Price Bid Opening).

Rules (Two-Envelope System):
- Price data is NEVER shown in the Technical (Part 1) screens.
- Only technically QUALIFIED bidders participate in Part 2.
- AI extracts quoted price from bidder documents (price schedule, commercial offer, quotation, etc.).
- If price is not mentioned, status is clearly recorded as "Price Not Mentioned".
- L1 = lowest price, L2 = second lowest, etc.
- If two bidders quote the same price, both receive the same rank and the tie is flagged.
"""
import re
import json
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from db.models import Bidder, Document, Page
from ai.client import get_client, MODEL_NAME


def get_qualified_bidders(db: Session, tender_id: int) -> List[Bidder]:
    """Return only technically Qualified bidders for this tender."""
    return (
        db.query(Bidder)
        .filter(Bidder.tender_id == tender_id, Bidder.final_status == "Qualified")
        .order_by(Bidder.name)
        .all()
    )


def save_price_for_bidder(
    db: Session,
    bidder_id: int,
    price: Optional[float],
    currency: str = "INR",
) -> Bidder:
    """Persist a bidder's quoted price and currency."""
    bidder = db.query(Bidder).filter(Bidder.id == bidder_id).first()
    if not bidder:
        raise ValueError(f"Bidder ID {bidder_id} not found.")
    bidder.quoted_price = price
    bidder.price_currency = currency
    db.commit()
    db.refresh(bidder)
    return bidder


def extract_bidder_price_with_ai(db: Session, bidder: Bidder) -> Tuple[Optional[float], str, str]:
    """
    Scans the bidder's documents to extract the commercial quoted price / bid amount.
    Returns:
        (price_float_or_None, currency_str, evidence_or_reason)
    If no price is found in the documents, returns (None, 'INR', 'Price Not Mentioned').
    """
    # 1. Gather all pages for this bidder
    docs = db.query(Document).filter(Document.bidder_id == bidder.id).all()
    if not docs:
        return (None, "INR", "Price Not Mentioned (No documents uploaded)")

    # Target likely candidate documents first (Price schedule, BOQ, Commercial, Offer, Quotation)
    candidate_pages = []
    other_pages = []

    price_keywords = ["price", "quotation", "commercial", "boq", "schedule of rates", "bid amount", "quoted", "total cost", "lump sum", "ex-works"]

    for d in docs:
        fname_lower = (d.file_name or "").lower()
        is_priority_doc = any(k in fname_lower for k in ["price", "commercial", "quotation", "boq", "schedule", "offer"])
        for p in d.pages:
            text_lower = (p.text or "").lower()
            if any(k in text_lower for k in price_keywords) or is_priority_doc:
                candidate_pages.append((d.file_name, p.page_number, p.text))
            else:
                other_pages.append((d.file_name, p.page_number, p.text))

    pages_to_inspect = candidate_pages if candidate_pages else other_pages
    if not pages_to_inspect:
        return (None, "INR", "Price Not Mentioned")

    # Combine text snippet (cap at reasonable context length)
    combined_snippets = []
    for fname, pnum, text in pages_to_inspect[:8]:
        combined_snippets.append(f"--- Document: {fname} (Page {pnum}) ---\n{text[:1200]}")
    corpus = "\n\n".join(combined_snippets)

    # 2. Check with AI
    client = get_client()
    if not client:
        # Regex fallback
        return _regex_fallback_extract(corpus)

    prompt = f"""You are a commercial bid evaluation expert for BSES Equipment Engineering.
Analyze the following bidder document excerpts to determine if an official QUOTED BID PRICE (commercial price offer / tender rate) is mentioned for this tender.

Important Rules:
1. Distinguish between ANNUAL TURNOVER / FINANCIAL STATEMENTS (e.g., turnover Rs 38 crore) and the ACTUAL BID QUOTATION for this tender. Do NOT use annual turnover as quoted price!
2. If the document has a specific tender quotation, ex-works price, lump-sum supply price, or total price for the equipment, extract it.
3. If no quoted bid price / tender rate is found, you MUST state "price_found": false.

Bidder Name: {bidder.name}

Document Excerpts:
{corpus}

Respond ONLY in valid JSON matching this schema:
{{
  "price_found": true or false,
  "quoted_price": <number or null>,
  "currency": "INR" or "USD" etc.,
  "evidence": "<exact quote and document source, or 'Price Not Mentioned'>"
}}
"""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        res_text = response.text.strip()
        data = json.loads(res_text)
        if data.get("price_found") and data.get("quoted_price") is not None:
            price_val = float(data["quoted_price"])
            cur_val = data.get("currency", "INR") or "INR"
            evid = data.get("evidence", "Extracted from bidder offer")
            return (price_val, cur_val, evid)
        else:
            return (None, "INR", "Price Not Mentioned")
    except Exception as e:
        return _regex_fallback_extract(corpus)


def _regex_fallback_extract(corpus: str) -> Tuple[Optional[float], str, str]:
    """Fallback heuristic regex to search for explicit quotation price lines."""
    patterns = [
        r'(?:total\s*(?:bid|quoted|offer)?\s*(?:price|amount|value)|quoted\s*price|lump\s*sum\s*price)\s*[:=-]?\s*(?:rs\.?|inr|₹)?\s*([0-9,]+(?:\.[0-9]+)?)',
        r'(?:rs\.?|inr|₹)\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:only|per\s*set|total)',
    ]
    for pat in patterns:
        m = re.search(pat, corpus, re.IGNORECASE)
        if m:
            raw_num = m.group(1).replace(",", "")
            try:
                val = float(raw_num)
                # Ignore very small numbers or likely clause numbers
                if val > 1000:
                    return (val, "INR", f"Extracted price: {m.group(0)}")
            except ValueError:
                pass
    return (None, "INR", "Price Not Mentioned")


def compute_commercial_ranking(db: Session, tender_id: int) -> List[Dict]:
    """
    Computes commercial ranking for ALL qualified bidders:
    - Bidders with valid prices are ranked L1, L2, L3...
    - Bidders with price=None are marked as "Price Not Mentioned" with rank=None
    """
    qualified = get_qualified_bidders(db, tender_id)
    if not qualified:
        return []

    priced = [b for b in qualified if b.quoted_price is not None and b.quoted_price > 0]
    unpriced = [b for b in qualified if b.quoted_price is None or b.quoted_price <= 0]

    # Sort priced bidders ascending (lowest is L1)
    priced.sort(key=lambda b: b.quoted_price)
    l1_price = priced[0].quoted_price if priced else None

    result = []
    rank = 1
    for i, b in enumerate(priced):
        # Tie detection: same price as previous bidder -> same rank
        if i > 0 and b.quoted_price == priced[i - 1].quoted_price:
            current_rank = result[-1]["rank"]
            tie = True
        else:
            current_rank = rank
            tie = False

        pct_above = round(((b.quoted_price - l1_price) / l1_price) * 100, 2) if (l1_price and l1_price > 0) else 0.0
        label = f"L{current_rank}"

        b.commercial_rank = current_rank
        db.add(b)

        result.append({
            "rank": current_rank,
            "label": label,
            "bidder_id": b.id,
            "name": b.name,
            "quoted_price": b.quoted_price,
            "currency": b.price_currency or "INR",
            "pct_above_l1": pct_above,
            "tie": tie,
            "status": "Quoted"
        })
        rank += 1

    # Unpriced bidders
    for b in unpriced:
        b.commercial_rank = None
        db.add(b)
        result.append({
            "rank": None,
            "label": "—",
            "bidder_id": b.id,
            "name": b.name,
            "quoted_price": None,
            "currency": b.price_currency or "INR",
            "pct_above_l1": None,
            "tie": False,
            "status": "Price Not Mentioned"
        })

    db.commit()
    return result


def get_commercial_ranking(db: Session, tender_id: int) -> List[Dict]:
    """Return ranking for display or report export."""
    return compute_commercial_ranking(db, tender_id)
