"""
Generates 6 complete test bidders, each with all 10 standard technical documents
plus the 11th Commercial Price Schedule, packaged into a ZIP archive.
"""
import os
import io
import sys
import zipfile
import fitz
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.generate_50_synthetic_bidders import build_docs_for_bidder, make_pdf_from_story

def generate_full_11_doc_commercial_zip():
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('T', parent=styles['Heading1'], fontSize=13, leading=16, textColor=colors.navy)
    sub_style = ParagraphStyle('S', parent=styles['Heading2'], fontSize=10, leading=13, textColor=colors.darkblue)
    body_style = ParagraphStyle('B', parent=styles['Normal'], fontSize=9, leading=12)

    # 6 Bidders with full 10-document profiles + Commercial Price specifications
    bidders_spec = [
        {
            "idx": 1,
            "folder": "Bidder_01_Siemens",
            "name": "Siemens Energy India Ltd",
            "profile": {
                "is_scan": False,
                "voltage": "11 kV",
                "breaking_current": "25 kA",
                "breaking_duration": "3 seconds",
                "frequency": "50 Hz",
                "protection": "IP 4X",
                "aux_voltage": "110 V DC",
                "deviation_status": "NIL",
                "test_standards": "IS 13118 / IEC 62271-100",
                "test_date": "14-06-2023",
                "turnover_y1": 42.5,
                "turnover_y2": 48.2,
                "turnover_y3": 52.8,
                "turnover_avg": 47.8,
                "supply_qty": 450,
                "supply_total": 550,
                "missing_docs": []
            },
            "commercial": {
                "has_price": True,
                "price_str": "INR 1,050,000.00",
                "price_num": 1050000.0,
                "comment": "Lowest bidder (Expected L1)"
            }
        },
        {
            "idx": 2,
            "folder": "Bidder_02_ABB",
            "name": "ABB Power Products & Systems",
            "profile": {
                "is_scan": False,
                "voltage": "11 kV",
                "breaking_current": "25 kA",
                "breaking_duration": "3 seconds",
                "frequency": "50 Hz",
                "protection": "IP 4X",
                "aux_voltage": "110 V DC",
                "deviation_status": "NIL",
                "test_standards": "IS 13118 / IEC 62271-100",
                "test_date": "20-08-2023",
                "turnover_y1": 55.0,
                "turnover_y2": 61.4,
                "turnover_y3": 68.0,
                "turnover_avg": 61.4,
                "supply_qty": 600,
                "supply_total": 700,
                "missing_docs": []
            },
            "commercial": {
                "has_price": True,
                "price_str": "INR 1,120,000.00",
                "price_num": 1120000.0,
                "comment": "Second lowest bidder (Expected L2)"
            }
        },
        {
            "idx": 3,
            "folder": "Bidder_03_Schneider",
            "name": "Schneider Electric Grid Ltd",
            "profile": {
                "is_scan": False,
                "voltage": "11 kV",
                "breaking_current": "25 kA",
                "breaking_duration": "3 seconds",
                "frequency": "50 Hz",
                "protection": "IP 4X",
                "aux_voltage": "110 V DC",
                "deviation_status": "NIL",
                "test_standards": "IS 13118 / IEC 62271-100",
                "test_date": "10-03-2024",
                "turnover_y1": 39.0,
                "turnover_y2": 44.5,
                "turnover_y3": 47.0,
                "turnover_avg": 43.5,
                "supply_qty": 380,
                "supply_total": 480,
                "missing_docs": []
            },
            "commercial": {
                "has_price": True,
                "price_str": "INR 1,185,000.00",
                "price_num": 1185000.0,
                "comment": "Tied for L3"
            }
        },
        {
            "idx": 4,
            "folder": "Bidder_04_LT",
            "name": "L&T Heavy Electrical Division",
            "profile": {
                "is_scan": False,
                "voltage": "11 kV",
                "breaking_current": "25 kA",
                "breaking_duration": "3 seconds",
                "frequency": "50 Hz",
                "protection": "IP 4X",
                "aux_voltage": "110 V DC",
                "deviation_status": "NIL",
                "test_standards": "IS 13118 / IEC 62271-100",
                "test_date": "15-11-2023",
                "turnover_y1": 80.0,
                "turnover_y2": 95.0,
                "turnover_y3": 110.0,
                "turnover_avg": 95.0,
                "supply_qty": 850,
                "supply_total": 950,
                "missing_docs": []
            },
            "commercial": {
                "has_price": True,
                "price_str": "INR 1,185,000.00",
                "price_num": 1185000.0,
                "comment": "Tied for L3"
            }
        },
        {
            "idx": 5,
            "folder": "Bidder_05_BHEL",
            "name": "BHEL Industrial Systems",
            "profile": {
                "is_scan": False,
                "voltage": "11 kV",
                "breaking_current": "25 kA",
                "breaking_duration": "3 seconds",
                "frequency": "50 Hz",
                "protection": "IP 4X",
                "aux_voltage": "110 V DC",
                "deviation_status": "NIL",
                "test_standards": "IS 13118 / IEC 62271-100",
                "test_date": "05-01-2024",
                "turnover_y1": 120.0,
                "turnover_y2": 135.0,
                "turnover_y3": 140.0,
                "turnover_avg": 131.6,
                "supply_qty": 1200,
                "supply_total": 1300,
                "missing_docs": []
            },
            "commercial": {
                "has_price": False,
                "price_str": None,
                "price_num": None,
                "comment": "Price envelope submitted separately / Price Not Mentioned"
            }
        },
        {
            "idx": 6,
            "folder": "Bidder_06_Kirloskar",
            "name": "Kirloskar Switchgear Systems",
            "profile": {
                "is_scan": False,
                "voltage": "11 kV",
                "breaking_current": "20 kA",
                "breaking_duration": "3 seconds",
                "frequency": "50 Hz",
                "protection": "IP 4X",
                "aux_voltage": "110 V DC",
                "deviation_status": "20 kA for 3 seconds offered instead of 25 kA",
                "test_standards": "IS 13118 / IEC 62271-100",
                "test_date": "18-09-2023",
                "turnover_y1": 35.0,
                "turnover_y2": 38.0,
                "turnover_y3": 41.0,
                "turnover_avg": 38.0,
                "supply_qty": 300,
                "supply_total": 400,
                "missing_docs": []
            },
            "commercial": {
                "has_price": True,
                "price_str": "INR 980,000.00",
                "price_num": 980000.0,
                "comment": "Deviates to 20 kA -> Not Qualified"
            }
        }
    ]

    zip_path = os.path.join("test_data", "6_commercial_test_bidders.zip")
    os.makedirs("test_data", exist_ok=True)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for b in bidders_spec:
            folder = b["folder"]
            name = b["name"]

            # 1 to 10: Standard Technical Documents
            docs_dict = build_docs_for_bidder(b["idx"], name, b["profile"])
            for doc_name, pdf_bytes in docs_dict.items():
                zf.writestr(f"{folder}/{doc_name}", pdf_bytes)

            # 11: Commercial Price Schedule / Quotation
            comm = b["commercial"]
            if comm["has_price"]:
                comm_story = [
                    Paragraph(f"<b>{name.upper()}</b>", title_style),
                    Paragraph("COMMERCIAL PRICE SCHEDULE & QUOTATION (PART-2)", sub_style),
                    Paragraph("Tender: BSES Equipment Engineering - NIT No. BSES/EE/2026/014", body_style),
                    Paragraph("Supply of 11kV Indoor VCB Switchgear Panels", body_style),
                    Spacer(1, 8),
                    Paragraph("We hereby submit our commercial price bid as follows:", body_style),
                    Spacer(1, 6),
                    Paragraph("• Equipment Description: 11kV 630A 25kA Indoor VCB Panels", body_style),
                    Paragraph("• Scope: Complete design, manufacture, testing, packing, supply & delivery", body_style),
                    Spacer(1, 6),
                    Paragraph(f"<b>Total Lump Sum Quoted Price (Ex-Works inclusive of all taxes): {comm['price_str']}</b>", body_style),
                    Paragraph(f"<b>Total Quoted Price: {comm['price_str']}</b>", body_style),
                    Spacer(1, 8),
                    Paragraph("Terms: Prices are firm and valid for 120 days from opening.", body_style),
                    Spacer(1, 12),
                    Paragraph(f"For {name}<br/><b>Commercial Director & Authorized Signatory</b>", body_style)
                ]
            else:
                comm_story = [
                    Paragraph(f"<b>{name.upper()}</b>", title_style),
                    Paragraph("COMMERCIAL ENVELOPE UNDERTAKING", sub_style),
                    Paragraph("Tender: BSES Equipment Engineering - NIT No. BSES/EE/2026/014", body_style),
                    Spacer(1, 8),
                    Paragraph("We confirm that our Commercial Price Bid has been sealed and submitted in a separate physical/electronic envelope per two-envelope bidding procedure.", body_style),
                    Paragraph("No price quotation figures are enclosed in this technical folder.", body_style),
                    Spacer(1, 12),
                    Paragraph(f"For {name}<br/><b>Authorized Signatory</b>", body_style)
                ]

            comm_pdf = make_pdf_from_story(comm_story, is_scan=False)
            zf.writestr(f"{folder}/11_Commercial_Price_Schedule.pdf", comm_pdf)

    print(f"Successfully generated 6 complete bidders with all 11 documents into: {zip_path}")
    print(f"Archive size: {os.path.getsize(zip_path)} bytes")

if __name__ == "__main__":
    generate_full_11_doc_commercial_zip()
