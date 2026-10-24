"""
50 Synthetic Bidders Generator for BSES 11kV VCB Tender
Creates:
1. 50 separate bidder folders under test_data/synthetic_50_bidders/
2. All 10 mandatory documents per bidder (Technical Offer, Deviation Sheet, GTP, Type Test Report,
   Balance Sheets, Credentials, Testing Facility, Self Declaration, PBG Undertaking, QAP)
3. Mix of 25 Digital Text PDFs + 25 Scanned Image PDFs
4. GROUND_TRUTH_ANSWER_KEY.csv containing the exact expected evaluation for every single clause.
"""

import os
import io
import csv
import fitz
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

BASE_DIR = os.path.join("test_data", "synthetic_50_bidders")
os.makedirs(BASE_DIR, exist_ok=True)

COMPANY_NAMES = [
    "Apex Power Grid Solutions Ltd", "Bharat Heavy Electricals & Switchgear", "Crompton Industrial Controls",
    "Delta High Voltage Systems", "Energo Switchgear Technologies", "Falcon Power Apparatus Pvt Ltd",
    "Ganga Switchgear & Transformers", "Havells Grid Equipment Ltd", "Indus Electrical Infrastructure",
    "Jupiter High Tech Switchgears", "Kirloskar Power Systems Ltd", "L&T Electrical Power Division",
    "Mahindra Grid Systems", "Nova Electro Mechanicals", "Omega High Voltage Controls",
    "Premier Power Equipment Pvt Ltd", "Quantum Grid Solutions", "Reliance Power Systems Ltd",
    "Schneider Power Distribution Ltd", "Torrent Electrical Apparatus", "Ultra Grid Technologies",
    "Vanguard Switchgear Systems", "Western High Voltage Ltd", "Zenith Power & Infra Ltd",
    "Ambience Electrical Equipments", "Bhavani Switchgear Works", "Century Power Solutions",
    "Dynamo Grid Apparatus Ltd", "Electra Switchgears Pvt Ltd", "Frontier High Voltage Systems",
    "Global Power & Automation", "Heritage Electrical Works", "Imperial Grid Controls",
    "Jaypee Electricals Ltd", "Kaveri Power Equipments", "Logix Switchgear Infrastructure",
    "Matrix High Voltage Tech", "National Switchgear Industries", "Orient Power & Grid Ltd",
    "Pinnacle High Voltage Systems", "Radiant Electrical Solutions", "Supreme Switchgear Works",
    "Titan Grid Technologies", "Universal Power Apparatus Ltd", "Vidyut Switchgear Industries",
    "Windsor Electrical Systems", "Xenon High Voltage Tech", "Yamuna Grid Apparatus Ltd",
    "Zodiac Power Controls Pvt Ltd", "Precision Switchgear & Infra Ltd"
]

def make_pdf_from_story(story, is_scan=False):
    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    doc.build(story)
    pdf_bytes = pdf_buf.getvalue()

    if not is_scan:
        return pdf_bytes

    fitz_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    scan_doc = fitz.open()
    for page in fitz_doc:
        pix = page.get_pixmap(dpi=100, colorspace=fitz.csGRAY)
        img_bytes = pix.tobytes("jpeg")
        
        img_pdf = fitz.open()
        rect = page.rect
        img_page = img_pdf.new_page(width=rect.width, height=rect.height)
        img_page.insert_image(rect, stream=img_bytes)
        scan_doc.insert_pdf(img_pdf)
        img_pdf.close()

    scan_bytes = scan_doc.tobytes()
    fitz_doc.close()
    scan_doc.close()
    return scan_bytes


