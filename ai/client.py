"""
Unified AI client wrapper using google-genai.
Rules from Dev Guide:
1. Put every LLM call in one file and keep the model name in .env.
2. Keep prompts isolated.
3. Handle both text and vision multimodal calls.
"""
import os
import io
from typing import Optional
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.8-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")


def get_client():
    """Initializes and returns google-genai Client if API key is present."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"Warning: Failed to initialize Gemini Client: {e}")
        return None


def extract_text_from_image(image_bytes: bytes, prompt: Optional[str] = None) -> str:
    """
    Extracts text from scanned page / handwriting / technical diagrams using Gemini Vision.
    Ensures exact capture of numbers, ratings, units (kV, kA, A, sec).
    """
    client = get_client()
    if client is None:
        return "[MOCK OCR - Set GEMINI_API_KEY in .env for actual Gemini 3.1 Flash Lite Vision OCR]"

    if prompt is None:
        prompt = (
            "You are an expert technical document OCR system for high-voltage electrical engineering tenders. "
            "Extract all text, technical parameters, numerical ratings, units (kV, kA, A, sec, MVA, Hz), "
            "stamps, signatures, and handwritten notes from this document page image. "
            "Maintain exact formatting, numbers, and units without omitting or altering any values. "
            "Output only the extracted text content."
        )

    try:
        image = Image.open(io.BytesIO(image_bytes))
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[image, prompt]
        )
        return response.text.strip() if response.text else ""
    except Exception as exc:
        return f"[OCR Error: {str(exc)}]"

