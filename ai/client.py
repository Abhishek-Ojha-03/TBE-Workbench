"""
Unified AI client wrapper using google-genai.
Rules from Dev Guide:
1. Put every LLM call in one file and keep the model name in .env.
2. Keep prompts isolated.
3. Handle both text and vision multimodal calls.
"""
import os
import io
from typing import Optional, List
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

# Prevent stale OS environment variable GOOGLE_API_KEY from overriding valid keys
if "GOOGLE_API_KEY" in os.environ and not os.getenv("KEEP_SYSTEM_GOOGLE_KEY"):
    del os.environ["GOOGLE_API_KEY"]

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.8-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY_3", "") or os.getenv("GEMINI_API_KEY", "")


def get_all_clients():
    """Returns a list of initialized genai Clients across all available keys in .env.
    Automatically detects GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3,
    GEMINI_API_KEY_4, GEMINI_API_KEY_5, and any future numbered keys.
    Allows transparent pooling and automatic failover when any key hits 429 quota.
    """
    from google import genai
    keys = []
    
    # Automatically collect all keys matching GEMINI_API_KEY* from environment
    for k_name, val in sorted(os.environ.items()):
        if k_name.startswith("GEMINI_API_KEY") and val.strip():
            clean_val = val.strip().strip('"').strip("'")
            if clean_val and clean_val not in keys:
                keys.append(clean_val)
    
    clients = []
    for k in keys:
        try:
            clients.append(genai.Client(api_key=k))
        except Exception:
            pass
    return clients


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
        try:
            response = active_client.models.generate_content(
                model=MODEL_NAME,
                contents=pil_images + [batch_prompt]
            )
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
        try:
            response = active_client.models.generate_content(
                model=MODEL_NAME,
                contents=[image, prompt]
            )
            return response.text.strip() if response.text else ""
        except Exception as exc:
            last_error = str(exc)
            if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
                # Immediate failover to the next key without crashing or stalling
                continue
            else:
                return f"[OCR Error: {last_error}]"

    return f"[OCR Error: {last_error}]"

