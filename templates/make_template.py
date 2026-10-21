"""
Creates the official Master TBE Template Excel file.
Follows the exact layout from Workflow & Developer Guide:
- Header block with Tender Info
- Column Structure: [S.No, Category, Clause, Technical Requirement, BSES Specified Value]
- Followed by dynamic Bidder Column Groups: [Offered Value, Compliance Status, Evidence / Remarks]
- Rows layout: Qualification Requirements (QR) first, then ONE BLANK ROW, then Other Requirements.
"""
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)
TBE_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "tbe_template.xlsx")


def create_master_tbe_template(target_path: str = TBE_TEMPLATE_PATH):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Technical Bid Evaluation"

    # Styling definitions
    navy_fill = PatternFill(start_color="0E2A47", end_color="0E2A47", fill_type="solid")
    gold_fill = PatternFill(start_color="D4AF37", end_color="D4AF37", fill_type="solid")
    white_bold = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    navy_bold = Font(name="Calibri", size=11, bold=True, color="0E2A47")
    thin_border = Border(
        left=Side(style='thin', color='B0B0B0'),
        right=Side(style='thin', color='B0B0B0'),
        top=Side(style='thin', color='B0B0B0'),
        bottom=Side(style='thin', color='B0B0B0')
    )

    # 1. Tender Title Banner
    ws.merge_cells("A1:K1")
    title_cell = ws["A1"]
    title_cell.value = "BSES EQUIPMENT ENGINEERING - TECHNICAL BID EVALUATION (TBE)"
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.fill = navy_fill
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    # 2. Metadata info rows
    ws["A2"] = "NIT Number:"
    ws["B2"] = "{{NIT_NO}}"
    ws["A3"] = "Tender Description:"
    ws["B3"] = "{{DESCRIPTION}}"
    ws["A4"] = "Evaluation Date:"
    ws["B4"] = "{{EVAL_DATE}}"

    for r in range(2, 5):
        ws[f"A{r}"].font = Font(name="Calibri", size=10, bold=True)
        ws[f"B{r}"].font = Font(name="Calibri", size=10)

    # 3. Main Headers (Row 6)
    headers = [
        ("S.No", 8),
        ("Category", 15),
        ("Clause No.", 12),
        ("Technical Requirement", 45),
        ("BSES Specification", 25)
    ]

    for col_idx, (hdr, width) in enumerate(headers, start=1):
        cell = ws.cell(row=6, column=col_idx, value=hdr)
        cell.font = white_bold
        cell.fill = navy_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width

    ws.row_dimensions[6].height = 28
    wb.save(target_path)
    wb.close()
    return target_path


if __name__ == "__main__":
    create_master_tbe_template()

