"""
In-memory extraction progress tracker, keyed by tender_id.

Deliberately simple for this stage of the project: a plain dict behind a
lock, not Redis/a DB table. This is fine for a single-process dev/demo
backend; if this API ever runs as multiple worker processes (e.g. gunicorn
with >1 worker), this would need to move to something shared across
processes (Redis, a DB table) since each worker would have its own copy
of this dict. Flagged here rather than silently assumed.
"""
import threading
from typing import Optional, TypedDict


class ProgressState(TypedDict):
    status: str  # "ingesting" | "extracting" | "complete" | "error"
    current_page: int
    total_pages: int
    requirements_so_far: int
    error: Optional[str]


_lock = threading.Lock()
_progress: dict[int, ProgressState] = {}


def set_progress(tender_id: int, **kwargs) -> None:
    with _lock:
        existing = _progress.get(tender_id, {
            "status": "ingesting",
            "current_page": 0,
            "total_pages": 0,
            "requirements_so_far": 0,
            "error": None,
        })
        existing.update(kwargs)
        _progress[tender_id] = existing  # type: ignore[assignment]


def get_progress(tender_id: int) -> Optional[ProgressState]:
    with _lock:
        return _progress.get(tender_id)


def clear_progress(tender_id: int) -> None:
    with _lock:
        _progress.pop(tender_id, None)
