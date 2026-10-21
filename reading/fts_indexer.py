"""
FTS5 Searcher for Candidate Pages.
Quickly finds pages in a bidder's bundle mentioning terms relevant to a requirement.
"""
from typing import List, Tuple
from sqlalchemy.orm import Session
from db.connection import engine
from db.models import Page, Document


def search_candidate_pages(
    db: Session,
    bidder_id: int,
    query_text: str,
    limit: int = 4
) -> List[Page]:
    """
    Searches the bidder's documents using SQLite FTS5 for the top candidate pages.
    Returns Page ORM entities.
    """
    # Clean query to purely alphanumeric tokens to prevent FTS5 syntax errors
    import re
    tokens = re.findall(r'[a-zA-Z0-9]+', query_text)
    
    # Common English stop words that pollute BM25 relevance rankings in technical tenders
    STOP_WORDS = {
        'the', 'and', 'for', 'with', 'shall', 'have', 'from', 'been', 'this', 'that',
        'equipment', 'comply', 'following', 'technical', 'parameters', 'parameter',
        'requirement', 'specified', 'below', 'clause', 'accordance', 'respects', 'any'
    }
    
    # Filter keywords: length > 1 (to keep units like '1s', '2x', 'ac', 'dc'), not stop words
    meaningful_keywords = [t for t in tokens if len(t) >= 2 and t.lower() not in STOP_WORDS]
    
    # Fallback to general tokens if all were filtered
    keywords = meaningful_keywords if meaningful_keywords else [t for t in tokens if len(t) > 2]
    
    if not keywords:
        return (
            db.query(Page)
            .join(Document, Page.document_id == Document.id)
            .filter(Document.bidder_id == bidder_id)
            .limit(limit)
            .all()
        )

    # Use OR search prioritizing specific technical keywords
    fts_query = " OR ".join(f'"{kw}"' for kw in keywords[:8])

    page_ids: List[int] = []
    with engine.connect() as conn:
        cursor = conn.exec_driver_sql(
            """
            SELECT p.page_id 
            FROM page_fts p
            JOIN documents d ON p.document_id = d.id
            WHERE d.bidder_id = ? AND page_fts MATCH ?
            ORDER BY bm25(page_fts)
            LIMIT ?
            """,
            (bidder_id, fts_query, limit)
        )
        rows = cursor.fetchall()
        page_ids = [r[0] for r in rows]

    if not page_ids:
        # Fallback: get top pages of the bidder
        return (
            db.query(Page)
            .join(Document, Page.document_id == Document.id)
            .filter(Document.bidder_id == bidder_id)
            .limit(limit)
            .all()
        )

    return db.query(Page).filter(Page.id.in_(page_ids)).all()
