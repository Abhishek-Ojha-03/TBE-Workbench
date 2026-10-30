"""
Accuracy Benchmark & Audit Matrix Dashboard (Screen 6)
Compares AI evaluations against GROUND_TRUTH_ANSWER_KEY.csv to display:
1. Top Summary KPI Cards (Overall Accuracy, Precision, Recall, Hallucination Count)
2. Interactive Visual 2x2 Confusion Matrix (TP, TN, FP, FN)
3. Value Trap Inspection Table (Audit Drilldown with side-by-side comparison & quotes)
"""

import os
import csv
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session

from db.models import Tender, Bidder, Finding, Evidence

ANSWER_KEY_CANDIDATES = [
    os.path.join("test_data", "synthetic_50_bidders", "GROUND_TRUTH_ANSWER_KEY.csv"),
    os.path.join("test_data", "GROUND_TRUTH_ANSWER_KEY.csv"),
]


def load_ground_truth():
    target_path = None
    for p in ANSWER_KEY_CANDIDATES:
        if os.path.exists(p):
            target_path = p
            break

    if not target_path:
        return {}
    gt_map = {}
    with open(target_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Map by Bidder_ID, Folder_Name, and Company_Name for easy matching
            b_id = row.get("Bidder_ID")
            folder = row.get("Folder_Name", "")
            comp = row.get("Company_Name", "")
            gt_map[str(b_id)] = row
            gt_map[folder.lower()] = row
            gt_map[comp.lower()] = row
    return gt_map


def render_accuracy_matrix_screen(db: Session, tender: Tender):
    top_c1, top_c2 = st.columns([3, 1])
    with top_c1:
        st.markdown("## 🎯 Accuracy Benchmark & Audit Matrix")
        st.caption(f"Tender: `{tender.nit_no}` — Evaluating AI verdicts against Ground Truth benchmarks to verify zero-hallucination.")
    with top_c2:
        docx_file = "TBE_Accuracy_Matrix_Formal_Report.docx" if os.path.exists("TBE_Accuracy_Matrix_Formal_Report.docx") else "TBE_Accuracy_Matrix_Documentation.docx"
        if os.path.exists(docx_file):
            with open(docx_file, "rb") as f:
                st.download_button(
                    label="📥 Download Formal Audit Report (.docx)",
                    data=f.read(),
                    file_name=f"TBE_50_Bidders_Accuracy_Formal_Report_NIT_{tender.nit_no}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )

    gt_data = load_ground_truth()
    if not gt_data:
        st.warning(f"⚠️ Ground Truth Answer Key not found in `test_data/`. Please ensure synthetic bidders are generated.")
        return

    bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all()
    if not bidders:
        st.info("No bidders found for this tender. Upload bidders in **TBE Working Excel** first.")
        return

    matched_evals = []

    # CLAUSE-LEVEL confusion matrix counters
    # TP: Bidder is Qualified  AND AI said "Complied"        → Correct acceptance
    # TN: Bidder is NotQualified AND AI said "Not Complied" or "Needs Human Review" → Correct rejection (cautious)
    # FP: Bidder is NotQualified AND AI said "Complied"      → HALLUCINATION (critical risk!)
    # FN: Bidder is Qualified  AND AI said "Not Complied" or "Needs Human Review" → Missed compliance
    tp = 0
    tn = 0
    fp = 0
    fn = 0

    for b in bidders:
        # Match bidder to Ground Truth entry (keep existing matching logic unchanged)
        clean_name = b.name.strip().lower()
        gt_entry = gt_data.get(clean_name) or gt_data.get(clean_name.replace("bidder_", "").split("_")[0])

        if not gt_entry and clean_name.isdigit():
            gt_entry = gt_data.get(clean_name)

        if not gt_entry:
            for k, val in gt_data.items():
                if clean_name in k or k in clean_name:
                    gt_entry = val
                    break

        findings = db.query(Finding).filter(Finding.bidder_id == b.id).all()
        if not findings:
            continue

        gt_overall = gt_entry.get("Ground_Truth_Status", "Qualified") if gt_entry else "Qualified"
        fail_reason = gt_entry.get("Ground_Truth_Failure_Reason", "") if gt_entry else ""
        expected_qual = (gt_overall == "Qualified")

        # ── CLAUSE-LEVEL counting ──────────────────────────────────────────────
        for f in findings:
            eff_status = f.engineer_status or f.ai_status or "Pending"
            if eff_status == "Pending":
                continue  # Skip unevaluated clauses entirely

            evidence = db.query(Evidence).filter(Evidence.finding_id == f.id).first()
            quote_text = evidence.quoted_text if evidence else "No quote found"
            req = f.requirement

            # ── Step 1: Detect the specific trap clause FIRST ─────────────────
            # A trap clause is the one specific parameter the bidder fails on.
            # All other clauses on a "Not Qualified" bidder may genuinely comply.
            is_trap_clause = False
            if req and not expected_qual:
                req_text_lower = (req.text or "").lower()
                if ("voltage" in req_text_lower and "voltage" in fail_reason.lower()) or \
                   ("short circuit" in req_text_lower and "breaking" in fail_reason.lower()) or \
                   ("protection" in req_text_lower and "protection" in fail_reason.lower()) or \
                   ("turnover" in req_text_lower and "turnover" in fail_reason.lower()) or \
                   ("supply" in req_text_lower and "supply" in fail_reason.lower()) or \
                   ("five years" in req_text_lower and "older than 5 years" in fail_reason.lower()) or \
                   ("missing" in fail_reason.lower() and "document" in fail_reason.lower()) or \
                   ("contradiction" in fail_reason.lower() and "kA" in (req.text or "")):
                    is_trap_clause = True

            # ── Step 2: Assign Ground Truth AFTER knowing is_trap_clause ──────
            if expected_qual:
                # Fully compliant bidder → every clause should be Complied
                clause_ground_truth = "Complied"
            else:
                # Not Qualified bidder:
                #   • The specific trap/failure clause → "Not Complied"
                #   • Every other clause the bidder genuinely meets → "Complied"
                #     (e.g. a voltage-trap bidder still correctly offers 320 units,
                #      Rs 14.5 cr turnover, IS 13118 conformity — those are TRUE
                #      compliances and AI saying "Complied" there is NOT a hallucination)
                clause_ground_truth = "Not Complied" if is_trap_clause else "Complied"

            # ── Step 3: Confusion matrix counting (clause-level, correct GT) ──
            # clause_ground_truth is now "Complied" or "Not Complied" per clause,
            # NOT a blanket bidder-level verdict.
            if clause_ground_truth == "Complied":
                # Ground truth says this clause SHOULD be Complied
                if eff_status == "Complied":
                    tp += 1
                    clause_match = "✅ PASS (True Complied)"
                else:
                    fn += 1
                    clause_match = "⚠️ MISS (False Disqualified)"
            else:
                # Ground truth says this clause SHOULD be Not Complied (trap clause)
                if eff_status == "Complied":
                    fp += 1
                    clause_match = "🚨 CRITICAL FAIL (Hallucination!)"
                else:
                    tn += 1
                    clause_match = "✅ PASS (Trap Caught)"

            matched_evals.append({
                "Bidder": b.name,
                "Test Category": gt_entry.get("Test_Category", "General") if gt_entry else "General",
                "Format": gt_entry.get("Format_Type", "Digital/Scan") if gt_entry else "Digital/Scan",
                "Clause": req.clause if req else "-",
                "Specification Requirement": req.text if req else "-",
                "Offered Value / Quote": quote_text,
                "Ground Truth Answer": clause_ground_truth,
                "AI Verdict": eff_status,
                "Audit Match": clause_match,
                "Is Trap Clause": "⚠️ YES" if is_trap_clause else "No",
                "Full Quote": quote_text,
                "AI Remarks": f.remark or "-"
            })

    # Count only evaluated (non-pending) clauses
    total_evals = tp + tn + fp + fn
    if total_evals == 0:
        st.info("Bidders are uploaded, but AI Verification has not been run yet. Please click **`🚀 Run AI Verification for ALL Bidders`** in the **TBE Working Excel** tab first.")
        return

    # ── 1. SUMMARY BANNER (raw counts) ────────────────────────────────────────
    st.markdown(
        f"""<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:10px 18px;margin-bottom:8px;font-size:13px;color:#166534;">
        📐 <b>Clause-level evaluation</b> — {total_evals} clause verdicts scored across {len(bidders)} bidders
        &nbsp;|&nbsp; TP={tp} &nbsp; TN={tn} &nbsp; FP={fp} &nbsp; FN={fn}
        </div>""",
        unsafe_allow_html=True,
    )

    # ── 2. TOP SUMMARY KPI CARDS ───────────────────────────────────────────────
    accuracy  = round(((tp + tn) / total_evals) * 100, 1) if total_evals > 0 else 0.0
    precision = round((tp / (tp + fp)) * 100, 1)          if (tp + fp) > 0    else 100.0
    recall    = round((tp / (tp + fn)) * 100, 1)          if (tp + fn) > 0    else 100.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🎯 Overall Accuracy",               f"{accuracy}%",
              help="(TP + TN) / Total evaluated clauses — clause-level score")
    c2.metric("🛡️ Precision (Zero-Hallucination)", f"{precision}%",
              help="TP / (TP + FP) — 100% means AI never said Complied when it shouldn't have")
    c3.metric("🔍 Recall (Coverage Rate)",          f"{recall}%",
              help="TP / (TP + FN) — how many genuinely compliant clauses the AI caught")

    fp_color = "normal" if fp == 0 else "inverse"
    c4.metric("🚨 Hallucination Count (FP)",        f"{fp}",
              delta="-0 (Goal Met)" if fp == 0 else f"+{fp} Traps Missed!",
              delta_color=fp_color)

    st.markdown("---")

    # ── 3. INTERACTIVE VISUAL 2×2 CONFUSION MATRIX ────────────────────────────
    st.subheader("📊 Interactive Visual Confusion Matrix (2×2)")
    st.caption("Clause-level comparison between Human Ground Truth and AI Predictions:")

    cm_col1, cm_col2 = st.columns(2)
    with cm_col1:
        st.markdown(f"""
        <div style="background-color:#d1fae5;border-left:6px solid #10b981;padding:14px 18px;border-radius:6px;margin-bottom:12px;">
            <h4 style="margin:0;color:#065f46;">🟩 True Complied (TP): {tp}</h4>
            <p style="margin:4px 0 0 0;color:#047857;font-size:13px;">
                Clause from a Qualified bidder — AI correctly said <b>Complied</b> with a cited quote.
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="background-color:#fee2e2;border-left:6px solid #ef4444;padding:14px 18px;border-radius:6px;margin-bottom:12px;">
            <h4 style="margin:0;color:#991b1b;">🟥 Hallucination / False Complied (FP): {fp}</h4>
            <p style="margin:4px 0 0 0;color:#b91c1c;font-size:13px;">
                ⚠️ Critical Risk: Clause from a <b>trap/disqualified bidder</b> — AI mistakenly said <b>Complied</b>.
            </p>
        </div>
        """, unsafe_allow_html=True)

    with cm_col2:
        st.markdown(f"""
        <div style="background-color:#e0f2fe;border-left:6px solid #0284c7;padding:14px 18px;border-radius:6px;margin-bottom:12px;">
            <h4 style="margin:0;color:#075985;">🟦 True Disqualified (TN): {tn}</h4>
            <p style="margin:4px 0 0 0;color:#0369a1;font-size:13px;">
                Clause from a trap/failed bidder — AI correctly said <b>Not Complied</b> or flagged for Review.
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="background-color:#fef3c7;border-left:6px solid #f59e0b;padding:14px 18px;border-radius:6px;margin-bottom:12px;">
            <h4 style="margin:0;color:#92400e;">🟨 False Disqualified (FN): {fn}</h4>
            <p style="margin:4px 0 0 0;color:#b45309;font-size:13px;">
                Clause from a Qualified bidder — AI said <b>Not Complied</b> or <b>Needs Review</b> incorrectly.
            </p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ── 4. VALUE TRAP INSPECTION TABLE (AUDIT DRILLDOWN) ──────────────────────
    st.subheader("🔍 Value Trap Inspection & Audit Drilldown")
    st.caption("Every evaluated clause side-by-side — check exact numbers, AI verdict, and cited quote:")

    df_evals = pd.DataFrame(matched_evals)

    f_c1, f_c2, f_c3 = st.columns([1, 1, 2])
    with f_c1:
        filter_status = st.selectbox(
            "Filter Audit Match:",
            ["All Evaluated Clauses", "Hallucinations Only (🚨 FP)", "Misses Only (⚠️ FN)", "Passed Clauses Only (✅)"]
        )
    with f_c2:
        filter_trap = st.selectbox(
            "Filter Trap Clauses:",
            ["All Clauses", "Trap Clauses Only (⚠️ YES)", "Non-Trap Clauses"]
        )
    with f_c3:
        bidder_filter = st.multiselect(
            "Filter by Bidder:",
            options=sorted(list(set(df_evals["Bidder"]))),
            default=[]
        )

    filtered_df = df_evals.copy()
    if bidder_filter:
        filtered_df = filtered_df[filtered_df["Bidder"].isin(bidder_filter)]
    if filter_status == "Hallucinations Only (🚨 FP)":
        filtered_df = filtered_df[filtered_df["Audit Match"].str.contains("CRITICAL|Hallucination")]
    elif filter_status == "Misses Only (⚠️ FN)":
        filtered_df = filtered_df[filtered_df["Audit Match"].str.contains("MISS")]
    elif filter_status == "Passed Clauses Only (✅)":
        filtered_df = filtered_df[filtered_df["Audit Match"].str.contains("PASS")]
    if filter_trap == "Trap Clauses Only (⚠️ YES)":
        filtered_df = filtered_df[filtered_df["Is Trap Clause"] == "⚠️ YES"]
    elif filter_trap == "Non-Trap Clauses":
        filtered_df = filtered_df[filtered_df["Is Trap Clause"] == "No"]

    display_cols = [
        "Bidder", "Test Category", "Clause", "Specification Requirement",
        "Offered Value / Quote", "Ground Truth Answer", "AI Verdict",
        "Is Trap Clause", "Audit Match", "AI Remarks"
    ]

    # ── HTML table with full wrapping text (no truncation) ────────────────────
    VERDICT_COLORS = {
        "Complied":           "#d1fae5",
        "Not Complied":       "#fee2e2",
        "Needs Human Review": "#fef3c7",
        "Pending":            "#f3f4f6",
    }
    MATCH_COLORS = {
        "✅": "#d1fae5",
        "⚠️": "#fef3c7",
        "🚨": "#fee2e2",
    }

    def _row_color(audit_match: str) -> str:
        for emoji, color in MATCH_COLORS.items():
            if emoji in audit_match:
                return color
        return "#ffffff"

    header_cells = "".join(
        f'<th style="background:#1e293b;color:#f1f5f9;padding:8px 10px;'
        f'text-align:left;white-space:nowrap;font-size:12px;">{col}</th>'
        for col in display_cols
    )

    body_rows = []
    for _, row in filtered_df[display_cols].iterrows():
        row_bg = _row_color(str(row.get("Audit Match", "")))
        verdict = str(row.get("AI Verdict", ""))
        verdict_bg = VERDICT_COLORS.get(verdict, "#ffffff")
        cells = []
        for col in display_cols:
            val = str(row.get(col, ""))
            if col == "AI Verdict":
                cell_style = (
                    f'background:{verdict_bg};font-weight:600;'
                    f'padding:8px 10px;font-size:12px;'
                    f'white-space:nowrap;vertical-align:top;'
                )
            elif col in ("Specification Requirement", "Offered Value / Quote", "AI Remarks"):
                cell_style = (
                    f'padding:8px 10px;font-size:12px;'
                    f'white-space:pre-wrap;word-break:break-word;'
                    f'min-width:220px;max-width:360px;vertical-align:top;'
                )
            else:
                cell_style = (
                    f'padding:8px 10px;font-size:12px;'
                    f'white-space:nowrap;vertical-align:top;'
                )
            cells.append(f'<td style="{cell_style}">{val}</td>')
        body_rows.append(
            f'<tr style="background:{row_bg};border-bottom:1px solid #e2e8f0;">'
            + "".join(cells)
            + "</tr>"
        )

    html_table = f"""
    <div style="overflow-x:auto;max-height:600px;overflow-y:auto;
                border:1px solid #cbd5e1;border-radius:6px;">
      <table style="border-collapse:collapse;width:100%;font-family:sans-serif;">
        <thead style="position:sticky;top:0;z-index:1;">
          <tr>{header_cells}</tr>
        </thead>
        <tbody>
          {"".join(body_rows)}
        </tbody>
      </table>
    </div>
    """
    st.markdown(html_table, unsafe_allow_html=True)
    st.caption(f"Showing {len(filtered_df)} of {len(df_evals)} evaluated clauses.")

    # ── 5. VERBATIM QUOTE INSPECTOR ───────────────────────────────────────────
    st.subheader("📄 Verbatim Document Quote Inspector")
    with st.expander("🔎 Click to inspect full verbatim quoted evidence for any evaluated clause", expanded=False):
        if filtered_df.empty:
            st.info("No rows match the current filter. Clear filters above to inspect quotes.")
        else:
            selected_row_idx = st.selectbox(
                "Select a row to inspect its exact quoted text:",
                range(len(filtered_df)),
                format_func=lambda idx: (
                    f"{filtered_df.iloc[idx]['Bidder']} — Clause {filtered_df.iloc[idx]['Clause']}: "
                    f"{filtered_df.iloc[idx]['Specification Requirement'][:50]}..."
                )
            )
            if selected_row_idx is not None:
                sel_row = filtered_df.iloc[selected_row_idx]
                q_c1, q_c2 = st.columns(2)
                with q_c1:
                    st.markdown(f"**Bidder:** `{sel_row['Bidder']}` — `{sel_row['Format']}`")
                    st.markdown(f"**Test Category:** `{sel_row['Test Category']}`")
                    st.markdown(f"**Clause:** `{sel_row['Clause']}` &nbsp; | &nbsp; **Trap Clause:** {sel_row['Is Trap Clause']}")
                    st.info(f"**Specification Requirement:**\n{sel_row['Specification Requirement']}")
                with q_c2:
                    st.markdown(f"**Ground Truth:** `{sel_row['Ground Truth Answer']}` &nbsp;|&nbsp; **AI Verdict:** `{sel_row['AI Verdict']}`")
                    st.markdown(f"**Audit Status:** {sel_row['Audit Match']}")
                    st.success(f"**Verbatim Cited Quote from Document:**\n\"{sel_row['Full Quote']}\"")
                    st.caption(f"**AI Engine Explanation:** {sel_row['AI Remarks']}")

