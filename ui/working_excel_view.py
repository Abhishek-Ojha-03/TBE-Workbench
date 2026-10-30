"""
UI Module for Screen 5: TBE Working Excel (Core Engine View).
Activities 6, 7, 8, 10, 12, 13, 14 in Workflow Document:
- Generate Working Excel
- Upload Bidder Documents all together
- Verify Bidder (AI extracts evidence & fills cells)
- Human Verification direct entry
- Re-verification of flagged rows
- Confirm Technical Status
- Download final TBE Excel
"""
import os
import io
import zipfile
import tempfile
import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session

from db.models import Tender, Bidder, Document, Finding, Requirement
from db.baseline_service import get_latest_baseline, get_baseline_requirements, get_bidders_for_tender
from reading.ingest import ingest_pdf_document, ingest_bidder_bundle_parallel, ingest_documents_concurrently
from ai.verifier import verify_all_requirements_for_bidder, verify_all_bidders
from rules.rule_engine import update_bidder_qualification_status
from outputs.excel_generator import WorkingExcelGenerator


def render_working_excel_screen(db: Session, tender: Tender):
    st.markdown(f"## 📊 TBE Working Excel & Bidder Dossiers: `{tender.nit_no}`")

    latest_baseline = get_latest_baseline(db, tender.id)
    bidders = get_bidders_for_tender(db, tender.id)

    if not latest_baseline:
        st.warning("Please approve the requirements baseline first in Screen 2.")
        return

    if not bidders:
        st.warning("Please set up at least one bidder in Screen 4.")
        return

    # Section A: Generate Working Excel
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Working TBE Master Matrix")
        st.caption("Layout: Qualification Requirements (QR) first, blank separator row, then technical specs.")
    with col2:
        if st.button("📥 Generate & Download Working Excel", type="primary", use_container_width=True):
            excel_gen = WorkingExcelGenerator()
            out_path, _ = excel_gen.generate_working_excel(db, tender)
            with open(out_path, "rb") as f:
                st.download_button(
                    label="💾 Click to Download .xlsx",
                    data=f.read(),
                    file_name=os.path.basename(out_path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

    st.divider()

    # ── Section ZIP: Bulk Upload ALL Bidders via ZIP ──────────────────────────
    with st.expander("📦 Bulk Ingest ALL Bidders via ZIP File (Upload Once for All)", expanded=False):
        st.caption(
            "ZIP must contain one sub-folder per bidder, each folder holding that bidder's PDFs. "
            "Example structure: `bidders.zip → Bidder_01_Apex/ → 01_Technical_Offer.pdf, ...`"
        )
        zip_file = st.file_uploader(
            "Upload ZIP containing all bidder folders",
            type=["zip"],
            key="bulk_zip_uploader",
            help="Each sub-folder inside the ZIP becomes one bidder. Nested sub-folders are ignored."
        )

        if zip_file and st.button("🚀 Extract & Ingest ALL Bidders from ZIP", type="primary", key="btn_bulk_zip_ingest"):
            import time
            from db.connection import SessionLocal
            from db.models import Bidder as BidderModel
            from reading.ingest import ingest_documents_concurrently

            zip_bytes = zip_file.read()

            zip_pbar  = st.progress(0.0, text="Extracting ZIP...")
            zip_log   = st.empty()
            zip_done  = st.empty()
            z_start   = time.time()

            try:
                zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
            except Exception as ze:
                st.error(f"Could not open ZIP: {ze}")
                st.stop()

            # ── Discover bidder folders ──
            # Handles both:
            # 1. Root structure: Bidder_01_Apex/01_Technical_Offer.pdf
            # 2. Nested zip: synthetic_50_bidders/Bidder_01_Apex/01_Technical_Offer.pdf
            import re
            all_names = zf.namelist()

            # Map:  bidder_folder_name  →  [zip_member_paths of PDFs inside it]
            bidder_folders: dict[str, list[str]] = {}
            for name in all_names:
                parts = [p for p in name.replace("\\", "/").split("/") if p]
                if len(parts) >= 2:
                    filename = parts[-1]
                    # The immediate parent directory of the PDF is the bidder folder
                    folder = parts[-2]
                    if filename.lower().endswith(".pdf"):
                        bidder_folders.setdefault(folder, []).append(name)

            if not bidder_folders:
                st.error(
                    "No PDF files found inside sub-folders in the ZIP. "
                    "Make sure the ZIP contains folders with PDFs inside."
                )
                st.stop()

            total_folders = len(bidder_folders)
            zip_log.info(f"Found **{total_folders} bidder folders** in ZIP. Starting ingestion...")

            completed      = 0
            total_docs_done = 0

            for folder_name, pdf_paths in bidder_folders.items():
                # Extract numeric bidder ID if present (e.g. 'Bidder_01_Apex' -> '1')
                match = re.search(r"\d+", folder_name)
                bidder_num_str = str(int(match.group())) if match else None

                # Create or find Bidder record
                thread_db = SessionLocal()
                try:
                    existing = thread_db.query(BidderModel).filter(
                        BidderModel.tender_id == tender.id,
                        BidderModel.name == folder_name
                    ).first()

                    # Fallback match: if bidder is named '1', '2', etc. in DB
                    if not existing and bidder_num_str:
                        existing = thread_db.query(BidderModel).filter(
                            BidderModel.tender_id == tender.id,
                            BidderModel.name == bidder_num_str
                        ).first()

                    if not existing:
                        new_bidder = BidderModel(
                            tender_id=tender.id,
                            name=folder_name,
                            final_status="Pending"
                        )
                        thread_db.add(new_bidder)
                        thread_db.commit()
                        thread_db.refresh(new_bidder)
                        b_id = new_bidder.id
                        matched_display_name = folder_name
                    else:
                        b_id = existing.id
                        matched_display_name = f"{existing.name} ({folder_name})"
                finally:
                    thread_db.close()

                # Read PDF bytes from ZIP in memory
                files_data = []
                for pdf_path in pdf_paths:
                    try:
                        pdf_bytes    = zf.read(pdf_path)
                        pdf_filename = pdf_path.replace("\\", "/").split("/")[-1]
                        files_data.append((pdf_filename, pdf_bytes))
                    except Exception:
                        pass

                if files_data:
                    doc_count = ingest_documents_concurrently(b_id, files_data, max_workers=4)
                    total_docs_done += doc_count

                completed += 1
                elapsed    = time.time() - z_start
                zip_pbar.progress(
                    completed / total_folders,
                    text=f"Ingesting... {completed}/{total_folders} bidders | {elapsed:.1f}s elapsed"
                )
                zip_log.markdown(
                    f"✅ **{folder_name}** — {len(files_data)} PDFs | "
                    f"{completed}/{total_folders} bidders done | `{elapsed:.1f}s`"
                )

            zf.close()
            total_z_time = time.time() - z_start
            zip_pbar.progress(1.0, text="Done!")
            zip_done.success(
                f"Bulk ingestion complete — **{total_folders} bidders**, "
                f"**{total_docs_done} documents** indexed in **{total_z_time:.1f}s**"
            )
            st.rerun()

    # ── Section B: Upload Bidder Documents & Run AI Verification ──────────────
    st.subheader("Bidder Document Ingestion & AI Verification")
    
    # Dual Master Action Bar: Ingest ALL Bidders & Verify ALL Bidders
    col_ingest_all, col_verify_all = st.columns(2)
    
    with col_ingest_all:
        if st.button("⚡ Ingest ALL Staged Documents for ALL Bidders", type="secondary", use_container_width=True, key="btn_ingest_all_staged"):
            # Gather all staged files from every bidder's uploader in session_state
            staged_bundles = {}
            for b in bidders:
                files = st.session_state.get(f"bidder_docs_{b.id}")
                if files:
                    staged_bundles[b.id] = (b.name, [(f.name, f.read()) for f in files])
            
            if not staged_bundles:
                st.warning("⚠️ No documents staged! Please browse/select PDF files in the bidder tabs below first.")
            else:
                total_files = sum(len(f_list) for _, (_, f_list) in staged_bundles.items())
                ingest_status = st.status(f"⚡ Ingesting {total_files} documents across {len(staged_bundles)} bidders in parallel...", expanded=True)
                with ingest_status:
                    import time
                    from concurrent.futures import ThreadPoolExecutor, as_completed
                    from reading.ingest import ingest_documents_concurrently

                    i_pbar = st.progress(0.0)
                    i_text = st.empty()
                    i_start = time.time()
                    
                    completed_bidders = 0
                    total_b_count = len(staged_bundles)
                    total_docs_done = 0

                    def _ingest_bidder(b_id, b_name, files_data):
                        count = ingest_documents_concurrently(b_id, files_data, max_workers=4)
                        return b_name, count

                    with ThreadPoolExecutor(max_workers=min(len(staged_bundles), 4)) as executor:
                        future_to_b = {
                            executor.submit(_ingest_bidder, b_id, b_info[0], b_info[1]): b_id
                            for b_id, b_info in staged_bundles.items()
                        }
                        for future in as_completed(future_to_b):
                            completed_bidders += 1
                            b_name, doc_count = future.result()
                            total_docs_done += doc_count
                            i_pbar.progress(completed_bidders / total_b_count)
                            elapsed = time.time() - i_start
                            i_text.markdown(f"✅ Ingested **{b_name}** ({doc_count} files) | Elapsed: `{elapsed:.1f}s`")

                    total_i_time = time.time() - i_start
                    i_pbar.progress(1.0)
                    ingest_status.update(label=f"✅ Ingestion complete! {total_docs_done} files indexed in {total_i_time:.1f}s", state="complete", expanded=False)
                    st.session_state["last_ingestion_time"] = round(total_i_time, 1)
                    st.session_state["last_ingestion_doc_count"] = total_docs_done
                    st.success(f"Successfully ingested {total_docs_done} documents across all bidders in {total_i_time:.1f} seconds!")
                    st.rerun()

    with col_verify_all:
        if st.button("🚀 Run AI Verification for ALL Bidders", type="primary", use_container_width=True, key="btn_run_all_bidders"):
            status_box = st.status("🚀 Running AI Verification for all bidders in parallel...", expanded=True)
            with status_box:
                import queue
                import threading
                import time
                from concurrent.futures import ThreadPoolExecutor
                from db.connection import SessionLocal
                from rules.rule_engine import update_bidder_qualification_status

                p_bar = st.progress(0.0)
                status_text = st.empty()
                
                # Live timer and speed metrics
                start_time = time.time()
                
                # Thread-safe queue for UI progress updates
                q = queue.Queue()
                b_names = {b.id: b.name for b in bidders}
                total_bidders = len(bidders)
                bidder_status_map = {b.name: "Starting..." for b in bidders}
                clause_history = {}  # Track timestamps per clause

                def worker_task(b_id, b_name):
                    thread_db = SessionLocal()
                    try:
                        def _on_clause(cur, tot, clause):
                            q.put(("progress", b_name, cur, tot, clause, time.time()))
                        
                        verify_all_requirements_for_bidder(thread_db, tender.id, b_id, progress_callback=_on_clause)
                        status_res = update_bidder_qualification_status(thread_db, b_id)
                        q.put(("bidder_done", b_name, status_res))
                    except Exception as err:
                        q.put(("error", b_name, str(err)))
                    finally:
                        thread_db.close()

                # High-speed Worker Pool:
                # 3 concurrent worker threads aligned with our 3 round-robin keys.
                # Each thread gets its own dedicated key in lockstep, maximizing parallel speed
                # while preventing burst rate saturation.
                NUM_CONCURRENT_WORKERS = min(3, max(len(bidders), 1))
                executor = ThreadPoolExecutor(max_workers=NUM_CONCURRENT_WORKERS)
                futures = [executor.submit(worker_task, b.id, b.name) for b in bidders]
                executor.shutdown(wait=False)

                completed_bidders = 0
                clause_counts = {b.name: (0, 1) for b in bidders}

                # Main thread drains the queue and safely updates Streamlit UI
                while completed_bidders < total_bidders:
                    try:
                        msg = q.get(timeout=0.2)
                        msg_type = msg[0]
                        if msg_type == "progress":
                            _, b_name, cur, tot, clause, t_stamp = msg
                            clause_counts[b_name] = (cur, tot)
                            clause_history[b_name] = t_stamp
                            bidder_status_map[b_name] = f"Clause `{clause}` ({cur}/{tot})"
                        elif msg_type == "bidder_done":
                            _, b_name, status_res = msg
                            completed_bidders += 1
                            bidder_status_map[b_name] = f"✅ Completed ({status_res})"
                        elif msg_type == "error":
                            _, b_name, err_str = msg
                            completed_bidders += 1
                            bidder_status_map[b_name] = f"⚠️ Error: {err_str}"
                    except queue.Empty:
                        pass

                    # Compute overall progress & timings
                    elapsed = time.time() - start_time
                    total_clauses = sum(tot for cur, tot in clause_counts.values()) or 1
                    done_clauses = sum(cur for cur, tot in clause_counts.values())
                    overall_pct = min(max(done_clauses / total_clauses, 0.0), 1.0)
                    p_bar.progress(overall_pct)

                    # Dynamic speed calculations
                    avg_per_clause = (elapsed / done_clauses) if done_clauses > 0 else 1.8
                    remaining_clauses = max(total_clauses - done_clauses, 0)
                    # Because bidders run concurrently, est remaining is max remaining per bidder * avg
                    max_pending_per_bidder = max((tot - cur for cur, tot in clause_counts.values()), default=0)
                    est_remaining = max_pending_per_bidder * avg_per_clause

                    # Update status text with live timer & stats
                    timing_header = f"⏱️ **Elapsed:** `{elapsed:.1f}s` | ⚡ **Avg per Clause:** `{avg_per_clause:.2f}s` | ⏳ **Est. Remaining:** `{est_remaining:.1f}s`\n\n"
                    lines = [f"- **{name}:** {st_txt}" for name, st_txt in bidder_status_map.items()]
                    status_text.markdown(timing_header + "\n".join(lines))

                total_time = time.time() - start_time
                p_bar.progress(1.0)
                status_box.update(
                    label=f"✅ Batch AI Verification complete! ({total_time:.1f}s total)",
                    state="complete",
                    expanded=False
                )
                st.session_state["last_verification_time"] = round(total_time, 1)
                st.success(f"All bidders evaluated in parallel in {total_time:.1f} seconds! (~{total_time/max(total_clauses, 1):.2f}s per evaluation)")
                st.rerun()

    tabs = st.tabs([f"🏢 {b.name} ({b.final_status})" for b in bidders])

    for idx, bidder in enumerate(bidders):
        with tabs[idx]:
            c_up, c_run = st.columns([2, 1])
            with c_up:
                uploaded_files = st.file_uploader(
                    f"Upload all documents for {bidder.name} (PDFs)",
                    type=["pdf"],
                    accept_multiple_files=True,
                    key=f"bidder_docs_{bidder.id}"
                )
                if uploaded_files:
                    if st.button(f"⚡ Fast Parallel Ingest ({len(uploaded_files)} Documents)", type="primary", key=f"btn_ingest_{bidder.id}"):
                        with st.spinner(f"Ingesting {len(uploaded_files)} PDFs concurrently using background workers..."):
                            import time
                            i_start = time.time()
                            files_data = [(uf.name, uf.read()) for uf in uploaded_files]
                            count = ingest_documents_concurrently(bidder.id, files_data, max_workers=6)
                            i_dur = round(time.time() - i_start, 1)
                            st.session_state["last_ingestion_time"] = i_dur
                            st.success(f"Fast Ingest Complete! {count} documents indexed in {i_dur} seconds.")
                            st.rerun()

            with c_run:
                st.write("")
                st.write("")
                if st.button(f"🤖 Run AI Verification for {bidder.name}", type="primary", key=f"run_verify_{bidder.id}", use_container_width=True):
                    with st.spinner(f"AI evaluating {bidder.name} against baseline requirements with quote verification..."):
                        findings = verify_all_requirements_for_bidder(db, tender.id, bidder.id)
                        status = update_bidder_qualification_status(db, bidder.id)
                        st.success(f"Verification complete! Bidder Status: {status}")
                        st.rerun()

            # Display uploaded files
            docs = db.query(Document).filter(Document.bidder_id == bidder.id).all()
            if docs:
                st.write(f"**Submitted Files ({len(docs)}):**")
                cols = st.columns(3)
                for d_i, d in enumerate(docs):
                    cols[d_i % 3].caption(f"📄 {d.file_name} ({len(d.pages)} pages)")

            # Live Grid View of findings & Direct Human Verification (Activity 10 & 13)
            active_req_ids = [r.id for r in latest_baseline.requirements if not r.not_applicable]
            findings = db.query(Finding).filter(
                Finding.bidder_id == bidder.id,
                Finding.requirement_id.in_(active_req_ids)
            ).all()
            if findings:
                # Calculate Parameter Match Accuracy Metrics
                total_clauses = len(findings)
                complied_count = sum(1 for f in findings if (f.engineer_status == "Complied" or (not f.engineer_status and f.ai_status == "Complied")))
                not_complied_count = sum(1 for f in findings if (f.engineer_status == "Not Complied" or (not f.engineer_status and f.ai_status == "Not Complied")))
                review_count = total_clauses - complied_count - not_complied_count
                accuracy_pct = round((complied_count / total_clauses) * 100, 1) if total_clauses > 0 else 0.0

                # Parameter Accuracy Summary KPI Row
                m_c1, m_c2, m_c3, m_c4, m_c5, m_c6 = st.columns(6)
                m_c1.metric("🎯 Match Accuracy", f"{accuracy_pct}%", help="Calculated as (Complied / Total) * 100")
                m_c2.metric("✅ Complied", f"{complied_count} / {total_clauses}")
                m_c3.metric("❌ Not Complied", f"{not_complied_count}")
                m_c4.metric("⚠️ Needs Review", f"{review_count}")
                
                last_i_time = st.session_state.get("last_ingestion_time")
                i_time_display = f"{last_i_time}s" if last_i_time else "-"
                m_c5.metric("📥 Ingest Time", i_time_display, help="Total execution duration for parallel document ingestion")

                last_time = st.session_state.get("last_verification_time")
                time_display = f"{last_time}s" if last_time else f"~{round(total_clauses * 1.8, 1)}s (est)"
                m_c6.metric("⚡ Verify Time", time_display, help="Total execution duration for AI verification")

                st.write(f"**Evaluation & Accuracy Matrix for {bidder.name}:**")
                table_rows = []
                for f in findings:
                    effective_status = f.engineer_status or f.ai_status
                    # Parameter accuracy score
                    if effective_status == "Complied":
                        acc_score = "100%"
                    elif effective_status == "Not Complied":
                        acc_score = "0%"
                    else:
                        acc_score = "Pending Review"

                    # Offered value / citation if available
                    offered_text = ""
                    if f.evidences:
                        ev = f.evidences[0]
                        p_no = ev.page.page_number if ev.page else "?"
                        doc_name = ev.page.document.file_name if (ev.page and ev.page.document) else "Doc"
                        offered_text = f'"{ev.quoted_text[:50]}..." [{doc_name} p.{p_no}]' if ev.quoted_text else ""

                    table_rows.append({
                        "Clause": f.requirement.clause or "-",
                        "Category": "QR" if f.requirement.is_QR else "Technical",
                        "Specification Requirement": f.requirement.text[:65] + "...",
                        "Bidder Offered Quote": offered_text or "(No quote found)",
                        "Status": effective_status,
                        "Parameter Accuracy": acc_score,
                        "Remarks": f.remark or ""
                    })
                df_matrix = pd.DataFrame(table_rows)

                def highlight_status(val):
                    if val == "Complied":
                        return "background-color: #d4edda; color: #155724; font-weight: bold;"
                    elif val == "Not Complied":
                        return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
                    elif "Review" in str(val):
                        return "background-color: #fff3cd; color: #856404; font-weight: bold;"
                    return ""

                def highlight_acc(val):
                    if val == "100%":
                        return "background-color: #e8f5e9; color: #2e7d32; font-weight: bold;"
                    elif val == "0%":
                        return "background-color: #ffebee; color: #c62828; font-weight: bold;"
                    elif "Pending" in str(val):
                        return "background-color: #fffde7; color: #f57f17; font-weight: bold;"
                    return ""

                styled_df = df_matrix.style.map(highlight_status, subset=["Status"]).map(highlight_acc, subset=["Parameter Accuracy"])
                st.dataframe(styled_df, use_container_width=True)

                # Direct Human Verification & Manual Cell Editing (Activity 10 & 13)
                with st.expander("✍️ Direct Engineer Human Verification (Quick Cell Update)", expanded=False):
                    c_sel, c_stat, c_btn = st.columns([2, 1, 1])
                    with c_sel:
                        f_options = {f.id: f"Clause {f.requirement.clause or '-'}: {f.requirement.text[:55]}... [AI: {f.ai_status}]" for f in findings}
                        selected_f_id = st.selectbox("Select Clause to verify/update:", options=list(f_options.keys()), format_func=lambda x: f_options[x], key=f"sel_dir_{bidder.id}")
                    with c_stat:
                        new_dir_status = st.selectbox("Engineer Status:", ["Complied", "Not Complied", "Needs Human Review"], key=f"stat_dir_{bidder.id}")
                    with c_btn:
                        st.write("")
                        st.write("")
                        if st.button("💾 Save Cell Status", key=f"btn_save_dir_{bidder.id}", use_container_width=True):
                            from db.audit_service import confirm_finding, override_finding
                            f_obj = db.query(Finding).filter(Finding.id == selected_f_id).first()
                            if new_dir_status == f_obj.ai_status:
                                confirm_finding(db, f_obj.id, who="Lead Engineer (Direct)")
                            else:
                                override_finding(db, f_obj.id, new_status=new_dir_status, reason="Direct engineer verification entered in TBE cell", who="Lead Engineer (Direct)")
                            update_bidder_qualification_status(db, bidder.id)
                            st.success(f"Updated status for Clause {f_obj.requirement.clause} to {new_dir_status}!")
                            st.rerun()

