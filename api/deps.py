"""
Shared FastAPI dependencies.

This file intentionally imports from the EXISTING Python backend
(db/connection.py) rather than redefining a database session — the whole
point of this API layer is to be a thin wrapper around the business logic
that already exists in db/, ai/, rules/, outputs/, not a reimplementation.
"""
from typing import Generator
from sqlalchemy.orm import Session

from db.connection import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a DB session per-request, closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
