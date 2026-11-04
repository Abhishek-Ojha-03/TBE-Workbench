"""
In-memory Delta Re-Verification progress tracker, keyed by (tender_id,
bidder_id) — same pattern as api/progress.py (specification extraction),
same single-process caveat noted there.
"""
import threading
from typing import Optional, TypedDict


class ClarificationProgressState(TypedDict):
    status: str  # "uploading" | "ingesting" | "reverifying" | "complete" | "error"
    total_flagged: int
    rechecked_count: int
    new_status: Optional[str]
    clauses: list[str]
    error: Optional[str]


_lock = threading.Lock()
_progress: dict[tuple[int, int], ClarificationProgressState] = {}


def set_progress(tender_id: int, bidder_id: int, **kwargs) -> None:
    with _lock:
        key = (tender_id, bidder_id)
        existing = _progress.get(key, {
            "status": "uploading",
            "total_flagged": 0,
            "rechecked_count": 0,
            "new_status": None,
            "clauses": [],
            "error": None,
        })
        existing.update(kwargs)
        _progress[key] = existing  # type: ignore[assignment]


def get_progress(tender_id: int, bidder_id: int) -> Optional[ClarificationProgressState]:
    with _lock:
        return _progress.get((tender_id, bidder_id))
