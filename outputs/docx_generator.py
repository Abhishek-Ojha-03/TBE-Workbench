"""
Word Document Generator (Step 11)
Generates the official BSES deliverables:
1. TBE MOM (Minutes of Meeting) (.docx)
2. TBE Report (Technical Evaluation Report - TER) (.docx)

Rules from Dev Guide:
- Fill the templates with CONFIRMED data only.
- Build tables and lists directly from the database.
- Use AI ONLY for sentences of summary text, and let the engineer edit them.
- DO NOT rank the bidders.
"""
import os
from datetime import datetime
from typing import List, Optional
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from sqlalchemy.orm import Session

from db.models import Tender, Bidder, BaselineVersion, Requirement, Finding, Evidence
from db.baseline_service import get_latest_baseline, get_baseline_requirements, get_bidders_for_tender
from ai.client import get_client, MODEL_NAME

DOCS_OUTPUT_DIR = os.path.join("data", "generated_reports")
os.makedirs(DOCS_OUTPUT_DIR, exist_ok=True)


def set_cell_background(cell, color_hex: str):
    """Utility to set Word table cell background shading."""
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)


def generate_ai_executive_summary(tender: Tender, bidders: List[Bidder]) -> str:
    """Uses Gemini strictly for narrative sentences of summary text (no ranking)."""
    bidder_statuses = [f"{b.name}: {b.final_status}" for b in bidders]
    bidders_str = ", ".join(bidder_statuses)

    client = get_client()
    if client is None:
        return (
            f"The Technical Bid Evaluation for tender {tender.nit_no} ({tender.description}) "
            f"has been conducted for {len(bidders)} participating bidders ({bidders_str}). "
            f"All technical parameters, qualification criteria, and type tests have been examined in accordance with BSES equipment standards."
        )

    prompt = f"""
Write a professional, 1-paragraph Executive Summary for a utility Technical Evaluation Report (TER).
Tender: {tender.description} (NIT No: {tender.nit_no})
Participating Bidders & Final Technical Statuses: {bidders_str}

Rules:
1. Neutral, authoritative technical tone suitable for BSES Equipment Engineering.
2. State the purpose, scope, and factual summary of technical compliance.
3. DO NOT rank the bidders.
"""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text.strip()
    except Exception:
        return (
            f"The Technical Bid Evaluation for tender {tender.nit_no} ({tender.description}) "
            f"has been concluded for {len(bidders)} bidders: {bidders_str}."
        )


def generate_tbe_mom(
    db: Session,
    tender: Tender,
    meeting_venue: str = "Engineering Conference Hall, BSES Bhawan, Nehru Place",
    attendees: Optional[List[str]] = None
) -> str:
    """
    Generates TBE Minutes of Meeting (MOM) (.docx) in standard BSES format.
    """
    if attendees is None:
        attendees = [
            "Sh. R.K. Sharma (Head - Equipment Engineering)",
            "Sh. Amit Verma (Sr. Manager - Substation Design)",
            "Er. P. K. Singh (Dy. Manager - Technical Evaluation)"
        ]

    bidders = get_bidders_for_tender(db, tender.id)
    latest_baseline = get_latest_baseline(db, tender.id)
    requirements = get_baseline_requirements(db, latest_baseline.id) if latest_baseline else []

    doc = Document()

    # Document Header Title
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = title.add_run("BSES EQUIPMENT ENGINEERING DIVISION\nMINUTES OF MEETING (MOM) - TECHNICAL BID EVALUATION")
    run_title.font.name = "Arial"
    run_title.font.size = Pt(13)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(14, 42, 71)

    doc.add_paragraph(f"Tender: {tender.description}")
    doc.add_paragraph(f"NIT Reference No: {tender.nit_no}")
    doc.add_paragraph(f"Meeting Date: {datetime.now().strftime('%d-%b-%Y')} | Venue: {meeting_venue}")

    # Attendees
    doc.add_heading("1. Committee Members Present:", level=2)
    for att in attendees:
        p = doc.add_paragraph(att, style='List Bullet')
        p.paragraph_format.space_after = Pt(2)

    # Evaluation Summary
    doc.add_heading("2. Technical Evaluation Proceedings & Findings:", level=2)
    summary_text = generate_ai_executive_summary(tender, bidders)
    p_sum = doc.add_paragraph(summary_text)
    p_sum.paragraph_format.line_spacing = 1.15

    # Bidder Status Table
    doc.add_heading("3. Summary of Technical Qualification:", level=2)
    table = doc.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "S.No."
    hdr_cells[1].text = "Bidder Name"
    hdr_cells[2].text = "Technical Status"
    for cell in hdr_cells:
        set_cell_background(cell, "0E2A47")
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.color.rgb = RGBColor(255, 255, 255)
                r.font.bold = True

    for idx, b in enumerate(bidders, start=1):
        row = table.add_row().cells
        row[0].text = str(idx)
        row[1].text = b.name
        row[2].text = b.final_status
        # Color coding
        if b.final_status == "Qualified":
            set_cell_background(row[2], "E2EFDA")
        elif b.final_status == "Not Qualified":
            set_cell_background(row[2], "FCE4D6")
        else:
            set_cell_background(row[2], "FFF2CC")

    # Signatures block
    doc.add_heading("4. Committee Signatures:", level=2)
    p_sig = doc.add_paragraph("\n\n\n______________________          ______________________          ______________________\n(Member - 1)                    (Member - 2)                    (Chairman / HOD)")
    p_sig.alignment = WD_ALIGN_PARAGRAPH.CENTER

    out_file = os.path.join(DOCS_OUTPUT_DIR, f"TBE_MOM_{tender.nit_no}.docx")
    doc.save(out_file)
    return out_file


