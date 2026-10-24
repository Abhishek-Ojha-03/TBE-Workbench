"""
Working Excel Generator (Step 6)
Rules:
1. Open the template file with openpyxl and fill its cells.
2. DO NOT create the sheet from nothing, or layout will drift from the original.
3. Structure: QR rows first, then ONE BLANK ROW, then other requirements.
4. One column group per bidder: [Offered Value, Compliance Status, Evidence / Remarks]
5. Keep a map of which requirement and bidder goes to which cell.
"""
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from typing import Dict, Tuple, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from db.models import Tender, BaselineVersion, Requirement, Bidder, Finding, Evidence
from db.baseline_service import get_latest_baseline, get_baseline_requirements, get_bidders_for_tender
from templates.make_template import TBE_TEMPLATE_PATH, create_master_tbe_template

OUTPUTS_DIR = os.path.join("data", "generated_excel")
os.makedirs(OUTPUTS_DIR, exist_ok=True)


class WorkingExcelGenerator:
    """
    Handles generation and cell mapping for the working TBE Excel sheet.
    """
    def __init__(self, template_path: str = TBE_TEMPLATE_PATH):
        if not os.path.exists(template_path):
            create_master_tbe_template(template_path)
        self.template_path = template_path

    def generate_working_excel(
        self,
        db: Session,
        tender: Tender,
        output_filename: Optional[str] = None
    ) -> Tuple[str, Dict[Tuple[int, int], Tuple[int, int]]]:
        """
        Generates the working TBE Excel populated with baseline requirements and bidder groups.
        Returns:
            - output_file_path: path to the saved populated Excel file.
            - cell_map: Dict mapping (requirement_id, bidder_id) -> (row, compliance_col)
        """
        wb = openpyxl.load_workbook(self.template_path)
        ws = wb.active

        # 1. Fill Tender Metadata
        ws["B2"] = tender.nit_no
        ws["B3"] = tender.description
        ws["B4"] = datetime.now().strftime("%d-%b-%Y %H:%M")

        # Styling presets
        thin_border = Border(
            left=Side(style='thin', color='D0D0D0'),
            right=Side(style='thin', color='D0D0D0'),
            top=Side(style='thin', color='D0D0D0'),
            bottom=Side(style='thin', color='D0D0D0')
        )
        gold_fill = PatternFill(start_color="F2E6C3", end_color="F2E6C3", fill_type="solid")
        header_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        white_bold = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        normal_font = Font(name="Calibri", size=10)
        bold_font = Font(name="Calibri", size=10, bold=True)

        # 2. Add Bidder Column Groups (starting at column 6: F, G, H...)
        bidders = get_bidders_for_tender(db, tender.id)
        start_col = 6  # Col F

        bidder_col_map: Dict[int, int] = {}  # bidder_id -> compliance_status_col

        for b_idx, bidder in enumerate(bidders):
            b_start = start_col + (b_idx * 3)
            b_end = b_start + 2

            # Merge top header for Bidder Name & Qualification Status (Row 5)
            ws.merge_cells(start_row=5, start_column=b_start, end_row=5, end_column=b_end)
            status_tag = (bidder.final_status or "Pending").upper()
            b_cell = ws.cell(row=5, column=b_start, value=f"BIDDER {b_idx+1}: {bidder.name.upper()}  [{status_tag}]")
            b_cell.font = white_bold
            b_cell.fill = header_fill
            b_cell.alignment = Alignment(horizontal="center", vertical="center")

            # Sub-headers (Row 6)
            sub_headers = ["Offered Value", "Compliance Status", "Evidence / Page Ref"]
            for sub_idx, sub_hdr in enumerate(sub_headers):
                c = ws.cell(row=6, column=b_start + sub_idx, value=sub_hdr)
                c.font = white_bold
                c.fill = header_fill
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                c.border = thin_border
                col_letter = get_column_letter(b_start + sub_idx)
                ws.column_dimensions[col_letter].width = 22 if sub_idx != 1 else 18

            # Compliance status column is at b_start + 1
            bidder_col_map[bidder.id] = b_start + 1

        # 3. Populate Requirements: QR first, then ONE BLANK ROW, then others
        latest_baseline = get_latest_baseline(db, tender.id)
        if not latest_baseline:
            raise ValueError(f"No baseline approved for Tender {tender.nit_no}.")

        all_reqs = get_baseline_requirements(db, latest_baseline.id)
        qr_reqs = [r for r in all_reqs if r.is_QR and not r.not_applicable]
        other_reqs = [r for r in all_reqs if not r.is_QR and not r.not_applicable]

        current_row = 7
        cell_map: Dict[Tuple[int, int], Tuple[int, int]] = {}  # (req_id, bidder_id) -> (row, col)

        # Set proper column widths for readability and prevent truncated display
        ws.column_dimensions['A'].width = 8    # S.No
        ws.column_dimensions['B'].width = 20   # Category
        ws.column_dimensions['C'].width = 12   # Clause No.
        ws.column_dimensions['D'].width = 45   # Technical Requirement (Full)
        ws.column_dimensions['E'].width = 45   # BSES Specification (Full)

        # Helper to write requirement row
        def write_req_row(sno: int, req: Requirement, is_qr_section: bool):
            nonlocal current_row
            ws.cell(row=current_row, column=1, value=sno).alignment = Alignment(horizontal="center", vertical="top")
            ws.cell(row=current_row, column=2, value="Qualification (QR)" if is_qr_section else "Technical Spec").alignment = Alignment(vertical="top")
            ws.cell(row=current_row, column=3, value=req.clause or "-").alignment = Alignment(horizontal="center", vertical="top")
            ws.cell(row=current_row, column=4, value=req.text).alignment = Alignment(wrap_text=True, vertical="top")
            ws.cell(row=current_row, column=5, value=req.text).alignment = Alignment(wrap_text=True, vertical="top")

            for col in range(1, 6):
                cell = ws.cell(row=current_row, column=col)
                cell.font = normal_font
                cell.border = thin_border
                if is_qr_section:
                    cell.fill = gold_fill

            # Map cell coordinates for each bidder and fill findings if available
            for b in bidders:
                status_col = bidder_col_map[b.id]
                cell_map[(req.id, b.id)] = (current_row, status_col)

                # Look up existing finding for this (requirement, bidder)
                finding = db.query(Finding).filter(
                    Finding.requirement_id == req.id,
                    Finding.bidder_id == b.id
                ).first()

                offered_val = ""
                status_val = ""
                evidence_val = ""

                if finding:
                    status_val = finding.engineer_status or finding.ai_status or ""
                    evidence_val = finding.remark or ""
                    # Check for attached quoted evidence
                    if finding.evidences:
                        ev = finding.evidences[0]
                        p_num = ev.page.page_number if ev.page else ""
                        d_name = ev.page.document.file_name if (ev.page and ev.page.document) else ""
                        offered_val = ev.quoted_text or ""
                        if d_name:
                            evidence_val = f"[{d_name} p.{p_num}] {evidence_val}"

                # Fill the 3 bidder columns: Offered Value, Status, Evidence
                vals = [offered_val, status_val, evidence_val]
                for offset, val in zip(range(-1, 2), vals):
                    target_cell = ws.cell(row=current_row, column=status_col + offset, value=val)
                    target_cell.border = thin_border
                    target_cell.alignment = Alignment(vertical="center", wrap_text=True)
                    target_cell.font = normal_font

                    # Apply status color styling to Compliance Status cell
                    if offset == 0 and status_val:
                        if status_val == "Complied":
                            target_cell.fill = PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid")
                            target_cell.font = Font(name="Calibri", size=10, bold=True, color="155724")
                        elif status_val == "Not Complied":
                            target_cell.fill = PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid")
                            target_cell.font = Font(name="Calibri", size=10, bold=True, color="721C24")
                        elif "Review" in status_val:
                            target_cell.fill = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
                            target_cell.font = Font(name="Calibri", size=10, bold=True, color="856404")

            current_row += 1

        # A. Write QR rows first
        s_no = 1
        for req in qr_reqs:
            write_req_row(s_no, req, is_qr_section=True)
            s_no += 1

        # B. Write ONE BLANK ROW separating QR and Other Requirements
        if qr_reqs and other_reqs:
            for c in range(1, start_col + (len(bidders) * 3)):
                blank_cell = ws.cell(row=current_row, column=c)
                blank_cell.fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
            ws.row_dimensions[current_row].height = 12
            current_row += 1

        # C. Write Other Requirements
        for req in other_reqs:
            write_req_row(s_no, req, is_qr_section=False)
            s_no += 1

        # D. Add Final Qualification Summary Block at the bottom of the matrix
        total_cols = start_col + (len(bidders) * 3) - 1

        # 1. Blank separator row
        current_row += 1
        for c in range(1, total_cols + 1):
            ws.cell(row=current_row, column=c).fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        ws.row_dimensions[current_row].height = 6
        current_row += 1

        # 2. Compliance Score Row
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=5)
        score_hdr = ws.cell(row=current_row, column=1, value="TOTAL CLAUSES COMPLIED (ACCURACY)")
        score_hdr.font = bold_font
        score_hdr.alignment = Alignment(horizontal="right", vertical="center")
        score_hdr.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        active_req_ids = [r.id for r in all_reqs]
        total_req_count = len(active_req_ids)

        for b in bidders:
            b_status_col = bidder_col_map[b.id]
            b_findings = db.query(Finding).filter(Finding.bidder_id == b.id, Finding.requirement_id.in_(active_req_ids)).all()
            comp_cnt = sum(1 for f in b_findings if (f.engineer_status or f.ai_status) == "Complied")
            not_comp_cnt = sum(1 for f in b_findings if (f.engineer_status or f.ai_status) == "Not Complied")
            pct = round((comp_cnt / total_req_count) * 100, 1) if total_req_count > 0 else 0

            # Merge 3 columns per bidder for score
            b_s = b_status_col - 1
            b_e = b_status_col + 1
            ws.merge_cells(start_row=current_row, start_column=b_s, end_row=current_row, end_column=b_e)
            sc_cell = ws.cell(row=current_row, column=b_s, value=f"{comp_cnt}/{total_req_count} Complied ({pct}%)")
            sc_cell.font = bold_font
            sc_cell.alignment = Alignment(horizontal="center", vertical="center")
            sc_cell.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
            for col_i in range(b_s, b_e + 1):
                ws.cell(row=current_row, column=col_i).border = thin_border

        for c_i in range(1, 6):
            ws.cell(row=current_row, column=c_i).border = thin_border
        ws.row_dimensions[current_row].height = 24
        current_row += 1

        # 3. Final TBE Status Row (The Primary Verdict!)
        ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=5)
        fin_hdr = ws.cell(row=current_row, column=1, value="FINAL TBE QUALIFICATION RESULT")
        fin_hdr.font = Font(name="Calibri", size=11, bold=True, color="1E3A8A")
        fin_hdr.alignment = Alignment(horizontal="right", vertical="center")
        fin_hdr.fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

        for b in bidders:
            b_status_col = bidder_col_map[b.id]
            f_status = (b.final_status or "Pending").strip()

            b_s = b_status_col - 1
            b_e = b_status_col + 1
            ws.merge_cells(start_row=current_row, start_column=b_s, end_row=current_row, end_column=b_e)
            st_cell = ws.cell(row=current_row, column=b_s, value=f_status.upper())
            st_cell.alignment = Alignment(horizontal="center", vertical="center")

            if f_status == "Qualified":
                st_cell.fill = PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid")
                st_cell.font = Font(name="Calibri", size=11, bold=True, color="155724")
            elif f_status == "Not Qualified":
                st_cell.fill = PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid")
                st_cell.font = Font(name="Calibri", size=11, bold=True, color="721C24")
            else:
                st_cell.fill = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
                st_cell.font = Font(name="Calibri", size=11, bold=True, color="856404")

            for col_i in range(b_s, b_e + 1):
                ws.cell(row=current_row, column=col_i).border = thin_border

        for c_i in range(1, 6):
            ws.cell(row=current_row, column=c_i).border = thin_border
        ws.row_dimensions[current_row].height = 28
        current_row += 1

        # 4. Save file
        if not output_filename:
            output_filename = f"TBE_Working_{tender.nit_no}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = os.path.join(OUTPUTS_DIR, output_filename)
        wb.save(output_path)
        wb.close()

        return output_path, cell_map

