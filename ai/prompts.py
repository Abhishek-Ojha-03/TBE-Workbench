"""
Prompt templates for TBE Workbench.
"""

SPEC_EXTRACTION_PROMPT = """
You are a senior technical tender evaluation and procurement expert for BSES Equipment Engineering.
Analyze the specification text from Page {page_number}.

Extract ONLY genuine, actionable requirements:
1. Technical specifications, parameters, ratings, requirements, performance criteria, deliverables, or standards.
2. Qualification Requirements (QR): Identify these STRICTLY by explicit headings like "Qualification Criteria", "Technical Qualification", "QR", "Eligibility", "Financial Criteria", "Past Experience". Do NOT guess a requirement as QR unless it falls under such an explicit heading or clause.
3. Mandatory Documents: e.g. "Technical Offer", "Deviation Sheet", "Audited balance sheets", "Type test reports", "Guaranteed Technical Particulars".
4. Sentences & Clauses: Extract each numbered or lettered clause as one complete requirement item. Keep the clause and its full text intact. Do NOT split a single clause (such as clause 2.3 or 2.4) into multiple fragmented sub-rows, and do NOT duplicate requirements already mentioned.
5. If technical parameters are presented in a table or list under a clause:
   - Extract EACH individual parameter as its own distinct requirement row with its parameter name and required value (e.g. "Rated voltage: 11 kV", "Rated short circuit breaking current: 25 kA for 3 seconds").
6. CRITICAL - WHAT NOT TO EXTRACT (FILTER OUT):
   - Do NOT extract section headings, chapter titles, table headers, or introductory lead-in phrases (e.g. "The following type tests shall have been carried out on the offered equipment:", "The equipment shall comply with the following technical parameters:").
   - Do NOT extract document metadata, boilerplate instructions, or notes about deviation sheets (e.g. "Any deviation from the above parameters shall be listed in the Deviation Sheet", "A Deviation Sheet marked NIL shall be taken to mean full compliance").
   - Do NOT extract repetitive sub-clause fragments (e.g. if an undertaking states "routine tests shall be carried out... and test certificates submitted", extract it as ONE single requirement, never two fragmented rows).

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
   - Specific document submission requirements when NO document is submitted at all. NOTE: If the bidder HAS submitted the actual document (e.g. they submitted an Audited Financial Statements extract certified by Chartered Accountants with 3-year turnover figures, or an actual Quality Assurance Plan stating routine/stage inspections and replacement of defective units), and it satisfies the requirement, mark "complied". Do NOT mark "not_complied" on document formatting technicalities if the authentic certified document/extract is submitted.
   - For requirement "The bidder shall submit a Quality Assurance Plan for approval within fifteen days of the date of the purchase order": If the bidder has submitted a document entitled "QUALITY ASSURANCE PLAN" detailing stage inspections/routine tests, mark "complied" citing the Quality Assurance Plan document.
   - For requirement "Any deviation from the above parameters shall be listed in the Deviation Sheet. A Deviation Sheet marked NIL shall be taken to mean full compliance": If the Deviation Sheet contains the word "NIL" or "NO DEVIATIONS", quote "NIL" or "We confirm that there are NO DEVIATIONS from the technical specification" directly from the bidder's Deviation Sheet and output "complied". Do NOT quote the tender requirement text itself.
   - Specific warranty, guarantee, or performance bank guarantee terms (e.g. 18 months / 24 months, 10% PBG). Do NOT treat blanket deviation sheet as proof of guarantee if no dedicated guarantee undertaking exists.
   - Specific type tests or ratings that must be backed by test reports or GTP.
   Never mark "complied" based solely on a blanket statement or NIL deviation sheet when concrete documentary evidence is required.
8. CRITICAL TABLE READING & ANTI-HALLUCINATION RULE (GUARANTEED TECHNICAL PARTICULARS):
   - When reading GTP tables (e.g. Sl No, Parameter Description, Required Value, Guaranteed by Bidder):
     You MUST read the value from the "Guaranteed by Bidder" / "Offered" column, NOT from the "Required Value" column.
   - If the bidder guaranteed value equals or exceeds the required value (e.g. required "25 kA for 3 seconds" and guaranteed "25 kA for 3 seconds"), the status IS "complied".
   - NEVER claim a bidder offered a lower or deviating value (such as "20 kA") unless the text explicitly and unambiguously appears under their offered/guaranteed particulars or in their Deviation Sheet. NEVER invent or hallucinate deviation figures!

Return valid JSON conforming to this schema:
{{
  "status": "complied" | "not_complied" | "needs_human_review",
  "document": "Document Name.pdf",
  "page": 1,
  "quote": "Exact verbatim quote from the page text above",
  "reason": "Detailed technical reason"
}}
"""


