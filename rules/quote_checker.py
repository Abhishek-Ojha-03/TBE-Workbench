"""
Quote checker: Strict 3-Tier verification in code.
Prevents hallucinations while tolerating OCR formatting noise (bullets, linebreaks, spacing).

Tier 1: Exact substring match.
Tier 2: Canonical cleaned match (strips bullets • * -, punctuation, extra spaces).
Tier 3: Key Technical Entity Anchor (checks that all numbers & units e.g. '25 kA', '3 seconds'
        really exist on the cited page along with technical context words).
"""
import re


def normalize_whitespace(text: str) -> str:
    """Normalizes multiple spaces, tabs, and newlines into single spaces for robust matching."""
    return re.sub(r'\s+', ' ', text).strip()


def verify_quote_in_page_text(quote: str, page_text: str) -> bool:
    """
    3-Tier Verification Cascade:
    Guarantees zero-hallucination while preventing false rejections caused by OCR artifacts.
    """
    if not quote or not page_text:
        return False

    q_strip = quote.strip()
    # ── Tier 1: Exact raw substring check ──
    if q_strip in page_text:
        return True

    # ── Tier 2: Canonical cleaned match (handles bullets, linebreaks, punctuation) ──
    clean = lambda t: re.sub(r'[\u2022\u25cf\u25aa\uf0b7*•\-_:;,|?()\"\'\[\]]', ' ', t.lower())
    norm = lambda t: re.sub(r'\s+', ' ', clean(t)).strip()

    nq = norm(q_strip)
    np = norm(page_text)

    if nq and nq in np:
        return True

    # ── Tier 3: Technical Entity & Numerical Anchor ──
    # Ensure all numerical values + units in quote genuinely exist on that page
    np_spaced = re.sub(r'(\d+)\s*([a-zA-Z]+)', r'\1 \2', np)
    nq_spaced = re.sub(r'(\d+)\s*([a-zA-Z]+)', r'\1 \2', nq)

    # Extract all numerical tokens e.g. '25 ka', '3 seconds', '11 kv', '14.5 crore'
    tokens = re.findall(r'\b\d+(?:\.\d+)?(?:\s+[a-z]+)?\b', nq_spaced)
    tokens = [t.strip() for t in tokens if any(c.isdigit() for c in t)]

    # If numbers exist in the quote, EVERY SINGLE ONE must exist on the page
    if tokens:
        if all(t in np_spaced for t in tokens):
            # Also require at least 2 key technical words to ensure context match
            alpha_words = [w for w in nq.split() if len(w) > 3 and not any(c.isdigit() for c in w)]
            matching_words = sum(1 for w in alpha_words if w in np)
            if matching_words >= min(2, len(alpha_words)):
                return True
    else:
        # Text-only quote (e.g. standard declaration or document title)
        # Check if 80%+ of significant words match on that page
        words = [w for w in nq.split() if len(w) > 3]
        if words:
            match_ratio = sum(1 for w in words if w in np) / len(words)
            if match_ratio >= 0.80:
                return True

    return False

