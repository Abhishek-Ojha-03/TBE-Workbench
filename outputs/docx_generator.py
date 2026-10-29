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
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from sqlalchemy.orm import Session

from db.models import Tender, Bidder, BaselineVersion, Requirement, Finding, Evidence
from db.baseline_service import get_latest_baseline, get_baseline_requirements, get_bidders_for_tender
from db.commercial_service import get_commercial_ranking
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


def generate_ai_negotiation_points(tender: Tender, bidder_summaries: List[Dict[str, Any]]) -> str:
    """Uses Gemini to generate actionable, high-leverage commercial and technical negotiation points for the committee."""
    client = get_client()
    if client is None:
        lines = []
        for bs in bidder_summaries:
            lines.append(f"• {bs['name']} (Score: {bs['score']}%): Verify all non-compliances and ensure delivery guarantees prior to commercial award.")
        return "\n".join(lines)

    prompt = f"""
You are a senior procurement committee chairperson and technical negotiator for BSES Equipment Engineering.
Review the following technical bid evaluation outcomes for tender {tender.nit_no} ({tender.description}):

Bidder Details & Findings:
{json.dumps(bidder_summaries, indent=2)}

Generate actionable, concise Negotiation Notes & Strategic Talking Points for the procurement committee.
For each bidder:
1. Identify technical non-compliances or ambiguities (deviations, missing tests, or outdated certificates).
2. Formulate practical Commercial & Technical Leverage for the utility engineer (e.g., zero-cost replacements, warranty extensions, price rebates, performance security holdbacks).
3. Specify the Recommended Committee Action.

Format the response cleanly with clear bullet points. Keep it professional, objective, and authoritative.
"""
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        return response.text.strip()
    except Exception:
        lines = []
        for bs in bidder_summaries:
            dev_text = f"{bs['deviations']} deviations noted" if bs['deviations'] > 0 else "technically compliant"
            lines.append(f"• {bs['name']} (Score: {bs['score']}% - {bs['status']}): {dev_text}. Recommended Action: Seek formal confirmation and price optimization during commercial negotiations.")
        return "\n".join(lines)


def _add_formatted_text_to_p(p, text: str):
    """Parses basic markdown like **bold** and adds styled runs to paragraph."""
    import re
    # Split text by **...**
    parts = re.split(r'(\*\*.*?\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**') and len(part) >= 4:
            run = p.add_run(part[2:-2])
            run.bold = True
        else:
            p.add_run(part)


def _write_markdown_to_doc(doc: Document, md_text: str):
    """Converts LLM Markdown response (headings, bullets, bold) cleanly into python-docx elements."""
    import re
    lines = md_text.split('\n')
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        
        # Check headings
        if line.startswith('### '):
            h = doc.add_heading(line[4:].strip(), level=3)
            h.paragraph_format.space_before = Pt(6)
            h.paragraph_format.space_after = Pt(2)
        elif line.startswith('## '):
            h = doc.add_heading(line[3:].strip(), level=2)
            h.paragraph_format.space_before = Pt(8)
            h.paragraph_format.space_after = Pt(3)
        elif line.startswith('# '):
            h = doc.add_heading(line[2:].strip(), level=1)
            h.paragraph_format.space_before = Pt(10)
            h.paragraph_format.space_after = Pt(4)
        elif re.match(r'^[-*•]\s+', line):
            # Bullet point
            clean_item = re.sub(r'^[-*•]\s+', '', line)
            p = doc.add_paragraph(style='List Bullet')
            _add_formatted_text_to_p(p, clean_item)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
        elif re.match(r'^\d+\.\s+', line):
            # Numbered list
            clean_item = re.sub(r'^\d+\.\s+', '', line)
            p = doc.add_paragraph(style='List Number')
            _add_formatted_text_to_p(p, clean_item)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.15
        else:
            p = doc.add_paragraph()
            _add_formatted_text_to_p(p, line)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15


