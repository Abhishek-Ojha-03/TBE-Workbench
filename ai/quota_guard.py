"""
Quota guard — stops the app from repeatedly hammering an already-exhausted
Gemini key, and blocks a job upfront if it clearly can't finish within
today's remaining quota, instead of letting it run partway and fail with
429/503 errors mid-job.

Two layers:
1. Reactive circuit breaker (is_exhausted / mark_exhausted / record_success):
   the moment a real 429/daily-limit error is observed for a key, that key
   is marked exhausted in the database (not just in-memory) until the next
   quota reset. Every call site checks this BEFORE attempting a real API
   call, so an exhausted key is skipped instantly rather than retried.
2. Proactive pre-flight (check_sufficient_quota): before starting a
   multi-call job (spec extraction, bulk verification), estimate how many
   calls it needs and compare against each key's self-tracked remaining
   budget for today. If clearly insufficient, raise QuotaExhaustedError
   before any work starts.

Deliberately persisted to the database (db/models.py: ApiKeyQuotaState),
not just an in-memory flag — this is what makes the exhaustion state
survive an app restart, and be shared between the Streamlit app and the
FastAPI backend if both run against the same database.
"""
import os
from datetime import datetime, timedelta, date
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from db.connection import SessionLocal
from db.models import ApiKeyQuotaState

# Google's free-tier daily quota resets at midnight Pacific Time, not a
# rolling 24h window from first use — confirmed during earlier debugging
# of today's 429 errors.
QUOTA_RESET_TZ = ZoneInfo("America/Los_Angeles")

# Conservative default — override via .env once you've confirmed the real
# per-key daily limit for your model/tier in the Google AI Studio dashboard.
# The earlier 429 error message observed a limit of 20 requests/day for the
# model this project's MODEL_NAME currently resolves to.
DAILY_LIMIT_PER_KEY = int(os.getenv("GEMINI_DAILY_LIMIT_PER_KEY", "20"))


class QuotaExhaustedError(Exception):
    """Raised by the pre-flight check when a job clearly can't complete
    within today's remaining quota. Carries a user-facing message and the
    next reset time so the UI can show both."""

    def __init__(self, message: str, resets_at: Optional[datetime] = None):
        super().__init__(message)
        self.message = message
        self.resets_at = resets_at


def _today_quota_date() -> date:
    """Today's date in the quota-reset timezone (Pacific) — NOT the
    server's local date, since that's what Google actually resets against."""
    return datetime.now(QUOTA_RESET_TZ).date()


def _next_reset_at() -> datetime:
    """Next upcoming Pacific midnight, returned as a naive UTC-equivalent
    datetime (matching how the rest of this project stores timestamps)."""
    now_pacific = datetime.now(QUOTA_RESET_TZ)
    next_midnight_pacific = (now_pacific + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return next_midnight_pacific.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _get_or_create_row(db, key_label: str) -> ApiKeyQuotaState:
    row = db.query(ApiKeyQuotaState).filter(ApiKeyQuotaState.key_label == key_label).first()
    if not row:
        row = ApiKeyQuotaState(key_label=key_label, calls_today=0, count_date=str(_today_quota_date()))
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def is_exhausted(client) -> bool:
    """Checked BEFORE attempting a real API call with this client. True if
    this key was marked exhausted and the reset time hasn't passed yet."""
    key_label = getattr(client, "_key_label", None)
    if not key_label:
        return False  # unlabeled client (shouldn't normally happen) — don't block it

    db = SessionLocal()
    try:
        row = db.query(ApiKeyQuotaState).filter(ApiKeyQuotaState.key_label == key_label).first()
        if not row or not row.exhausted_until:
            return False
        if datetime.utcnow() >= row.exhausted_until:
            # Reset time has passed — clear it so this key is usable again.
            row.exhausted_until = None
            db.commit()
            return False
        return True
    finally:
        db.close()


def mark_exhausted(client) -> None:
    """Call this the moment a real 429/daily-limit error is observed for
    this client — persists the exhaustion so it's remembered across
    restarts and skipped immediately on every subsequent call site."""
    key_label = getattr(client, "_key_label", None)
    if not key_label:
        return

    db = SessionLocal()
    try:
        row = _get_or_create_row(db, key_label)
        row.exhausted_until = _next_reset_at()
        db.commit()
    finally:
        db.close()


def record_success(client) -> None:
    """Increments today's self-tracked call count for this key — used only
    by the pre-flight estimate below, not by is_exhausted/mark_exhausted."""
    key_label = getattr(client, "_key_label", None)
    if not key_label:
        return

    db = SessionLocal()
    try:
        row = _get_or_create_row(db, key_label)
        today_str = str(_today_quota_date())
        if row.count_date != today_str:
            row.count_date = today_str
            row.calls_today = 0
        row.calls_today += 1
        db.commit()
    finally:
        db.close()


def check_sufficient_quota(estimated_calls_needed: int) -> Tuple[bool, str, Optional[datetime]]:
    """
    Proactive pre-flight check. Call this BEFORE starting a multi-call job
    (spec extraction, bulk verification) with an estimate of how many
    Gemini calls it will need (e.g. page count, or ceil(requirements/12)
    per bidder). Returns (ok, message, resets_at).

    This is an approximation — it can't see calls made outside this app —
    so it only blocks when the shortfall is clear, not on tight margins.
    """
    from ai.client import get_all_clients

    clients = get_all_clients()
    if not clients:
        # No clients configured at all — not a quota problem, let the
        # normal "[MOCK OCR]" / error-string fallbacks in ai/client.py handle it.
        return True, "", None

    db = SessionLocal()
    try:
        today_str = str(_today_quota_date())
        available = 0
        earliest_reset: Optional[datetime] = None

        for client in clients:
            key_label = getattr(client, "_key_label", None)
            if not key_label:
                available += DAILY_LIMIT_PER_KEY
                continue

            row = db.query(ApiKeyQuotaState).filter(ApiKeyQuotaState.key_label == key_label).first()
            if row and row.exhausted_until and datetime.utcnow() < row.exhausted_until:
                if earliest_reset is None or row.exhausted_until < earliest_reset:
                    earliest_reset = row.exhausted_until
                continue  # this key contributes 0 — it's exhausted

            used_today = row.calls_today if (row and row.count_date == today_str) else 0
            available += max(0, DAILY_LIMIT_PER_KEY - used_today)

        if available >= estimated_calls_needed:
            return True, "", None

        resets_at = earliest_reset or _next_reset_at()
        resets_at_str = resets_at.strftime("%H:%M UTC")
        message = (
            f"Daily request limit reached — this job needs an estimated "
            f"{estimated_calls_needed} AI calls, but only about {available} remain "
            f"across your API keys today. It will likely fail partway through. "
            f"Try again after {resets_at_str}, or once quota resets."
        )
        return False, message, resets_at
    finally:
        db.close()
