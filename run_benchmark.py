"""
Benchmark Evaluation Runner against the Ground Truth Answer Key.
Loads test_data/answer_key.csv and evaluates accuracy, false 'Complied' rate,
and citation verification.

Usage:
  python run_benchmark.py                  # Run with sample_limit=10
  python run_benchmark.py --full           # Run all 55 rows
  python run_benchmark.py --reingest       # Force re-ingest documents
"""
import os
import sys
import csv
import pandas as pd
from datetime import datetime

from db.connection import SessionLocal, init_db
from db.models import Tender, Bidder, Document, Page, Finding, Requirement, BaselineVersion
from db.repository import create_tender
from reading.ingest import ingest_pdf_document
from ai.verifier import verify_requirement_for_bidder
from rules.rule_engine import update_bidder_qualification_status

BENCHMARK_DB_MARKER = "BENCHMARK_TENDER"


def get_or_create_benchmark_tender(db, force_reingest=False):
    """
    Returns (tender, bidder_map, is_new).
    If a benchmark tender already exists in the DB, reuses it (fast).
    Otherwise creates a new one and ingests all documents.
    """
    # Check if benchmark tender already exists
    existing = db.query(Tender).filter(
        Tender.description.contains(BENCHMARK_DB_MARKER)
    ).order_by(Tender.id.desc()).first()

    if existing and not force_reingest:
        print(f"[REUSE] Found existing benchmark tender: {existing.nit_no}", flush=True)
        bidders = db.query(Bidder).filter(Bidder.tender_id == existing.id).all()
        bidder_map = {b.name: b for b in bidders}
        return existing, bidder_map, False

    # Create new benchmark tender
    nit_no = f"NIT-{BENCHMARK_DB_MARKER}-{datetime.now().strftime('%H%M%S')}"
    tender = create_tender(
        db,
        description=f"11kV VCB Equipment Tender {BENCHMARK_DB_MARKER}",
        nit_no=nit_no
    )
    print(f"[NEW] Created benchmark tender: {tender.nit_no}", flush=True)

    bidder_dir_map = {
        "ABC Switchgear Pvt Ltd": os.path.join("test_data", "bidder_ABC_Switchgear"),
        "XYZ Electricals Ltd":    os.path.join("test_data", "bidder_XYZ_Electricals"),
        "PQR Power Systems":      os.path.join("test_data", "bidder_PQR_Power"),
    }

    bidder_map = {}
    for b_name, folder in bidder_dir_map.items():
        b_record = Bidder(tender_id=tender.id, name=b_name, final_status="Pending")
        db.add(b_record)
        db.commit()
        db.refresh(b_record)
        bidder_map[b_name] = b_record

        if os.path.exists(folder):
            pdf_files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".pdf"))
            print(f"\n[INGEST] {b_name}: {len(pdf_files)} PDFs", flush=True)
            for i, pf in enumerate(pdf_files, 1):
                file_path = os.path.join(folder, pf)
                print(f"  [{i}/{len(pdf_files)}] {pf} ... ", end="", flush=True)
                with open(file_path, "rb") as f_obj:
                    ingest_pdf_document(
                        db=db,
                        file_bytes=f_obj.read(),
                        file_name=pf,
                        document_type="Bidder Document",
                        bidder_id=b_record.id
                    )
                print("OK", flush=True)
        else:
            print(f"  [WARN] Folder not found: {folder}", flush=True)

    return tender, bidder_map, True


