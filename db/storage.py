"""
Supabase Storage helper — used instead of local disk for files that must
survive a backend restart (page preview images, cached bidder ZIPs).

Free-tier hosts like Render wipe local disk on every restart/redeploy, so
anything saved under data/ with plain open(...,"wb") disappears. When
SUPABASE_URL + SUPABASE_SERVICE_KEY are set, callers upload/download
through this module instead; when they aren't set (local dev), callers
fall back to local disk as before — storage_enabled() tells them which
path to take.
"""
import os
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "tbe-files")


def storage_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _headers(content_type: Optional[str] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def upload_file(file_bytes: bytes, path: str, content_type: str = "application/octet-stream") -> bool:
    """Uploads (or overwrites) a file at `path` inside the bucket. Returns
    False on any failure — caller should fall back to local disk."""
    if not storage_enabled():
        return False
    url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{path}"
    headers = _headers(content_type)
    headers["x-upsert"] = "true"
    try:
        resp = requests.put(url, headers=headers, data=file_bytes, timeout=30)
        return resp.status_code in (200, 201)
    except requests.RequestException:
        return False


def download_file(path: str) -> Optional[bytes]:
    """Downloads a file at `path` from the bucket. Returns None if storage
    isn't configured, the file doesn't exist, or the request fails."""
    if not storage_enabled():
        return None
    url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{path}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=30)
        if resp.status_code == 200:
            return resp.content
    except requests.RequestException:
        pass
    return None
