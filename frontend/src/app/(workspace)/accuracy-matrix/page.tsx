"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import WorkspaceHeader from "@/components/layout/workspace-header";
import Badge from "@/components/ui/badge";
import Button from "@/components/ui/button";
import { AccuracyMatrixRow, ApiError, downloadAccuracyFormalReport, getAccuracyMatrix } from "@/lib/api";
import { useActiveTenderStore } from "@/lib/store";

type StatusFilter = "all" | "hallucinations" | "misses" | "passed";
type TrapFilter = "all" | "trap" | "non-trap";

function matchTone(audit: string): "violet" | "neutral" {
  return audit.startsWith("PASS") ? "violet" : "neutral";
}

export default function AccuracyMatrixPage() {
  const router = useRouter();
  const { tenderId, tenderName, clearActiveTender } = useActiveTenderStore();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [trapFilter, setTrapFilter] = useState<TrapFilter>("all");
  const [bidderFilter, setBidderFilter] = useState<string>("all");
  const [selectedRowIdx, setSelectedRowIdx] = useState<number | null>(null);

  const matrixQuery = useQuery({
    queryKey: ["accuracy-matrix", tenderId],
    queryFn: () => getAccuracyMatrix(tenderId as number),
    enabled: tenderId !== null,
    retry: false,
  });

  const downloadReportMutation = useMutation({
    mutationFn: () => downloadAccuracyFormalReport(tenderId as number),
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Failed to download the formal audit report.");
    },
  });

  const notFound = matrixQuery.error instanceof ApiError && matrixQuery.error.status === 404;
  const data = matrixQuery.data;
  const rows = useMemo(() => data?.rows ?? [], [data]);

  const bidderNames = useMemo(
    () => Array.from(new Set(rows.map((r) => r.bidder))).sort(),
    [rows]
  );

  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      if (bidderFilter !== "all" && r.bidder !== bidderFilter) return false;
      if (statusFilter === "hallucinations" && !r.audit_match.includes("CRITICAL")) return false;
      if (statusFilter === "misses" && !r.audit_match.includes("MISS")) return false;
      if (statusFilter === "passed" && !r.audit_match.startsWith("PASS")) return false;
      if (trapFilter === "trap" && !r.is_trap_clause) return false;
      if (trapFilter === "non-trap" && r.is_trap_clause) return false;
      return true;
    });
  }, [rows, bidderFilter, statusFilter, trapFilter]);

  const selectedRow: AccuracyMatrixRow | null =
    selectedRowIdx !== null && filteredRows[selectedRowIdx] ? filteredRows[selectedRowIdx] : null;

  if (tenderId === null) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
        <p className="text-h3 text-neutral-300">No tender selected</p>
        <p className="max-w-md text-b2 text-neutral-75">
          Open a tender from the Home screen first — this page needs to know which
          tender&apos;s AI verdicts to audit.
        </p>
        <button
          type="button"
          onClick={() => router.push("/")}
          className="rounded-md bg-violet-300 px-5 py-2.5 text-b2 font-medium text-white hover:bg-violet-400"
        >
          Go to Home
        </button>
      </div>
    );
  }

  return (
    <>
      <WorkspaceHeader
        title="Accuracy Matrix"
        tenderOptions={[tenderName ?? "Tender"]}
        onBack={() => {
          clearActiveTender();
          router.push("/");
        }}
      />

      <div className="mb-6 flex items-center justify-between gap-4">
        <p className="text-b2 text-neutral-75">
          Evaluating AI verdicts against Ground Truth benchmarks to verify zero-hallucination.
        </p>
        <Button
          variant="primary"
          disabled={downloadReportMutation.isPending}
          onClick={() => downloadReportMutation.mutate()}
        >
          {downloadReportMutation.isPending ? "Downloading..." : "Download Formal Audit Report (.docx)"}
        </Button>
      </div>

      {matrixQuery.isLoading && (
        <p className="py-8 text-center text-b2 text-neutral-75">Loading accuracy matrix...</p>
      )}

      {notFound && (
        <div className="rounded-lg border border-neutral-50 p-5 text-b2 text-neutral-300">
          Ground Truth Answer Key not found in test_data/ on the server. This benchmark view
          requires the synthetic bidder test set — it is not available for a regular client
          tender.
        </div>
      )}

      {data && data.total_evals === 0 && !data.has_bidders && (
        <div className="rounded-lg border border-neutral-50 p-5 text-b2 text-neutral-300">
          No bidders found for this tender. Upload bidders in TBE Working Excel first.
        </div>
      )}

      {data && data.total_evals === 0 && data.has_bidders && (
        <div className="rounded-lg border border-neutral-50 p-5 text-b2 text-neutral-300">
          Bidders are uploaded, but AI Verification has not been run yet. Run AI Verification for
          ALL Bidders on the TBE Working Excel screen first.
        </div>
      )}

      {data && data.total_evals > 0 && (
        <>
          <div className="mb-6 rounded-lg bg-violet-50 px-5 py-4 text-b2 text-violet-300">
            Clause-level evaluation — {data.total_evals} clause verdicts scored across{" "}
            {data.bidder_count} bidders. TP={data.tp} TN={data.tn} FP={data.fp} FN={data.fn}
          </div>

          <div className="mb-6 grid grid-cols-4 gap-4">
            <div className="rounded-lg border border-neutral-50 p-4">
              <p className="text-b3 text-neutral-100">Overall Accuracy</p>
              <p className="text-h1 font-semibold text-neutral-300">{data.accuracy_pct}%</p>
              <p className="mt-1 text-b3 text-neutral-75">(TP + TN) / total evaluated clauses</p>
            </div>
            <div className="rounded-lg border border-neutral-50 p-4">
              <p className="text-b3 text-neutral-100">Precision (Zero-Hallucination)</p>
              <p className="text-h1 font-semibold text-neutral-300">{data.precision_pct}%</p>
              <p className="mt-1 text-b3 text-neutral-75">TP / (TP + FP)</p>
            </div>
            <div className="rounded-lg border border-neutral-50 p-4">
              <p className="text-b3 text-neutral-100">Recall (Coverage Rate)</p>
              <p className="text-h1 font-semibold text-neutral-300">{data.recall_pct}%</p>
              <p className="mt-1 text-b3 text-neutral-75">TP / (TP + FN)</p>
            </div>
            <div className="rounded-lg border border-neutral-50 p-4">
              <p className="text-b3 text-neutral-100">Hallucination Count (FP)</p>
              <p className="text-h1 font-semibold text-neutral-300">{data.fp}</p>
              <p className="mt-1 text-b3 text-neutral-75">
                {data.fp === 0 ? "Goal met — zero hallucinations" : `${data.fp} traps missed`}
              </p>
            </div>
          </div>

          <h3 className="mb-3 text-h3 text-neutral-300">Confusion Matrix (2×2)</h3>
          <div className="mb-6 grid grid-cols-2 gap-4">
            <div className="rounded-lg border border-neutral-50 p-4">
              <p className="text-b2 font-medium text-neutral-300">True Complied (TP): {data.tp}</p>
              <p className="mt-1 text-b3 text-neutral-75">
                Clause from a Qualified bidder — AI correctly said Complied with a cited quote.
              </p>
            </div>
            <div className="rounded-lg border border-neutral-50 p-4">
              <p className="text-b2 font-medium text-neutral-300">True Disqualified (TN): {data.tn}</p>
              <p className="mt-1 text-b3 text-neutral-75">
                Clause from a trap/failed bidder — AI correctly said Not Complied or flagged for
                review.
              </p>
            </div>
            <div className="rounded-lg border border-neutral-50 p-4">
              <p className="text-b2 font-medium text-neutral-300">
                Hallucination / False Complied (FP): {data.fp}
              </p>
              <p className="mt-1 text-b3 text-neutral-75">
                Critical risk: clause from a trap/disqualified bidder — AI mistakenly said
                Complied.
              </p>
            </div>
            <div className="rounded-lg border border-neutral-50 p-4">
              <p className="text-b2 font-medium text-neutral-300">False Disqualified (FN): {data.fn}</p>
              <p className="mt-1 text-b3 text-neutral-75">
                Clause from a Qualified bidder — AI said Not Complied or Needs Review incorrectly.
              </p>
            </div>
          </div>

          <h3 className="mb-3 text-h3 text-neutral-300">Value Trap Inspection &amp; Audit Drilldown</h3>
          <div className="mb-4 flex gap-3">
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value as StatusFilter);
                setSelectedRowIdx(null);
              }}
              className="rounded-md border border-neutral-50 px-3 py-2 text-b3 text-neutral-300 focus:outline-none"
            >
              <option value="all">All Evaluated Clauses</option>
              <option value="hallucinations">Hallucinations Only (FP)</option>
              <option value="misses">Misses Only (FN)</option>
              <option value="passed">Passed Clauses Only</option>
            </select>
            <select
              value={trapFilter}
              onChange={(e) => {
                setTrapFilter(e.target.value as TrapFilter);
                setSelectedRowIdx(null);
              }}
              className="rounded-md border border-neutral-50 px-3 py-2 text-b3 text-neutral-300 focus:outline-none"
            >
              <option value="all">All Clauses</option>
              <option value="trap">Trap Clauses Only</option>
              <option value="non-trap">Non-Trap Clauses</option>
            </select>
            <select
              value={bidderFilter}
              onChange={(e) => {
                setBidderFilter(e.target.value);
                setSelectedRowIdx(null);
              }}
              className="rounded-md border border-neutral-50 px-3 py-2 text-b3 text-neutral-300 focus:outline-none"
            >
              <option value="all">All Bidders</option>
              {bidderNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          <div className="mb-2 max-h-[500px] overflow-auto rounded-lg border border-neutral-50">
            <table className="w-full text-left text-b3">
              <thead className="sticky top-0 bg-neutral-50 text-neutral-100">
                <tr>
                  <th className="px-4 py-3 font-normal">Bidder</th>
                  <th className="px-4 py-3 font-normal">Clause</th>
                  <th className="px-4 py-3 font-normal">Requirement</th>
                  <th className="px-4 py-3 font-normal">Ground Truth</th>
                  <th className="px-4 py-3 font-normal">AI Verdict</th>
                  <th className="px-4 py-3 font-normal">Trap</th>
                  <th className="px-4 py-3 font-normal">Audit Match</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((r, idx) => (
                  <tr
                    key={idx}
                    onClick={() => setSelectedRowIdx(idx)}
                    className={`cursor-pointer border-t border-neutral-50 ${
                      selectedRowIdx === idx ? "bg-violet-50" : "hover:bg-neutral-50"
                    }`}
                  >
                    <td className="px-4 py-3 text-neutral-300">{r.bidder}</td>
                    <td className="px-4 py-3 text-neutral-300">{r.clause}</td>
                    <td className="max-w-[280px] truncate px-4 py-3 text-neutral-300">
                      {r.requirement_text}
                    </td>
                    <td className="px-4 py-3 text-neutral-300">{r.ground_truth_answer}</td>
                    <td className="px-4 py-3 text-neutral-300">{r.ai_verdict}</td>
                    <td className="px-4 py-3 text-neutral-300">{r.is_trap_clause ? "Yes" : "No"}</td>
                    <td className="px-4 py-3">
                      <Badge tone={matchTone(r.audit_match)}>{r.audit_match}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mb-6 text-b3 text-neutral-75">
            Showing {filteredRows.length} of {rows.length} evaluated clauses. Click a row to
            inspect its full verbatim quote below.
          </p>

          {selectedRow && (
            <div className="rounded-lg border border-neutral-50 p-5">
              <h3 className="mb-3 text-h3 text-neutral-300">Verbatim Document Quote Inspector</h3>
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <p className="text-b3 text-neutral-100">
                    Bidder: {selectedRow.bidder} — {selectedRow.format_type}
                  </p>
                  <p className="mb-2 text-b3 text-neutral-100">
                    Test Category: {selectedRow.test_category} · Clause: {selectedRow.clause} ·
                    Trap Clause: {selectedRow.is_trap_clause ? "Yes" : "No"}
                  </p>
                  <p className="mb-1 text-b3 font-medium text-neutral-300">Specification Requirement</p>
                  <p className="rounded-md bg-neutral-50 px-4 py-3 text-b3 text-neutral-75">
                    {selectedRow.requirement_text}
                  </p>
                </div>
                <div>
                  <p className="mb-2 text-b3 text-neutral-100">
                    Ground Truth: {selectedRow.ground_truth_answer} &nbsp;|&nbsp; AI Verdict:{" "}
                    {selectedRow.ai_verdict}
                  </p>
                  <p className="mb-2 text-b3 text-neutral-100">Audit Status: {selectedRow.audit_match}</p>
                  <p className="mb-1 text-b3 font-medium text-neutral-300">
                    Verbatim Cited Quote from Document
                  </p>
                  <p className="mb-3 rounded-md bg-violet-50 px-4 py-3 text-b3 italic text-violet-300">
                    &quot;{selectedRow.full_quote}&quot;
                  </p>
                  <p className="text-b3 text-neutral-75">
                    AI Engine Explanation: {selectedRow.ai_remarks}
                  </p>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