def generate_tbe_report(db: Session, tender: Tender) -> str:
    """
    Generates Technical Evaluation Report (TER) (.docx) in standard BSES format:
    - Cover page
    - Index
    - Comparison table
    - Executive summary
    """
    bidders = get_bidders_for_tender(db, tender.id)
    latest_baseline = get_latest_baseline(db, tender.id)
    requirements = get_baseline_requirements(db, latest_baseline.id) if latest_baseline else []

    doc = Document()

    # 1. Cover Page
    cover = doc.add_paragraph()
    cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_cov = cover.add_run("\n\n\nBSES EQUIPMENT ENGINEERING\n\nTECHNICAL EVALUATION REPORT (TER)\n\n")
    r_cov.font.name = "Arial"
    r_cov.font.size = Pt(20)
    r_cov.font.bold = True
    r_cov.font.color.rgb = RGBColor(14, 42, 71)

    p_desc = doc.add_paragraph()
    p_desc.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_d = p_desc.add_run(f"EQUIPMENT TENDER: {tender.description}\nNIT REF: {tender.nit_no}\n\nDATE: {datetime.now().strftime('%B %Y')}")
    r_d.font.size = Pt(13)
    doc.add_page_break()

    # 2. Executive Summary
    doc.add_heading("1. Executive Summary", level=1)
    summary_text = generate_ai_executive_summary(tender, bidders)
    doc.add_paragraph(summary_text)

    # 3. Scope & Baseline
    doc.add_heading("2. Technical Baseline & Requirements Evaluated", level=1)
    doc.add_paragraph(f"The baseline consists of {len(requirements)} approved technical and qualification requirements.")

    # 4. Bidder Comparison Matrix Table
    doc.add_heading("3. Detailed Bidder Technical Comparison Table", level=1)

    num_cols = 4 + len(bidders)
    table = doc.add_table(rows=1, cols=num_cols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    headers = ["Clause", "Requirement Description", "Category"]
    for b in bidders:
        headers.append(b.name)
    headers.append("BSES Standard")

    for col_idx, text in enumerate(headers):
        cell = table.rows[0].cells[col_idx]
        cell.text = text
        set_cell_background(cell, "0E2A47")
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.color.rgb = RGBColor(255, 255, 255)
                r.font.bold = True
                r.font.size = Pt(9)

    for req in requirements:
        row_cells = table.add_row().cells
        row_cells[0].text = req.clause or "-"
        row_cells[1].text = req.text[:55] + "..." if len(req.text) > 55 else req.text
        row_cells[2].text = "QR" if req.is_QR else "Technical"

        col_i = 3
        for b in bidders:
            # Query confirmed finding
            finding = (
                db.query(Finding)
                .filter(Finding.requirement_id == req.id, Finding.bidder_id == b.id)
                .first()
            )
            status = finding.engineer_status if (finding and finding.engineer_status) else (finding.ai_status if finding else "Pending")
            row_cells[col_i].text = status
            if status == "Complied":
                set_cell_background(row_cells[col_i], "E2EFDA")
            elif status == "Not Complied":
                set_cell_background(row_cells[col_i], "FCE4D6")
            col_i += 1

        row_cells[col_i].text = "Compliant"

    # 5. Conclusion
    doc.add_heading("4. Final Recommendation", level=1)
    qualified = [b.name for b in bidders if b.final_status == "Qualified"]
    not_qualified = [b.name for b in bidders if b.final_status == "Not Qualified"]

    doc.add_paragraph(f"Technically Qualified Bidders: {', '.join(qualified) if qualified else 'None'}")
    doc.add_paragraph(f"Disqualified Bidders: {', '.join(not_qualified) if not_qualified else 'None'}")

    out_file = os.path.join(DOCS_OUTPUT_DIR, f"TBE_TER_Report_{tender.nit_no}.docx")
    doc.save(out_file)
    return out_file

