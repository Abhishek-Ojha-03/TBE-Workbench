"""
Commercial Evaluation endpoints — Part 2 (Price Bid Opening), wrapping
db/commercial_service.py unchanged. Same two-envelope rule as
ui/commercial_view.py: only technically Qualified bidders are visible
here, AI extracts quoted prices, and L1/L2/L3 ranking is computed from
them.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db
from api.schemas import CommercialRankingRow, FetchPricesResponse
from db.models import Bidder
from db.repository import get_tender_by_id
from db.commercial_service import (
    get_qualified_bidders,
    extract_bidder_price_with_ai,
    save_price_for_bidder,
    compute_commercial_ranking,
)

router = APIRouter(prefix="/tenders/{tender_id}", tags=["commercial"])


@router.get("/commercial-ranking", response_model=List[CommercialRankingRow])
def commercial_ranking(tender_id: int, db: Session = Depends(get_db)):
    """Matches the Commercial Evaluation screen's ranking table — only
    Qualified bidders appear, ranked L1/L2/L3 by quoted price."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    ranking = compute_commercial_ranking(db, tender_id)
    return [CommercialRankingRow(**r) for r in ranking]


@router.post("/commercial-fetch-prices", response_model=FetchPricesResponse)
def fetch_prices_with_ai(tender_id: int, db: Session = Depends(get_db)):
    """Matches the '⚡ Fetch Prices with AI' button — scans every Qualified
    bidder's documents for a quoted price and saves it, then returns the
    freshly recomputed ranking."""
    tender = get_tender_by_id(db, tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    qualified = get_qualified_bidders(db, tender_id)
    if not qualified:
        raise HTTPException(
            status_code=400,
            detail="No bidders are marked Qualified yet — complete Technical Evaluation first.",
        )

    for b in qualified:
        price, currency, _reason = extract_bidder_price_with_ai(db, b)
        save_price_for_bidder(db, b.id, price, currency)

    ranking = compute_commercial_ranking(db, tender_id)
    return FetchPricesResponse(
        scanned_count=len(qualified),
        ranking=[CommercialRankingRow(**r) for r in ranking],
    )
