"""
In-memory bulk-ZIP-ingestion progress tracker, keyed by tender_id — same
"plain dict behind a lock" approach as api/progress.py, with the same
single-process caveat noted there.
"""
import threading
from typing import Optional, TypedDict


class BulkIngestState(TypedDict):
    status: str  # "running" | "complete" | "error"
    completed: int
    total: int
    status_by_bidder: dict[str, str]
    error: Optional[str]


_lock = threading.Lock()
_progress: dict[int, BulkIngestState] = {}


def start_progress(tender_id: int, total: int) -> None:
    with _lock:
        _progress[tender_id] = {
            "status": "running",
            "completed": 0,
            "total": total,
            "status_by_bidder": {},
            "error": None,
        }


def report_bidder_done(tender_id: int, bidder_name: str, summary: str) -> None:
    with _lock:
        state = _progress.get(tender_id)
        if not state:
            return
        state["status_by_bidder"][bidder_name] = summary
        state["completed"] += 1


def finish_progress(tender_id: int) -> None:
    with _lock:
        state = _progress.get(tender_id)
        if state:
            state["status"] = "complete"


def fail_progress(tender_id: int, error: str) -> None:
    with _lock:
        state = _progress.get(tender_id)
        if state:
            state["status"] = "error"
            state["error"] = error


def get_progress(tender_id: int) -> Optional[BulkIngestState]:
    with _lock:
        return _progress.get(tender_id)
