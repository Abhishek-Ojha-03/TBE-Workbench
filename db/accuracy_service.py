"""
Accuracy Benchmark & Audit Matrix service — compares AI evaluations
against GROUND_TRUTH_ANSWER_KEY.csv. Same matching/scoring logic as
ui/accuracy_matrix_view.py, extracted here (unchanged) so the FastAPI
route can call it without importing Streamlit.
"""
import os
import csv
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from db.models import Tender, Bidder, Finding, Evidence

ANSWER_KEY_CANDIDATES = [
    os.path.join("test_data", "synthetic_50_bidders", "GROUND_TRUTH_ANSWER_KEY.csv"),
    os.path.join("test_data", "GROUND_TRUTH_ANSWER_KEY.csv"),
]


def load_ground_truth() -> Dict[str, dict]:
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
            b_id = row.get("Bidder_ID")
            folder = row.get("Folder_Name", "")
            comp = row.get("Company_Name", "")
            gt_map[str(b_id)] = row
            gt_map[folder.lower()] = row
            gt_map[comp.lower()] = row
    return gt_map


def compute_accuracy_matrix(db: Session, tender: Tender) -> Optional[dict]:
    """
    Returns None if the ground-truth CSV isn't present (this is a
    benchmark/audit feature for the synthetic 50-bidder test set, not a
    general per-client report — mirrors ui/accuracy_matrix_view.py's
    early-return behavior). Returns a dict with KPI counts and the
    per-clause audit rows otherwise.
    """
    gt_data = load_ground_truth()
    if not gt_data:
        return None

    bidders = db.query(Bidder).filter(Bidder.tender_id == tender.id).all()
    if not bidders:
        return {"has_bidders": False, "total_evals": 0}

    matched_evals: List[dict] = []
    tp = tn = fp = fn = 0

    for b in bidders:
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

        for f in findings:
            eff_status = f.engineer_status or f.ai_status or "Pending"
            if eff_status == "Pending":
                continue

            evidence = db.query(Evidence).filter(Evidence.finding_id == f.id).first()
            quote_text = evidence.quoted_text if evidence else "No quote found"
            req = f.requirement

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

            if expected_qual:
                clause_ground_truth = "Complied"
            else:
                clause_ground_truth = "Not Complied" if is_trap_clause else "Complied"

            if clause_ground_truth == "Complied":
                if eff_status == "Complied":
                    tp += 1
                    clause_match = "PASS (True Complied)"
                else:
                    fn += 1
                    clause_match = "MISS (False Disqualified)"
            else:
                if eff_status == "Complied":
                    fp += 1
                    clause_match = "CRITICAL FAIL (Hallucination!)"
                else:
                    tn += 1
                    clause_match = "PASS (Trap Caught)"

            matched_evals.append({
                "bidder": b.name,
                "test_category": gt_entry.get("Test_Category", "General") if gt_entry else "General",
                "format_type": gt_entry.get("Format_Type", "Digital/Scan") if gt_entry else "Digital/Scan",
                "clause": (req.clause or "-") if req else "-",
                "requirement_text": (req.text or "-") if req else "-",
                "offered_value": quote_text,
                "ground_truth_answer": clause_ground_truth,
                "ai_verdict": eff_status,
                "audit_match": clause_match,
                "is_trap_clause": is_trap_clause,
                "full_quote": quote_text,
                "ai_remarks": f.remark or "-",
            })

    total_evals = tp + tn + fp + fn
    if total_evals == 0:
        return {"has_bidders": True, "total_evals": 0}

    accuracy = round(((tp + tn) / total_evals) * 100, 1)
    precision = round((tp / (tp + fp)) * 100, 1) if (tp + fp) > 0 else 100.0
    recall = round((tp / (tp + fn)) * 100, 1) if (tp + fn) > 0 else 100.0

    return {
        "has_bidders": True,
        "total_evals": total_evals,
        "bidder_count": len(bidders),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "accuracy_pct": accuracy,
        "precision_pct": precision,
        "recall_pct": recall,
        "rows": matched_evals,
    }
