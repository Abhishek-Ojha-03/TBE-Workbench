"""
Unified AI client wrapper using google-genai.
Rules from Dev Guide:
1. Put every LLM call in one file and keep the model name in .env.
2. Keep prompts isolated.
3. Handle both text and vision multimodal calls.
"""
import os
import io
import itertools
import threading
from typing import Optional, List
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

# Prevent stale OS environment variable GOOGLE_API_KEY from overriding valid keys
if "GOOGLE_API_KEY" in os.environ and not os.getenv("KEEP_SYSTEM_GOOGLE_KEY"):
    del os.environ["GOOGLE_API_KEY"]

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.8-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY_3", "") or os.getenv("GEMINI_API_KEY", "")

_CLIENT_POOL: List = []
_CLIENT_CYCLE = None
_POOL_LOCK = threading.Lock()


def get_all_clients():
    """Returns a list of initialized genai Clients across all available keys in .env.
    Automatically detects GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3,
    GEMINI_API_KEY_4, GEMINI_API_KEY_5, and any future numbered keys.
    Allows transparent pooling and automatic failover when any key hits 429 quota.
    """
    global _CLIENT_POOL, _CLIENT_CYCLE
    from google import genai

    with _POOL_LOCK:
        if _CLIENT_POOL:
            return _CLIENT_POOL

        keys = []  # list of (env_var_name, key_value), in sorted-name order
        for k_name, val in sorted(os.environ.items()):
            if k_name.startswith("GEMINI_API_KEY") and val.strip():
                clean_val = val.strip().strip('"').strip("'")
                if clean_val and clean_val not in [v for _, v in keys]:
                    keys.append((k_name, clean_val))

        clients = []
        for k_name, k in keys:
            try:
                c = genai.Client(api_key=k)
                # Tagged with the env var name (never the raw key) so
                # ai/quota_guard.py can persist per-key exhaustion state
                # without ever storing a secret in the database.
                c._key_label = k_name
                clients.append(c)
            except Exception:
                pass

        _CLIENT_POOL = clients
        if _CLIENT_POOL:
            _CLIENT_CYCLE = itertools.cycle(_CLIENT_POOL)
        return _CLIENT_POOL


def get_next_client():
    """
    Thread-safe Round-Robin client selector.
    Cycles evenly across all available API keys:
      Request 1 -> Key 1
      Request 2 -> Key 2
      Request 3 -> Key 3
      Request 4 -> Key 1 ...
    Triples instant throughput with 0 added delay.
    """
    global _CLIENT_CYCLE
    get_all_clients()
    with _POOL_LOCK:
        if not _CLIENT_POOL:
            return None
        return next(_CLIENT_CYCLE)


def get_client():
    """Initializes and returns the primary google-genai Client.
    Prioritizes GEMINI_API_KEY from .env first, then GOOGLE_API_KEY.
    """
    clients = get_all_clients()
    return clients[0] if clients else None


def extract_text_from_images_batch(image_bytes_list: List[bytes], prompt: Optional[str] = None) -> List[str]:
    """
    Extracts text from a batch of up to 4-5 scanned pages simultaneously in a SINGLE Gemini Vision call.
    Reduces network round-trips and API quota consumption by up to 80%.
    """
    if not image_bytes_list:
        return []
        
    if len(image_bytes_list) == 1:
        return [extract_text_from_image(image_bytes_list[0], prompt)]

    clients = get_all_clients()
    if not clients:
        return ["[MOCK OCR]"] * len(image_bytes_list)

    num_pages = len(image_bytes_list)
    batch_prompt = (
        f"You are an expert technical document OCR system for high-voltage electrical engineering tenders.\n"
        f"The user has provided {num_pages} document page images in sequence.\n"
        f"Extract all text, numbers, units (kV, kA, A, sec, Hz, MVA), ratings, tables, stamps, and signatures from each page.\n"
        f"You MUST format your output with this exact delimiter between pages:\n"
    )
    for i in range(1, num_pages + 1):
        batch_prompt += f"=== PAGE {i} ===\n[extracted text for page {i}]\n"
    batch_prompt += "Ensure 100% precision on numerical values and units. Do not omit any technical specifications."

    pil_images = []
    for b in image_bytes_list:
        try:
            pil_images.append(Image.open(io.BytesIO(b)))
        except Exception:
            pass

    if len(pil_images) != num_pages:
        # Fallback to individual extraction if any image fails to load
        return [extract_text_from_image(b, prompt) for b in image_bytes_list]

    last_error = ""
    for active_client in clients:
        from ai import quota_guard
        if quota_guard.is_exhausted(active_client):
            continue  # skip a key we already know is exhausted today — don't even try
        try:
            response = active_client.models.generate_content(
                model=MODEL_NAME,
                contents=pil_images + [batch_prompt]
            )
            quota_guard.record_success(active_client)
            raw_text = response.text.strip() if response.text else ""

            # Split results by page delimiter
            results = []
            for i in range(1, num_pages + 1):
                marker = f"=== PAGE {i} ==="
                next_marker = f"=== PAGE {i+1} ===" if i < num_pages else None

                if marker in raw_text:
                    part = raw_text.split(marker)[1]
                    if next_marker and next_marker in part:
                        part = part.split(next_marker)[0]
                    results.append(part.strip())
                else:
                    results.append("")

            if len(results) == num_pages and any(len(r) > 10 for r in results):
                return results
        except Exception as exc:
            last_error = str(exc)
            if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
                # Only a genuine per-day quota error locks the key out until
                # tomorrow — a brief RPM burst just moves on to the next key.
                if quota_guard.is_daily_quota_error(last_error):
                    quota_guard.mark_exhausted(active_client)
                continue

    # Graceful fallback: individual extraction if batch delimiter parsing failed
    return [extract_text_from_image(b, prompt) for b in image_bytes_list]


def extract_text_from_image(image_bytes: bytes, prompt: Optional[str] = None) -> str:
    """
    Extracts text from scanned page / handwriting / technical diagrams using Gemini Vision.
    Ensures exact capture of numbers, ratings, units (kV, kA, A, sec).
    Iterates through the pool of API clients so that if one key hits a 429 quota error,
    it automatically fails over to the next working key.
    """
    clients = get_all_clients()
    if not clients:
        return "[MOCK OCR - Set GEMINI_API_KEY in .env for actual Gemini Vision OCR]"

    if prompt is None:
        prompt = (
            "You are an expert technical document OCR system for high-voltage electrical engineering tenders. "
            "Extract all text, technical parameters, numerical ratings, units (kV, kA, A, sec, MVA, Hz), "
            "stamps, signatures, and handwritten notes from this document page image. "
            "Maintain exact formatting, numbers, and units without omitting or altering any values. "
            "Output only the extracted text content."
        )

    last_error = ""
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as img_err:
        return f"[Image Error: {img_err}]"

    for active_client in clients:
        from ai import quota_guard
        if quota_guard.is_exhausted(active_client):
            continue  # skip a key we already know is exhausted today — don't even try
        try:
            response = active_client.models.generate_content(
                model=MODEL_NAME,
                contents=[image, prompt]
            )
            quota_guard.record_success(active_client)
            return response.text.strip() if response.text else ""
        except Exception as exc:
            last_error = str(exc)
            if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
                # Only a genuine per-day quota error locks the key out until
                # tomorrow — a brief RPM burst just moves on to the next key.
                if quota_guard.is_daily_quota_error(last_error):
                    quota_guard.mark_exhausted(active_client)
                continue
            else:
                return f"[OCR Error: {last_error}]"

    return f"[OCR Error: {last_error}]"