def build_docs_for_bidder(idx, name, profile):
    is_scan = profile["is_scan"]
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('T', parent=styles['Heading1'], fontSize=13, leading=15, textColor=colors.navy)
    body_style = ParagraphStyle('B', parent=styles['Normal'], fontSize=9, leading=12)
    sub_style = ParagraphStyle('S', parent=styles['Heading2'], fontSize=10, leading=13, textColor=colors.darkblue)

    docs = {}

    # 1. Technical Offer
    if "Technical_Offer" not in profile["missing_docs"]:
        story = [
            Paragraph(f"<b>{name.upper()}</b>", title_style),
            Paragraph("TECHNICAL OFFER & SPECIFICATION COMPLIANCE", sub_style),
            Paragraph("Tender: BSES Equipment Engineering - NIT No. BSES/EE/2026/014", body_style),
            Paragraph("Supply of 11kV Vacuum Circuit Breaker Panels", body_style),
            Spacer(1, 8),
            Paragraph("We hereby submit our formal technical offer for 11kV VCB Panels. We confirm that our equipment conforms in all respects to IS 13118 and IEC 62271-100, and to the latest amendments thereof.", body_style),
            Spacer(1, 6),
            Paragraph(f"<b>Operating Mechanism:</b> Motor wound spring charged type, suitable for both local and remote operation.", body_style),
            Spacer(1, 6),
            Paragraph(f"<b>Guaranteed Technical Parameters:</b>", body_style),
            Paragraph(f"• System Rated Voltage: {profile['voltage']}", body_style),
            Paragraph(f"• Short Circuit Breaking Capacity: {profile['breaking_current']} for {profile['breaking_duration']}", body_style),
            Paragraph(f"• Rated Operating Frequency: {profile['frequency']}", body_style),
            Paragraph(f"• Ingress Protection Degree: {profile['protection']}", body_style),
            Paragraph(f"• Auxiliary Supply Voltage: {profile['aux_voltage']}", body_style),
            Spacer(1, 12),
            Paragraph("For " + name + "<br/><b>Authorized Signatory & Seal</b>", body_style)
        ]
        docs["01_Technical_Offer.pdf"] = make_pdf_from_story(story, is_scan)

    # 2. Deviation Sheet
    if "Deviation_Sheet" not in profile["missing_docs"]:
        story = [
            Paragraph(f"<b>{name.upper()}</b>", title_style),
            Paragraph("SCHEDULE OF DEVIATIONS (TECHNICAL & COMMERCIAL)", sub_style),
            Paragraph("Tender NIT No. BSES/EE/2026/014", body_style),
            Spacer(1, 8),
            Paragraph("Any deviation from the parameters shall be listed in the Deviation Sheet. A Deviation Sheet marked NIL shall be taken to mean full compliance.", body_style),
            Spacer(1, 8),
        ]
        if profile["deviation_status"] == "NIL":
            table_data = [
                ["Sl No.", "Clause Reference", "Specification Requirement", "Deviations Offered", "Remarks"],
                ["1", "NIL", "NIL - All technical parameters complied without exception", "NIL", "Full compliance confirmed"]
            ]
        else:
            table_data = [
                ["Sl No.", "Clause Reference", "Specification Requirement", "Deviations Offered", "Remarks"],
                ["1", "3.4 (Technical)", "25 kA for 3 seconds", profile["deviation_status"], "Deviation acknowledged"]
            ]
        t = Table(table_data, colWidths=[35, 80, 160, 140, 110])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))
        story.append(Paragraph("For " + name + "<br/><b>Authorized Signatory & Seal</b>", body_style))
        docs["02_Deviation_Sheet.pdf"] = make_pdf_from_story(story, is_scan)

    # 3. Guaranteed Technical Particulars (GTP)
    if "GTP" not in profile["missing_docs"]:
        gtp_v = profile["contradict_voltage"] if profile.get("contradictions") else profile["voltage"]
        gtp_ka = profile["contradict_breaking"] if profile.get("contradictions") else profile["breaking_current"]
        story = [
            Paragraph(f"<b>{name.upper()}</b>", title_style),
            Paragraph("GUARANTEED TECHNICAL PARTICULARS (GTP)", sub_style),
            Paragraph("Indoor Metalclad Vacuum Circuit Breaker Panels - 11kV", body_style),
            Spacer(1, 8),
        ]
        table_data = [
            ["Sl No.", "Parameter Description", "Required Value", "Guaranteed by Bidder"],
            ["1", "Rated voltage", "11 kV", gtp_v],
            ["2", "Rated short circuit breaking current", "25 kA for 3 seconds", f"{gtp_ka} for {profile['breaking_duration']}"],
            ["3", "Rated frequency", "50 Hz", profile['frequency']],
            ["4", "Degree of protection of enclosure", "IP 4X or better", profile['protection']],
            ["5", "Auxiliary supply voltage", "110 V DC", profile['aux_voltage']],
            ["6", "Breaker Type & Interrupter", "Vacuum Circuit Breaker", "Vacuum Circuit Breaker (Hermetically Sealed)"],
            ["7", "Operating Mechanism", "Motor wound spring charged", "Motor wound spring charged type"],
            ["8", "Control Modes", "Local and remote", "Suitable for both local and remote operation"]
        ]
        t = Table(table_data, colWidths=[35, 175, 145, 170])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.navy),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))
        story.append(Paragraph("For " + name + "<br/><b>Chief Technical Officer</b>", body_style))
        docs["03_Guaranteed_Technical_Particulars.pdf"] = make_pdf_from_story(story, is_scan)

    # 4. Type Test Report
    if "Type_Test" not in profile["missing_docs"]:
        story = [
            Paragraph("CENTRAL POWER RESEARCH INSTITUTE (CPRI) / ERDA TEST CERTIFICATE", title_style),
            Paragraph("NABL Accredited High Voltage Testing Laboratory", sub_style),
            Spacer(1, 6),
            Paragraph(f"<b>Test Report Certificate Number:</b> CPRI/NABL/HV/{1000 + idx}", body_style),
            Paragraph(f"<b>Date of Testing & Issue:</b> {profile['test_date']}", body_style),
            Paragraph(f"<b>Manufacturer / Client:</b> {name}", body_style),
            Paragraph(f"<b>Apparatus Tested:</b> 11kV Vacuum Circuit Breaker Panel", body_style),
            Paragraph(f"<b>Standard of Verification:</b> {profile['test_standards']}", body_style),
            Spacer(1, 8),
            Paragraph("<b>MANDATORY TYPE TESTS CONDUCTED & CERTIFIED:</b>", body_style),
            Paragraph(f"• <b>Short circuit breaking current test:</b> Successfully carried out at {profile['breaking_current']} for {profile['breaking_duration']}.", body_style),
            Paragraph("• <b>Lightning impulse withstand test:</b> Tested and passed at 75 kV peak impulse withstand.", body_style),
            Paragraph("• <b>Power frequency withstand test:</b> Tested and passed at 28 kV rms for 60 seconds.", body_style),
            Paragraph("• <b>Temperature rise test:</b> Carried out on offered equipment with temperature rise within limits.", body_style),
            Spacer(1, 12),
            Paragraph("<b>Senior Testing Officer & NABL Lab Director</b>", body_style)
        ]
        docs["04_Type_Test_Reports.pdf"] = make_pdf_from_story(story, is_scan)

    # 5. Audited Balance Sheets
    if "Balance_Sheets" not in profile["missing_docs"]:
        story = [
            Paragraph("STATUTORY AUDIT & CHARTERED ACCOUNTANTS CERTIFICATE", title_style),
            Paragraph(f"Turnover Certification for {name}", sub_style),
            Spacer(1, 6),
            Paragraph("We have verified the audited financial statements of the bidder for the last three financial years:", body_style),
            Spacer(1, 6),
            Paragraph(f"1. FY 2022-2023 Turnover: Rs. {profile['turnover_y1']} Crore", body_style),
            Paragraph(f"2. FY 2023-2024 Turnover: Rs. {profile['turnover_y2']} Crore", body_style),
            Paragraph(f"3. FY 2024-2025 Turnover: Rs. {profile['turnover_y3']} Crore", body_style),
            Spacer(1, 6),
            Paragraph(f"<b>Certified Average Annual Turnover:</b> Rs. {profile['turnover_avg']} crore during the last three financial years.", body_style),
            Spacer(1, 12),
            Paragraph("For M/s K.R. Mehta & Associates, Chartered Accountants<br/><b>Firm Regn No: 104231W | UDIN: 25104231AAAAK0921</b>", body_style)
        ]
        docs["05_Audited_Balance_Sheets.pdf"] = make_pdf_from_story(story, is_scan)

    # 6. Credentials
    if "Credentials" not in profile["missing_docs"]:
        story = [
            Paragraph(f"<b>{name.upper()}</b>", title_style),
            Paragraph("MANUFACTURING AND PAST SUPPLY PERFORMANCE CREDENTIALS", sub_style),
            Spacer(1, 6),
            Paragraph(f"This is to certify that {name} has designed, manufactured, and supplied high-voltage vacuum circuit breakers across Indian power utilities:", body_style),
            Spacer(1, 6),
            Paragraph(f"• Supply to State Electricity Boards / DISCOMs: {profile['supply_qty']} Nos. 11kV Vacuum Circuit Breakers", body_style),
            Paragraph(f"• Additional Utility Deployments: 100 Nos. 11kV VCB Units", body_style),
            Spacer(1, 6),
            Paragraph(f"<b>Certified Total Supply:</b> The bidder has designed, manufactured and supplied {profile['supply_total']} numbers of 11kV Vacuum Circuit Breakers to State Electricity Boards or Distribution Licensees in India during the last five years.", body_style),
            Spacer(1, 12),
            Paragraph("For " + name + "<br/><b>Head - Commercial Contracts</b>", body_style)
        ]
        docs["06_Supply_Credentials.pdf"] = make_pdf_from_story(story, is_scan)

    # 7. Testing Facility
    if "Testing_Facility" not in profile["missing_docs"]:
        story = [
            Paragraph(f"<b>{name.upper()}</b>", title_style),
            Paragraph("IN-HOUSE ROUTINE TESTING FACILITY AND CALIBRATION CERTIFICATE", sub_style),
            Spacer(1, 6),
            Paragraph(f"We confirm that {name} owns and operates an in-house routine testing facility at the manufacturing works.", body_style),
            Paragraph("Routine tests shall be carried out on each circuit breaker in the presence of the purchaser's representative, and test certificates shall be submitted for approval before despatch.", body_style),
            Spacer(1, 6),
            Paragraph("<b>List of In-House Test Equipment with Valid Calibration:</b>", body_style),
            Paragraph("1. High Voltage Dielectric Test Bench 100 kV AC (Calibrated through NABL lab, valid up to 2026)", body_style),
            Paragraph("2. Micro-Ohmmeter Contact Resistance Test Set 100A (Calibrated valid up to 2026)", body_style),
            Paragraph("3. Circuit Breaker Travel & Operating Timing Analyzer (Calibrated valid up to 2026)", body_style),
            Spacer(1, 12),
            Paragraph("<b>Routine Testing Quality In-Charge</b>", body_style)
        ]
        docs["07_InHouse_Routine_Testing_Facility.pdf"] = make_pdf_from_story(story, is_scan)

    # 8. Self Declaration
    if "Self_Declaration" not in profile["missing_docs"]:
        story = [
            Paragraph(f"<b>{name.upper()}</b>", title_style),
            Paragraph("NON-BLACKLISTING & NON-DEBARMENT UNDERTAKING", sub_style),
            Paragraph("(On Official Company Letterhead)", body_style),
            Spacer(1, 8),
            Paragraph("To: BSES Equipment Engineering, New Delhi.", body_style),
            Spacer(1, 6),
            Paragraph(f"Dear Sir,<br/>We, {name}, hereby solemnly declare that our company has <b>not been blacklisted or debarred</b> by any utility in India during the last three years.", body_style),
            Paragraph("We further certify that all statements made in our bid submission are true and verifiable.", body_style),
            Spacer(1, 12),
            Paragraph("For " + name + "<br/><b>Managing Director & Authorized Signatory</b>", body_style)
        ]
        docs["08_Self_Declaration.pdf"] = make_pdf_from_story(story, is_scan)

    # 9. PBG Undertaking
    if "PBG" not in profile["missing_docs"]:
        story = [
            Paragraph(f"<b>{name.upper()}</b>", title_style),
            Paragraph("PERFORMANCE BANK GUARANTEE & DEFECT LIABILITY UNDERTAKING", sub_style),
            Spacer(1, 6),
            Paragraph("1. <b>Equipment Guarantee:</b> The equipment shall be guaranteed against defective design, material and workmanship for a period of 18 months from the date of commissioning or 24 months from the date of despatch, whichever is earlier.", body_style),
            Spacer(1, 6),
            Paragraph("2. <b>Performance Bank Guarantee:</b> The bidder shall furnish a performance bank guarantee for 10 percent of the order value, valid for the full guarantee period.", body_style),
            Spacer(1, 12),
            Paragraph("For " + name + "<br/><b>Authorized Financial Signatory</b>", body_style)
        ]
        docs["09_Performance_Bank_Guarantee_Undertaking.pdf"] = make_pdf_from_story(story, is_scan)

    # 10. QAP
    if "QAP" not in profile["missing_docs"]:
        story = [
            Paragraph(f"<b>{name.upper()}</b>", title_style),
            Paragraph("QUALITY ASSURANCE PLAN (QAP) SUBMISSION UNDERTAKING", sub_style),
            Spacer(1, 6),
            Paragraph("The bidder shall submit a Quality Assurance Plan for approval within fifteen days of the date of the purchase order.", body_style),
            Paragraph("Any equipment failing a routine test shall be replaced at the bidder's cost.", body_style),
            Spacer(1, 12),
            Paragraph("For " + name + "<br/><b>Head - Quality Management</b>", body_style)
        ]
        docs["10_Quality_Assurance_Plan.pdf"] = make_pdf_from_story(story, is_scan)

    return docs


