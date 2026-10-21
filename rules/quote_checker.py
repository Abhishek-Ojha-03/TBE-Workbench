"""
Quote checker: Strict verification in code.
Rule from Dev Guide (Step 7, item 12):
"Check the quote in code. The quote must really appear in the text of that page.
If it does not, throw the answer away and set the status to 'Needs Human Review'.
This stops the AI from inventing proof."
"""
import re


def normalize_whitespace(text: str) -> str:
    """Normalizes multiple spaces, tabs, and newlines into single spaces for robust matching."""
    return re.sub(r'\s+', ' ', text).strip()


def verify_quote_in_page_text(quote: str, page_text: str) -> bool:
    """
    Checks whether the exact quote exists within the raw extracted page text.
    Uses exact substring match first, followed by whitespace-normalized comparison.
    Never accepts hallucinated quotes.
    """
    if not quote or not page_text:
        return False

    # 1. Exact raw substring check
    if quote.strip() in page_text:
        return True

    # 2. Whitespace-normalized match (handles PDF newline linebreaks)
    norm_quote = normalize_whitespace(quote).lower()
    norm_page = normalize_whitespace(page_text).lower()

    return norm_quote in norm_page