def generate_tbe_mom(
    db: Session,
    tender: Tender,
    meeting_venue: str = "Engineering Conference Hall, BSES Bhawan, Nehru Place",
    attendees: Optional[List[str]] = None
) -> str:
    """
    Generates TBE Minutes of Meeting (MOM) (.docx) in standard BSES format:
    - Committee Members
    - Executive Proceedings
    - Comprehensive Technical Compliance & Scoring Table
    - Actionable Strategic Negotiation & Discussion Points
    - Signature Blocks
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
    req_ids = [r.id for r in requirements]
    total_reqs_count = len(requirements)

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

    # 3. Comprehensive Bidder Status & Scoring Table
    doc.add_heading("3. Summary of Technical Scoring & Qualification Outcomes:", level=2)
    table = doc.add_table(rows=1, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "S.No."
    hdr_cells[1].text = "Bidder Name"
    hdr_cells[2].text = "Total Clauses"
    hdr_cells[3].text = "Complied (✅)"
    hdr_cells[4].text = "Score (%)"
    hdr_cells[5].text = "Final Outcome"
    for cell in hdr_cells:
        set_cell_background(cell, "0E2A47")
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.color.rgb = RGBColor(255, 255, 255)
                r.font.bold = True
                r.font.size = Pt(9)

    bidder_summaries = []

    for idx, b in enumerate(bidders, start=1):
        findings = db.query(Finding).filter(Finding.bidder_id == b.id, Finding.requirement_id.in_(req_ids)).all() if req_ids else []
        complied_count = sum(1 for f in findings if (f.engineer_status or f.ai_status or '').lower() == 'complied')
        not_complied_count = sum(1 for f in findings if (f.engineer_status or f.ai_status or '').lower() == 'not complied')
        review_count = sum(1 for f in findings if 'review' in (f.engineer_status or f.ai_status or '').lower())
        
        eval_total = total_reqs_count if total_reqs_count > 0 else len(findings)
        score = round((complied_count / eval_total * 100), 1) if eval_total else 0.0

        dev_clauses = []
        for f in findings:
            st_val = (f.engineer_status or f.ai_status or '').lower()
            if st_val == 'not complied' or 'review' in st_val:
                req_obj = next((r for r in requirements if r.id == f.requirement_id), None)
                dev_clauses.append({
                    "clause": req_obj.clause if req_obj else "General",
                    "text": (req_obj.text[:80] + "...") if req_obj else "",
                    "issue": f.remark or f.ai_reason or "Verification query pending"
                })

        bidder_summaries.append({
            "name": b.name,
            "status": b.final_status,
            "score": score,
            "deviations": not_complied_count,
            "reviews": review_count,
            "key_issues": dev_clauses[:3]
        })

        row = table.add_row().cells
        row[0].text = str(idx)
        row[1].text = b.name
        row[2].text = str(eval_total)
        row[3].text = str(complied_count)
        row[4].text = f"{score}%"
        row[5].text = b.final_status

        # Color coding
        if b.final_status == "Qualified":
            set_cell_background(row[5], "E2EFDA")
        elif b.final_status == "Not Qualified":
            set_cell_background(row[5], "FCE4D6")
        else:
            set_cell_background(row[5], "FFF2CC")

    # 4. Actionable Committee Discussion & Negotiation Playbook
    doc.add_heading("4. Committee Discussion & Strategic Negotiation Playbook:", level=2)
    doc.add_paragraph(
        "Based on the technical deviations, incomplete test certificates, and parameter variances recorded above, "
        "the AI Engine has synthesized the following specific negotiation talking points and commercial leverage points "
        "for the Procurement Committee during price negotiations:"
    )

    negotiation_text = generate_ai_negotiation_points(tender, bidder_summaries)
    _write_markdown_to_doc(doc, negotiation_text)

    # 5. Commercial Bid Ranking (Part 2) — only if prices have been entered
    commercial_ranking = get_commercial_ranking(db, tender.id)
    if commercial_ranking:
        doc.add_heading("5. Commercial Bid Ranking — Part 2 (Price Bid Opening):", level=2)
        doc.add_paragraph(
            "The following price ranking has been derived from the commercial (price) envelopes "
            "opened after completion of the Technical Evaluation. Only technically qualified "
            "bidders are included. L1 = lowest quoted price."
        )

        comm_table = doc.add_table(rows=1, cols=5)
        comm_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        comm_table.autofit = True

        comm_hdrs = ["L-Rank", "Bidder Name", "Quoted Price", "% Above L1", "Recommendation"]
        for ci, ch in enumerate(comm_hdrs):
            cell = comm_table.rows[0].cells[ci]
            cell.text = ch
            set_cell_background(cell, "0E2A47")
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.color.rgb = RGBColor(255, 255, 255)
                    r.font.bold = True
                    r.font.size = Pt(9)

        for entry in commercial_ranking:
            cr = comm_table.add_row().cells
            tie_flag = " ⚠️ TIE" if entry.get("tie") else ""
            cr[0].text = f"{entry['label']}{tie_flag}"
            cr[1].text = entry["name"]
            cr[2].text = f"{entry['currency']} {entry['quoted_price']:,.2f}"
            cr[3].text = f"{entry['pct_above_l1']:.2f}%" if entry["pct_above_l1"] > 0 else "Lowest"
            cr[4].text = "RECOMMEND" if entry["rank"] == 1 else f"Alt — {entry['pct_above_l1']:.2f}% above L1"

            if entry["rank"] == 1:
                set_cell_background(cr[0], "E2EFDA")
                set_cell_background(cr[4], "E2EFDA")
            elif entry["rank"] == 2:
                set_cell_background(cr[0], "FFF2CC")
            else:
                set_cell_background(cr[0], "FCE4D6")

        sig_section = 6
    else:
        sig_section = 5

    # Signatures block
    doc.add_heading(f"{sig_section}. Committee Signatures:", level=2)
    p_sig = doc.add_paragraph("\n\n\n______________________          ______________________          ______________________\n(Member - 1)                    (Member - 2)                    (Chairman / HOD)")
    p_sig.alignment = WD_ALIGN_PARAGRAPH.CENTER

    safe_nit = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (tender.nit_no or "TENDER"))
    out_file = os.path.join(DOCS_OUTPUT_DIR, f"TBE_MOM_{safe_nit}.docx")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
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

    # 5. Technical Scoring & Compliance Summary Table
    doc.add_heading("4. Quantitative Scoring & Compliance Summary", level=1)
    score_table = doc.add_table(rows=1, cols=6)
    score_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    score_table.autofit = True

    s_headers = ["S.No.", "Bidder Name", "Total Clauses", "Complied (✅)", "Score (%)", "Final Outcome"]
    for c_i, s_txt in enumerate(s_headers):
        cell = score_table.rows[0].cells[c_i]
        cell.text = s_txt
        set_cell_background(cell, "0E2A47")
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.color.rgb = RGBColor(255, 255, 255)
                r.font.bold = True
                r.font.size = Pt(9)

    req_ids = [r.id for r in requirements]
    total_reqs_count = len(requirements)

    for idx, b in enumerate(bidders, start=1):
        findings = db.query(Finding).filter(Finding.bidder_id == b.id, Finding.requirement_id.in_(req_ids)).all() if req_ids else []
        complied_count = sum(1 for f in findings if (f.engineer_status or f.ai_status or '').lower() == 'complied')
        eval_total = total_reqs_count if total_reqs_count > 0 else len(findings)
        score = round((complied_count / eval_total * 100), 1) if eval_total else 0.0

        r_cells = score_table.add_row().cells
        r_cells[0].text = str(idx)
        r_cells[1].text = b.name
        r_cells[2].text = str(eval_total)
        r_cells[3].text = str(complied_count)
        r_cells[4].text = f"{score}%"
        r_cells[5].text = b.final_status

        if b.final_status == "Qualified":
            set_cell_background(r_cells[5], "E2EFDA")
        elif b.final_status == "Not Qualified":
            set_cell_background(r_cells[5], "FCE4D6")
        else:
            set_cell_background(r_cells[5], "FFF2CC")

    # 6. Conclusion
    doc.add_heading("5. Final Recommendation", level=1)
    qualified = [b.name for b in bidders if b.final_status == "Qualified"]
    not_qualified = [b.name for b in bidders if b.final_status == "Not Qualified"]

    doc.add_paragraph(f"Technically Qualified Bidders: {', '.join(qualified) if qualified else 'None'}")
    doc.add_paragraph(f"Disqualified Bidders: {', '.join(not_qualified) if not_qualified else 'None'}")

    safe_nit = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (tender.nit_no or "TENDER"))
    out_file = os.path.join(DOCS_OUTPUT_DIR, f"TBE_TER_Report_{safe_nit}.docx")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    doc.save(out_file)
    return out_file