def run_benchmark_on_test_data(sample_limit: int = 10, force_reingest: bool = False):
    """
    Runs evaluation on a representative slice of the ground truth dataset,
    compares findings with answer_key.csv, and prints a structured scorecard.
    """
    print("=" * 70, flush=True)
    print("  TBE WORKBENCH - BENCHMARK EVALUATION", flush=True)
    print("=" * 70, flush=True)

    init_db()
    db = SessionLocal()

    csv_path = os.path.join("test_data", "answer_key.csv")
    if not os.path.exists(csv_path):
        print(f"[ERROR] {csv_path} not found.", flush=True)
        db.close()
        return

    df_key = pd.read_csv(csv_path)
    print(f"[INFO] Answer Key loaded: {len(df_key)} rows total", flush=True)

    # 1. Get or create benchmark tender (reuses existing if possible)
    tender, bidder_db_map, is_new = get_or_create_benchmark_tender(db, force_reingest)

    # 2. Select sample rows
    sample_df = df_key.head(sample_limit)
    print(f"\n[INFO] Running on first {len(sample_df)} rows "
          f"({'all' if sample_limit >= len(df_key) else 'sample'}).", flush=True)

    # 3. Get or create baseline
    baseline = db.query(BaselineVersion).filter(
        BaselineVersion.tender_id == tender.id
    ).first()
    if not baseline:
        baseline = BaselineVersion(tender_id=tender.id, version_number=1)
        db.add(baseline)
        db.commit()
        db.refresh(baseline)

    # 4. Get/create requirements (idempotent: skip if already created)
    req_map = {}
    existing_reqs = db.query(Requirement).filter(
        Requirement.baseline_version_id == baseline.id
    ).all()
    for r in existing_reqs:
        req_map[r.clause] = r

    for _, row in sample_df.iterrows():
        clause = str(row["clause"]).strip()
        if clause not in req_map:
            req = Requirement(
                baseline_version_id=baseline.id,
                clause=clause,
                text=str(row["requirement"]).strip(),
                is_QR=bool(row["is_qualification"]),
                not_applicable=False
            )
            db.add(req)
            db.commit()
            db.refresh(req)
            req_map[clause] = req

    # 5. Run Verification row by row
    print(f"\n{'=' * 70}", flush=True)
    print("  RUNNING LIVE AI VERIFICATION", flush=True)
    print(f"{'=' * 70}", flush=True)

    matches = 0
    false_complied_count = 0
    results_summary = []

    for i, (idx, row) in enumerate(sample_df.iterrows(), 1):
        b_name = str(row["bidder"]).strip()
        clause = str(row["clause"]).strip()
        expected_result = str(row["correct_result"]).strip()
        is_trap = bool(row.get("is_trap", False))
        needs_ocr = bool(row.get("needs_ocr", False))

        bidder = bidder_db_map.get(b_name)
        if not bidder:
            print(f"  [{i}/{len(sample_df)}] [SKIP] Unknown bidder: {b_name}", flush=True)
            continue

        req = req_map.get(clause)
        if not req:
            print(f"  [{i}/{len(sample_df)}] [SKIP] Unknown clause: {clause}", flush=True)
            continue

        print(
            f"  [{i:02d}/{len(sample_df)}] {b_name[:20]:<20} Clause {clause:<8} "
            f"{'[TRAP]' if is_trap else '      '} {'[OCR]' if needs_ocr else '     '} ... ",
            end="", flush=True
        )

        # Clear previous finding so we re-verify fresh
        existing_finding = (
            db.query(Finding)
            .filter(Finding.requirement_id == req.id, Finding.bidder_id == bidder.id)
            .first()
        )
        if existing_finding:
            db.delete(existing_finding)
            db.commit()

        finding = verify_requirement_for_bidder(db, req, bidder)
        actual_result = finding.ai_status.strip()

        is_false_complied = (
            actual_result.lower() == "complied"
            and expected_result.lower() == "not complied"
        )
        if is_false_complied:
            false_complied_count += 1

        is_match = actual_result.lower() == expected_result.lower()
        if is_match:
            matches += 1

        match_tag = "[MATCH]    " if is_match else "[MISMATCH] "
        safety_tag = "[DANGEROUS]" if is_false_complied else "[SAFE]     "
        print(f"{match_tag} {safety_tag} -> AI: {actual_result}", flush=True)

        import time
        time.sleep(1.5)

        results_summary.append({
            "row": i,
            "bidder": b_name,
            "clause": clause,
            "expected": expected_result,
            "actual": actual_result,
            "match": "MATCH" if is_match else "MISMATCH",
            "false_complied": "DANGEROUS" if is_false_complied else "SAFE",
            "is_trap": is_trap,
            "needs_ocr": needs_ocr,
            "evidence": (finding.remark or "None")[:120],
        })

    db.close()

    # 6. Final Scorecard
    print(f"\n{'=' * 70}", flush=True)
    print("  SCORECARD - DETAILED RESULTS", flush=True)
    print(f"{'=' * 70}", flush=True)
    print(
        f"{'#':<4} {'Bidder':<22} {'Clause':<10} {'Expected':<22} {'AI Result':<22} "
        f"{'Match':<10} {'Safety':<12} {'Trap':<5} {'OCR':<4}",
        flush=True
    )
    print("-" * 115, flush=True)
    for r in results_summary:
        print(
            f"{r['row']:<4} {r['bidder'][:21]:<22} {r['clause']:<10} "
            f"{r['expected'][:21]:<22} {r['actual'][:21]:<22} "
            f"{r['match']:<10} {r['false_complied']:<12} "
            f"{'Y' if r['is_trap'] else 'N':<5} {'Y' if r['needs_ocr'] else 'N':<4}",
            flush=True
        )

    total_tested = len(results_summary)
    accuracy = (matches / total_tested * 100) if total_tested > 0 else 0
    trap_rows = [r for r in results_summary if r["is_trap"]]
    trap_matches = sum(1 for r in trap_rows if r["match"] == "MATCH")

    print(f"\n{'=' * 70}", flush=True)
    print("  FINAL SCORECARD", flush=True)
    print(f"{'=' * 70}", flush=True)
    print(f"  Total Rows Tested  : {total_tested}", flush=True)
    print(f"  Overall Accuracy   : {accuracy:.1f}%  ({matches}/{total_tested})", flush=True)
    print(f"  False 'Complied'   : {false_complied_count}  (TARGET: ZERO)", flush=True)
    print(f"  Trap Row Accuracy  : {trap_matches}/{len(trap_rows)} trap rows handled correctly", flush=True)
    print(f"{'=' * 70}", flush=True)

    if false_complied_count == 0:
        print("  [PASS] SAFETY CHECK: No false 'Complied' results.", flush=True)
    else:
        print(f"  [FAIL] SAFETY CHECK: {false_complied_count} dangerous false Complied results!", flush=True)

    print(f"{'=' * 70}", flush=True)

    return results_summary


if __name__ == "__main__":
    full_run = "--full" in sys.argv
    reingest = "--reingest" in sys.argv
    limit = 55 if full_run else 10
    run_benchmark_on_test_data(sample_limit=limit, force_reingest=reingest)