def generate_all_50():
    answer_rows = []
    print("Generating 50 synthetic bidder test packages...")

    for i in range(1, 51):
        name = COMPANY_NAMES[i - 1]
        folder_name = f"Bidder_{i:02d}_{name.split()[0]}"
        bidder_path = os.path.join(BASE_DIR, folder_name)
        os.makedirs(bidder_path, exist_ok=True)

        is_scan = (i % 2 == 0)

        # Baseline compliant profile
        p = {
            "is_scan": is_scan,
            "voltage": "11 kV",
            "breaking_current": "25 kA",
            "breaking_duration": "3 seconds",
            "frequency": "50 Hz",
            "protection": "IP 4X",
            "aux_voltage": "110 V DC",
            "turnover_y1": "12.5",
            "turnover_y2": "14.2",
            "turnover_y3": "16.8",
            "turnover_avg": "14.5",
            "supply_qty": "220",
            "supply_total": "320",
            "test_date": "15-06-2023",
            "test_standards": "IS 13118 and IEC 62271-100",
            "deviation_status": "NIL",
            "missing_docs": [],
            "contradictions": False,
            "expected_qualification": "Qualified",
            "category": "Compliant",
            "fail_reason": "Fully Compliant - All parameters and documents met"
        }

        if 1 <= i <= 12:
            p["category"] = "Fully Compliant"
            p["expected_qualification"] = "Qualified"

        elif 13 <= i <= 25:
            p["category"] = "Numerical Value Trap"
            p["expected_qualification"] = "Not Qualified"
            if i == 13:
                p["voltage"] = "10.5 kV"
                p["fail_reason"] = "Rated voltage 10.5 kV fails 11 kV requirement"
            elif i == 14:
                p["voltage"] = "11.0 kV"
                p["fail_reason"] = "Rated voltage 11.0 kV"
            elif i == 15:
                p["breaking_current"] = "20 kA"
                p["fail_reason"] = "Short circuit breaking current 20 kA is below 25 kA"
            elif i == 16:
                p["breaking_current"] = "22 kA"
                p["fail_reason"] = "Short circuit breaking current 22 kA is below 25 kA"
            elif i == 17:
                p["breaking_duration"] = "1 second"
                p["fail_reason"] = "Breaking duration 1 second fails required 3 seconds"
            elif i == 18:
                p["protection"] = "IP 40"
                p["fail_reason"] = "Degree of protection IP 40 fails IP 4X requirement"
            elif i == 19:
                p["protection"] = "IP 2X"
                p["fail_reason"] = "Degree of protection IP 2X fails IP 4X requirement"
            elif i == 20:
                p["aux_voltage"] = "220 V DC"
                p["fail_reason"] = "Auxiliary voltage 220 V DC fails 110 V DC requirement"
            elif i == 21:
                p["turnover_avg"] = "7.5"
                p["turnover_y1"] = "6.5"; p["turnover_y2"] = "7.5"; p["turnover_y3"] = "8.5"
                p["fail_reason"] = "Average turnover 7.5 Cr fails minimum Rs. 10 crore"
            elif i == 22:
                p["turnover_avg"] = "9.2"
                p["turnover_y1"] = "8.5"; p["turnover_y2"] = "9.0"; p["turnover_y3"] = "10.1"
                p["fail_reason"] = "Average turnover 9.2 Cr fails minimum Rs. 10 crore"
            elif i == 23:
                p["supply_total"] = "120"
                p["supply_qty"] = "60"
                p["fail_reason"] = "Supply quantity 120 numbers fails minimum 200 units"
            elif i == 24:
                p["supply_total"] = "180"
                p["supply_qty"] = "90"
                p["fail_reason"] = "Supply quantity 180 numbers fails minimum 200 units"
            elif i == 25:
                p["frequency"] = "60 Hz"
                p["fail_reason"] = "Rated frequency 60 Hz fails 50 Hz requirement"

        elif 26 <= i <= 35:
            p["category"] = "Expired Certificate / Standards Mismatch"
            p["expected_qualification"] = "Not Qualified"
            if i in [26, 27, 28, 29, 30]:
                p["test_date"] = "10-04-2017"
                p["fail_reason"] = "Type test report dated 2017 is older than 5 years"
            elif i in [31, 32, 33]:
                p["test_date"] = "15-08-2018"
                p["fail_reason"] = "Type test report dated 2018 is older than 5 years"
            else:
                p["test_standards"] = "IS 2516 (superseded legacy standard only)"
                p["fail_reason"] = "Does not conform to IS 13118 and IEC 62271-100"

        elif 36 <= i <= 43:
            p["category"] = "Missing Mandatory Document"
            p["expected_qualification"] = "Not Qualified"
            if i in [36, 37]:
                p["missing_docs"] = ["Deviation_Sheet"]
                p["fail_reason"] = "Missing mandatory Deviation Sheet"
            elif i in [38, 39]:
                p["missing_docs"] = ["Balance_Sheets"]
                p["fail_reason"] = "Missing mandatory Audited Balance Sheets"
            elif i in [40, 41]:
                p["missing_docs"] = ["Self_Declaration"]
                p["fail_reason"] = "Missing mandatory Non-Blacklisting Self Declaration"
            else:
                p["missing_docs"] = ["Type_Test"]
                p["fail_reason"] = "Missing mandatory Type Test Reports"

        elif 44 <= i <= 50:
            p["category"] = "Contradiction / Deviation"
            p["expected_qualification"] = "Not Qualified"
            p["contradictions"] = True
            p["contradict_voltage"] = "11 kV"
            p["contradict_breaking"] = "20 kA"
            p["deviation_status"] = "Short circuit capacity offered is 20 kA instead of 25 kA"
            p["fail_reason"] = "Deviation sheet lists 20 kA breaking capacity deviation"

        generated_docs = build_docs_for_bidder(i, name, p)
        for doc_name, doc_bytes in generated_docs.items():
            doc_path = os.path.join(bidder_path, doc_name)
            with open(doc_path, "wb") as f:
                f.write(doc_bytes)

        format_type = "Scanned Image PDF" if is_scan else "Digital Selectable Text PDF"
        answer_rows.append({
            "Bidder_ID": i,
            "Folder_Name": folder_name,
            "Company_Name": name,
            "Format_Type": format_type,
            "Test_Category": p["category"],
            "Ground_Truth_Status": p["expected_qualification"],
            "Offered_Voltage": p.get("contradict_voltage", p["voltage"]) if p.get("contradictions") else p["voltage"],
            "Offered_Breaking_Current": p.get("contradict_breaking", p["breaking_current"]) if p.get("contradictions") else p["breaking_current"],
            "Offered_Duration": p["breaking_duration"],
            "Offered_Protection": p["protection"],
            "Offered_Turnover_Avg": f"{p['turnover_avg']} Cr",
            "Offered_Supply_Qty": f"{p['supply_total']} Units",
            "Type_Test_Date": p["test_date"],
            "Missing_Documents": ", ".join(p["missing_docs"]) if p["missing_docs"] else "None",
            "Ground_Truth_Failure_Reason": p["fail_reason"]
        })

        if i % 10 == 0:
            print(f"  Generated {i}/50 bidders...")

    csv_path = os.path.join(BASE_DIR, "GROUND_TRUTH_ANSWER_KEY.csv")
    fieldnames = list(answer_rows[0].keys())
    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(answer_rows)

    print(f"\nAll 50 bidders generated successfully at: {BASE_DIR}")
    print(f"Ground Truth Answer Key generated at: {csv_path}")

if __name__ == "__main__":
    generate_all_50()