BATCH_BIDDER_VERIFICATION_PROMPT = """
You are an expert technical bid evaluation engineer checking bidder documents against utility tender specifications.

You are evaluating a batch of {num_requirements} technical requirements for ONE bidder.

REQUIREMENTS TO EVALUATE IN THIS BATCH:
{requirements_batch_text}

BELOW ARE THE CANDIDATE PAGES FOUND IN THE BIDDER'S SUBMITTED DOCUMENTS:
{candidate_pages_text}

Rules:
1. THE GOLDEN RULE: You only suggest. If you cannot find direct concrete proof in the candidate pages above, output status "needs_human_review". NEVER guess "complied".
2. If concrete evidence is found that meets or exceeds the required specification, output "complied".
3. If evidence shows the bidder explicitly fails, deviates, or falls short of the requirement, output "not_complied".
4. "quote" MUST be an EXACT, VERBATIM sentence from one of the candidate pages above. Do NOT modify, summarize, or paraphrase the quote.
5. "document": exact name of the file where the quote is located (e.g. "ABC_guaranteed_technical_particulars.pdf").
6. "page": 1-based integer page number where the quote is located.
7. "clause_id": exact ID/Clause label matching the requirement (e.g. "REQ-1", "REQ-2", etc.).
8. "reason": clear technical justification.
9. CRITICAL ANTI-TRAP GUARD:
   - Specific document submission requirements: If the bidder HAS submitted the actual authentic document (e.g., Audited Financial Statements extract certified by Chartered Accountants, Quality Assurance Plan detailing stage inspections, Deviation sheet, etc.), mark "complied" citing that document.
   - For requirement "The bidder shall submit a Quality Assurance Plan for approval within fifteen days of the date of the purchase order": If the bidder has submitted a document entitled "QUALITY ASSURANCE PLAN", mark "complied" citing it.
   - For requirement "Any deviation from the above parameters shall be listed in the Deviation Sheet. A Deviation Sheet marked NIL shall be taken to mean full compliance": If the Deviation Sheet contains the word "NIL" or "NO DEVIATIONS", quote "NIL" or "We confirm that there are NO DEVIATIONS from the technical specification" directly from the Deviation Sheet and output "complied". Do NOT quote the tender specification text itself.
   - Specific warranty, guarantee, or PBG terms: Must be backed by the guarantee undertaking document.
   - Do NOT mark "complied" based solely on a blanket statement when concrete documentary proof is absent.
10. CRITICAL TABLE READING & ANTI-HALLUCINATION RULE (GUARANTEED TECHNICAL PARTICULARS):
   - When reading GTP tables (e.g. Sl No, Parameter Description, Required Value, Guaranteed by Bidder):
     You MUST read the value from the "Guaranteed by Bidder" / "Offered" column, NOT from the "Required Value" column.
   - If the bidder guaranteed value equals or exceeds the required value (e.g. required "25 kA for 3 seconds" and guaranteed "25 kA for 3 seconds"), the status IS "complied".
   - NEVER claim a bidder offered a lower or deviating value (such as "20 kA") unless the text explicitly and unambiguously appears under their offered/guaranteed particulars or in their Deviation Sheet. NEVER invent or hallucinate deviation figures!

Return valid JSON conforming strictly to this schema:
{{
  "evaluations": [
    {{
      "clause_id": "REQ-1",
      "status": "complied" | "not_complied" | "needs_human_review",
      "document": "Document Name.pdf",
      "page": 1,
      "quote": "Exact verbatim quote from the candidate page above",
      "reason": "Detailed technical justification"
    }}
  ]
}}
Ensure you return an evaluation for EVERY requirement in this batch!
"""


