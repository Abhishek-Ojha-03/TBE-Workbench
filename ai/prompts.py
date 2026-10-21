"""
Prompt templates for TBE Workbench.
"""

SPEC_EXTRACTION_PROMPT = """
You are a senior technical tender evaluation and procurement expert.
Analyze the following specification text from Page {page_number}.

Extract all:
1. Technical specifications, parameters, ratings, requirements, performance criteria, deliverables, or standards (whether for electrical equipment, IT hardware/software/laptops, vehicles/tyres, civil/mechanical supplies, or maintenance/consulting services).
2. Qualification Requirements (QR): Identify these STRICTLY by explicit headings like "Qualification Criteria", "Technical Qualification", "QR", "Eligibility", "Financial Criteria", "Past Experience". Do NOT guess a requirement as QR unless it falls under such an explicit heading or clause.
3. Mandatory Documents: e.g. "Signed Technical Offer", "Deviation Sheet", "Audited Balance Sheets", "OEM Authorization", "Test Reports / Certificates", "Certifications".

Return a valid JSON object matching this schema:
{{
  "requirements": [
    {{
      "clause": "string or null",
      "text": "full requirement statement",
      "is_qualification_requirement": boolean,
      "is_mandatory_document": boolean,
      "standards": ["string", ...],
      "page": {page_number}
    }}
  ]
}}

Specification Content (Page {page_number}):
\"\"\"
{page_text}
\"\"\"
"""

BIDDER_VERIFICATION_PROMPT = """
You are an expert technical bid evaluation engineer checking bidder documents against a utility specification.
Requirement to evaluate:
Clause: {clause}
Requirement Text: \"\"\"{requirement_text}\"\"\"

Below are the candidate pages found in the bidder's submitted documents:
{candidate_pages_text}

Rules:
1. THE GOLDEN RULE: You only suggest. If you cannot find direct proof, output status "needs_human_review". NEVER guess "complied".
2. If evidence is found that meets or exceeds the required ratings, output "complied".
3. If evidence shows the bidder explicitly fails or deviates from the requirement, output "not_complied".
4. "quote" MUST be an EXACT, VERBATIM sentence from one of the candidate pages above. Do NOT modify or paraphrase the quote.
5. "document": exact name of the file where the quote is located.
6. "page": 1-based page number where the quote is located.
7. "reason": clear technical justification.
8. CRITICAL ANTI-TRAP GUARD: A general statement in a "Deviation Sheet" claiming "NO DEVIATIONS" or a blanket statement in a "Technical Offer" claiming compliance with all clauses is NOT proof of compliance for:
   - Specific document submission requirements (e.g. submitting a Quality Assurance Plan, Audited Balance Sheet, Credentials, Test Facility proof, etc.). If the specific required document is not submitted, output "not_complied" or "needs_human_review".
   - Specific warranty, guarantee, or performance bank guarantee terms (e.g. 18 months / 24 months, 10% PBG). Do NOT treat blanket deviation sheet as proof of guarantee if no dedicated guarantee undertaking exists.
   - Specific type tests or ratings that must be backed by test reports or GTP.
   Never mark "complied" based solely on a blanket statement or NIL deviation sheet when concrete documentary evidence is required.

Return valid JSON conforming to this schema:
{{
  "status": "complied" | "not_complied" | "needs_human_review",
  "document": "Document Name.pdf",
  "page": 1,
  "quote": "Exact verbatim quote from the page text above",
  "reason": "Detailed technical reason"
}}
"""

