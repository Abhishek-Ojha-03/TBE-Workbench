"""
Commercial Evaluation Service (Part 2 — Price Bid Opening).

Rules (Two-Envelope System):
- Price data is NEVER shown in the Technical (Part 1) screens.
- Only technically QUALIFIED bidders participate in Part 2.
- L1 = lowest price, L2 = second lowest, etc.
- If two bidders quote the same price, both receive the same rank and the
  tie is flagged for the committee to resolve manually.
"""
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from db.models import Bidder


# ── Helpers ──────────────────────────────────────────────────────────────────

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
    """
    Persist a bidder's quoted price and currency.
    Pass price=None to clear a previously entered price.
    """
    bidder = db.query(Bidder).filter(Bidder.id == bidder_id).first()
    if not bidder:
        raise ValueError(f"Bidder ID {bidder_id} not found.")
    bidder.quoted_price = price
    bidder.price_currency = currency
    db.commit()
    db.refresh(bidder)
    return bidder


def compute_commercial_ranking(db: Session, tender_id: int) -> List[Dict]:
    """
    Sort qualified bidders with a quoted price by ascending price, assign
    commercial_rank (L1=1, L2=2, …), persist ranks, and return a ranked list.

    Returns a list of dicts:
      {rank, label, bidder_id, name, quoted_price, currency, pct_above_l1, tie}
    Bidders without a price entered are excluded from ranking.
    """
    qualified = get_qualified_bidders(db, tender_id)
    priced = [b for b in qualified if b.quoted_price is not None]

    if not priced:
        return []

    priced.sort(key=lambda b: b.quoted_price)
    l1_price = priced[0].quoted_price

    result = []
    rank = 1
    for i, b in enumerate(priced):
        # Detect tie: same price as previous bidder → same rank
        if i > 0 and b.quoted_price == priced[i - 1].quoted_price:
            current_rank = result[-1]["rank"]
            tie = True
        else:
            current_rank = rank
            tie = i > 0 and b.quoted_price == priced[i - 1].quoted_price

        pct_above = round(((b.quoted_price - l1_price) / l1_price) * 100, 2) if l1_price else 0.0
        label = f"L{current_rank}"

        b.commercial_rank = current_rank
        db.add(b)

        result.append(
            {
                "rank": current_rank,
                "label": label,
                "bidder_id": b.id,
                "name": b.name,
                "quoted_price": b.quoted_price,
                "currency": b.price_currency or "INR",
                "pct_above_l1": pct_above,
                "tie": tie,
            }
        )
        rank += 1

    db.commit()
    return result


def get_commercial_ranking(db: Session, tender_id: int) -> List[Dict]:
    """
    Return the last computed ranking from DB (without recomputing).
    Returns same dict structure as compute_commercial_ranking().
    """
    qualified = get_qualified_bidders(db, tender_id)
    priced = [b for b in qualified if b.quoted_price is not None]

    if not priced:
        return []

    priced.sort(key=lambda b: (b.commercial_rank or 9999, b.quoted_price or 0))
    l1_price = min(b.quoted_price for b in priced)

    result = []
    seen_prices = {}
    for b in priced:
        pct_above = round(((b.quoted_price - l1_price) / l1_price) * 100, 2) if l1_price else 0.0
        rank = b.commercial_rank or 0
        tie = b.quoted_price in seen_prices
        seen_prices[b.quoted_price] = True
        result.append(
            {
                "rank": rank,
                "label": f"L{rank}",
                "bidder_id": b.id,
                "name": b.name,
                "quoted_price": b.quoted_price,
                "currency": b.price_currency or "INR",
                "pct_above_l1": pct_above,
                "tie": tie,
            }
        )
    return result

