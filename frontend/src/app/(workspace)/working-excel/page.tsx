"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import WorkspaceHeader from "@/components/layout/workspace-header";
import Button from "@/components/ui/button";
import Badge from "@/components/ui/badge";
import InfoHint from "@/components/ui/info-hint";
import {
  ApiError,
  Bidder,
  Finding,
  downloadWorkingExcel,
  listBidders,
  listBidderDocuments,
  getFindings,
  bulkZipIngest,
  getBulkZipIngestProgress,
  ingestBidderDocuments,
  verifyBidder,
  qualifyBidder,
} from "@/lib/api";
import { useActiveTenderStore } from "@/lib/store";

function UploadIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 16V4M12 4l-4 4M12 4l4 4" />
      <path d="M4 16v3a2 2 0 002 2h12a2 2 0 002-2v-3" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 4v12M12 16l-4-4M12 16l4-4" />
      <path d="M4 20h16" />
    </svg>
  );
}

function badgeToneFor(status: string): "violet" | "neutral" {
  return status === "Qualified" ? "violet" : "neutral";
}

function statusTone(status: string): "violet" | "neutral" {
  return status === "Complied" ? "violet" : "neutral";
}

function effectiveStatus(f: Finding): string {
  return f.engineer_status || f.ai_status || "Pending";
}

function accuracyLabel(status: string): string {
  if (status === "Complied") return "100%";
  if (status === "Not Complied") return "0%";
  return "Pending Review";
}

/**
 * Chunked-concurrency runner for "Verify ALL Bidders" — Streamlit ran this
 * with 3 concurrent worker threads server-side with live per-clause
 * progress; here each bidder is its own HTTP call, run 3-at-a-time, with
 * progress reported after each bidder completes (coarser than per-clause,
 * but real and live rather than a single opaque "Verifying..." button).
 */
async function runWithConcurrency<T>(
  items: T[],
  concurrency: number,
  worker: (item: T) => Promise<void>
): Promise<void> {
  let next = 0;
  async function runNext(): Promise<void> {
    const i = next++;
    if (i >= items.length) return;
    await worker(items[i]);
    return runNext();
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, () => runNext()));
}

export default function WorkingExcelPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { tenderId, tenderName, clearActiveTender } = useActiveTenderStore();
  const [activeBidder, setActiveBidder] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Ephemeral per-session timings — same lifetime as Streamlit's
  // st.session_state equivalents (reset on page reload, not persisted).
  const [ingestTimes, setIngestTimes] = useState<Record<number, number>>({});
  const [verifyTimes, setVerifyTimes] = useState<Record<number, number>>({});
  const [verifyAllProgress, setVerifyAllProgress] = useState<
    { completed: number; total: number; statusByBidder: Record<number, string> } | null
  >(null);
  // Flips true once a bulk ingest has completed this session — gates the
  // "Run AI Verification for ALL Bidders" button so it's greyed out until
  // there's something ingested to verify.
  const [hasIngestedAll, setHasIngestedAll] = useState(false);
  const [bulkIngestStarted, setBulkIngestStarted] = useState(false);

  const bulkIngestProgressQuery = useQuery({
    queryKey: ["bulk-ingest-progress", tenderId],
    queryFn: () => getBulkZipIngestProgress(tenderId as number),
    enabled: tenderId !== null && bulkIngestStarted,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
  });

  const biddersQuery = useQuery({
    queryKey: ["bidders", tenderId],
    queryFn: () => listBidders(tenderId as number),
    enabled: tenderId !== null,
  });

  const downloadExcelMutation = useMutation({
    mutationFn: () => downloadWorkingExcel(tenderId as number),
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Failed to generate Working Excel.");
    },
  });

  const bulkZipIngestMutation = useMutation({
    mutationFn: () => bulkZipIngest(tenderId as number),
    onSuccess: () => {
      setBulkIngestStarted(true);
    },
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Bulk ZIP ingestion failed.");
    },
  });

  // Reflects the bulk ingest's completion into the gate for "Run AI
  // Verification for ALL Bidders" and refreshes the document lists once —
  // a ref guards against re-firing while status stays "complete" across
  // unrelated re-renders, same pattern used for specification progress.
  const hasHandledBulkIngestRef = useRef<string | null>(null);
  useEffect(() => {
    const status = bulkIngestProgressQuery.data?.status;
    if (status === "complete" && hasHandledBulkIngestRef.current !== "complete") {
      hasHandledBulkIngestRef.current = "complete";
      setHasIngestedAll(true);
      queryClient.invalidateQueries({ queryKey: ["bidder-documents", tenderId] });
    }
    if (status === "error") {
      hasHandledBulkIngestRef.current = "error";
    }
    if (status === "running") {
      hasHandledBulkIngestRef.current = null;
    }
  }, [bulkIngestProgressQuery.data?.status, queryClient, tenderId]);

  const bidders = biddersQuery.data ?? [];
  const bidder = bidders[activeBidder];

  const documentsQuery = useQuery({
    queryKey: ["bidder-documents", tenderId, bidder?.id],
    queryFn: () => listBidderDocuments(tenderId as number, bidder.id),
    enabled: tenderId !== null && !!bidder,
  });

  const findingsQuery = useQuery({
    queryKey: ["findings", tenderId, bidder?.id],
    queryFn: () => getFindings(tenderId as number, bidder.id),
    enabled: tenderId !== null && !!bidder,
  });

  const ingestMutation = useMutation({
    mutationFn: async (files: File[]) => {
      const start = performance.now();
      const res = await ingestBidderDocuments(tenderId as number, bidder.id, files);
      return { res, seconds: (performance.now() - start) / 1000 };
    },
    onSuccess: ({ res, seconds }) => {
      setIngestTimes((prev) => ({ ...prev, [bidder.id]: Math.round(seconds * 10) / 10 }));
      queryClient.invalidateQueries({ queryKey: ["bidder-documents", tenderId, bidder.id] });
      alert(`Ingested ${res.ingested_count} document(s) for ${bidder.name} in ${seconds.toFixed(1)}s.`);
    },
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Document ingestion failed.");
    },
  });

  const verifyMutation = useMutation({
    mutationFn: async () => {
      const start = performance.now();
      const res = await verifyBidder(tenderId as number, bidder.id);
      return { res, seconds: (performance.now() - start) / 1000 };
    },
    onSuccess: ({ seconds }) => {
      setVerifyTimes((prev) => ({ ...prev, [bidder.id]: Math.round(seconds * 10) / 10 }));
      queryClient.invalidateQueries({ queryKey: ["bidders", tenderId] });
      queryClient.invalidateQueries({ queryKey: ["findings", tenderId, bidder.id] });
    },
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "AI verification failed.");
    },
  });

  const verifyAllMutation = useMutation({
    mutationFn: async () => {
      const start = performance.now();
      setVerifyAllProgress({
        completed: 0,
        total: bidders.length,
        statusByBidder: Object.fromEntries(bidders.map((b) => [b.id, "Starting..."])),
      });

      await runWithConcurrency(bidders, 3, async (b: Bidder) => {
        try {
          const bStart = performance.now();
          await verifyBidder(tenderId as number, b.id);
          const bSeconds = Math.round(((performance.now() - bStart) / 1000) * 10) / 10;
          setVerifyTimes((prev) => ({ ...prev, [b.id]: bSeconds }));
          setVerifyAllProgress((prev) =>
            prev
              ? {
                  completed: prev.completed + 1,
                  total: prev.total,
                  statusByBidder: { ...prev.statusByBidder, [b.id]: `Completed (${bSeconds}s)` },
                }
              : prev
          );
        } catch (err) {
          setVerifyAllProgress((prev) =>
            prev
              ? {
                  completed: prev.completed + 1,
                  total: prev.total,
                  statusByBidder: {
                    ...prev.statusByBidder,
                    [b.id]: err instanceof ApiError ? `Error: ${err.message}` : "Error",
                  },
                }
              : prev
          );
        }
        queryClient.invalidateQueries({ queryKey: ["bidders", tenderId] });
        queryClient.invalidateQueries({ queryKey: ["findings", tenderId, b.id] });
      });

      return (performance.now() - start) / 1000;
    },
    onSuccess: (totalSeconds) => {
      alert(`AI verification complete for all bidders in ${totalSeconds.toFixed(1)}s.`);
    },
    onError: () => {
      alert("AI verification failed for one or more bidders — see per-bidder status above.");
    },
  });

  const ingestAllMutation = useMutation({
    mutationFn: async () => {
      // Matches Streamlit's "Ingest ALL Staged Documents for ALL Bidders" —
      // reuses the same saved-ZIP ingestion path since staged docs for all
      // bidders come from that one ZIP.
      return bulkZipIngest(tenderId as number);
    },
    onSuccess: () => {
      setBulkIngestStarted(true);
    },
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Ingestion failed.");
    },
  });

  const qualifyMutation = useMutation({
    mutationFn: (status: "Qualified" | "Not Qualified") =>
      qualifyBidder(tenderId as number, bidder!.id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bidders", tenderId] }),
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Failed to update qualification status.");
    },
  });

  if (tenderId === null) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
        <p className="text-h3 text-neutral-300">No tender selected</p>
        <p className="max-w-md text-b2 text-neutral-75">
          Open a tender from the Home screen first — this page needs to know which
          tender&apos;s bidder dossiers it&apos;s working with.
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

  const documents = documentsQuery.data ?? [];
  const findings = findingsQuery.data ?? [];

  const totalClauses = findings.length;
  const compliedCount = findings.filter((f) => effectiveStatus(f) === "Complied").length;
  const notCompliedCount = findings.filter((f) => effectiveStatus(f) === "Not Complied").length;
  const reviewCount = totalClauses - compliedCount - notCompliedCount;
  const accuracyPct = totalClauses > 0 ? Math.round((compliedCount / totalClauses) * 1000) / 10 : 0;

  // "Verified" = AI verification has run for at least one bidder, reflected
  // in final_status moving off the default "Pending" — used to gate the
  // Working Excel download, since it only makes sense once there's
  // something verified to fill it with.
  const hasVerifiedAny = bidders.some((b) => b.final_status !== "Pending");

  const ingestTimeDisplay = bidder && ingestTimes[bidder.id] !== undefined ? `${ingestTimes[bidder.id]}s` : "—";
  const verifyTimeDisplay =
    bidder && verifyTimes[bidder.id] !== undefined
      ? `${verifyTimes[bidder.id]}s`
      : totalClauses > 0
      ? `~${Math.round(totalClauses * 1.8 * 10) / 10}s (est)`
      : "—";

  return (
    <>
      <WorkspaceHeader
        title="TBE Working Excel"
        tenderOptions={[tenderName ?? "Tender"]}
        onBack={() => {
          clearActiveTender();
          router.push("/");
        }}
      />

      {/* Bulk ZIP ingestion */}
      <div className="mb-6 rounded-lg border border-neutral-50 p-5">
        <h3 className="mb-2 text-h3 text-neutral-300">Bulk Ingest ALL Bidders via ZIP File</h3>
        <p className="mb-4 text-b3 text-neutral-75">
          Reuses the ZIP already uploaded on Requirements &amp; Setup — no re-upload needed. Each
          bidder&apos;s folder of PDFs gets ingested in one pass.
        </p>
        <Button
          variant="primary"
          disabled={bulkZipIngestMutation.isPending}
          onClick={() => bulkZipIngestMutation.mutate()}
        >
          {bulkZipIngestMutation.isPending ? "Starting..." : "Extract & Ingest ALL Bidders from Saved ZIP"}
        </Button>

        {bulkIngestStarted && bulkIngestProgressQuery.data && (
          <div className="mt-4 rounded-md border border-neutral-50 p-4">
            <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-neutral-50">
              <div
                className="h-2 rounded-full bg-violet-300 transition-all"
                style={{
                  width: `${
                    (bulkIngestProgressQuery.data.completed / Math.max(bulkIngestProgressQuery.data.total, 1)) * 100
                  }%`,
                }}
              />
            </div>
            <p className="mb-2 text-b3 text-neutral-75">
              {bulkIngestProgressQuery.data.status === "running"
                ? `Ingesting ${bulkIngestProgressQuery.data.completed} / ${bulkIngestProgressQuery.data.total} bidder folders...`
                : bulkIngestProgressQuery.data.status === "complete"
                ? `Done — ${bulkIngestProgressQuery.data.completed} / ${bulkIngestProgressQuery.data.total} bidder folders processed.`
                : `Failed: ${bulkIngestProgressQuery.data.error ?? "unknown error"}`}
            </p>
            <div className="flex flex-col gap-1">
              {Object.entries(bulkIngestProgressQuery.data.status_by_bidder).map(([name, status]) => (
                <p key={name} className="text-b3 text-neutral-200">
                  <span className="font-medium text-neutral-300">{name}:</span> {status}
                </p>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Bidder Document Ingestion & AI Verification */}
      <h3 className="mb-4 text-h3 text-neutral-300">Bidder Document Ingestion &amp; AI Verification</h3>
      <div className="mb-3 flex gap-3">
        <Button
          variant="primary"
          className="flex-1 justify-center"
          disabled={ingestAllMutation.isPending}
          onClick={() => ingestAllMutation.mutate()}
        >
          {ingestAllMutation.isPending ? "Starting..." : "Ingest ALL Staged Documents for ALL Bidders"}
        </Button>
        <Button
          variant="primary"
          className="flex-1 justify-center"
          disabled={!hasIngestedAll || verifyAllMutation.isPending}
          title={!hasIngestedAll ? "Ingest bidder documents first — above — before running verification." : undefined}
          onClick={() => verifyAllMutation.mutate()}
        >
          {verifyAllMutation.isPending ? "Verifying..." : "Run AI Verification for ALL Bidders"}
        </Button>
      </div>

      {verifyAllProgress && (
        <div className="mb-6 rounded-lg border border-neutral-50 p-4">
          <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-neutral-50">
            <div
              className="h-2 rounded-full bg-violet-300 transition-all"
              style={{ width: `${(verifyAllProgress.completed / Math.max(verifyAllProgress.total, 1)) * 100}%` }}
            />
          </div>
          <p className="mb-2 text-b3 text-neutral-75">
            {verifyAllProgress.completed} / {verifyAllProgress.total} bidders verified
          </p>
          <div className="flex flex-col gap-1">
            {bidders.map((b) => (
              <p key={b.id} className="text-b3 text-neutral-200">
                <span className="font-medium text-neutral-300">{b.name}:</span>{" "}
                {verifyAllProgress.statusByBidder[b.id] ?? "Pending"}
              </p>
            ))}
          </div>
        </div>
      )}

      {biddersQuery.isLoading && (
        <p className="text-b2 text-neutral-75">Loading bidders...</p>
      )}

      {!biddersQuery.isLoading && bidders.length === 0 && (
        <p className="text-b2 text-neutral-75">
          No bidders yet — add bidders on the Requirements &amp; Setup page first.
        </p>
      )}

      {bidders.length > 0 && bidder && (
        <>
          {/* Bidder tabs */}
          <div className="mb-4 flex gap-1 rounded-full bg-white p-1 w-fit">
            {bidders.map((b, i) => (
              <button
                key={b.id}
                type="button"
                onClick={() => setActiveBidder(i)}
                className={`rounded-full px-4 py-2 text-b2 font-medium transition-colors ${
                  activeBidder === i
                    ? "bg-violet-50 text-violet-300"
                    : "text-neutral-200 hover:bg-neutral-50"
                }`}
              >
                {b.name} ({b.final_status})
              </button>
            ))}
          </div>

          <div className="rounded-lg border border-neutral-50 p-5">
            {/* Upload + ingest/verify for this bidder */}
            <div className="mb-5 flex items-end gap-4">
              <label className="flex flex-1 cursor-pointer items-center gap-3 rounded-lg border-2 border-dashed border-violet-200 bg-violet-50/30 px-5 py-4">
                <UploadIcon />
                <span className="text-b2 text-neutral-300">Upload all PDFs for {bidder.name}</span>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf"
                  className="hidden"
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? []);
                    if (files.length > 0) ingestMutation.mutate(files);
                    e.target.value = "";
                  }}
                />
              </label>
              <Button
                variant="primary"
                disabled={ingestMutation.isPending}
                onClick={() => fileInputRef.current?.click()}
              >
                {ingestMutation.isPending ? "Ingesting..." : "Fast Parallel Ingest"}
              </Button>
              <Button
                variant="primary"
                disabled={verifyMutation.isPending}
                onClick={() => verifyMutation.mutate()}
              >
                {verifyMutation.isPending ? "Verifying..." : "Run AI Verification"}
              </Button>
            </div>

            {/* Submitted Files */}
            {documents.length > 0 && (
              <div className="mb-5">
                <p className="mb-2 text-b3 font-medium text-neutral-300">
                  Submitted Files ({documents.length}):
                </p>
                <div className="grid grid-cols-3 gap-x-4 gap-y-1">
                  {documents.map((d) => (
                    <p key={d.id} className="text-b3 text-neutral-75">
                      {d.file_name} ({d.page_count} page{d.page_count === 1 ? "" : "s"})
                    </p>
                  ))}
                </div>
              </div>
            )}

            {/* KPI cards */}
            <div className="mb-5 grid grid-cols-6 gap-3">
              <div className="rounded-lg border border-neutral-50 p-4">
                <p className="text-b3 text-neutral-100">
                  Match Accuracy
                  <InfoHint text="Share of this bidder's clauses marked Complied out of all evaluated clauses." />
                </p>
                <p className="text-h1 font-semibold text-neutral-300">
                  {totalClauses > 0 ? `${accuracyPct}%` : "—"}
                </p>
              </div>
              <div className="rounded-lg border border-neutral-50 p-4">
                <p className="text-b3 text-neutral-100">
                  Complied
                  <InfoHint text="Clauses the AI (or engineer override) marked as Complied, out of total evaluated." />
                </p>
                <p className="text-h1 font-semibold text-neutral-300">
                  {totalClauses > 0 ? `${compliedCount} / ${totalClauses}` : "—"}
                </p>
              </div>
              <div className="rounded-lg border border-neutral-50 p-4">
                <p className="text-b3 text-neutral-100">
                  Not Complied
                  <InfoHint text="Clauses marked Not Complied — the bidder's offer deviates from the requirement." />
                </p>
                <p className="text-h1 font-semibold text-neutral-300">{totalClauses > 0 ? notCompliedCount : "—"}</p>
              </div>
              <div className="rounded-lg border border-neutral-50 p-4">
                <p className="text-b3 text-neutral-100">
                  Needs Review
                  <InfoHint text="Clauses the AI couldn't confidently verdict — flagged for manual engineer review." />
                </p>
                <p className="text-h1 font-semibold text-neutral-300">{totalClauses > 0 ? reviewCount : "—"}</p>
              </div>
              <div className="rounded-lg border border-neutral-50 p-4">
                <p className="text-b3 text-neutral-100">
                  Ingest Time
                  <InfoHint text="How long it took to upload and parse this bidder's documents in this session." />
                </p>
                <p className="text-h1 font-semibold text-neutral-300">{ingestTimeDisplay}</p>
              </div>
              <div className="rounded-lg border border-neutral-50 p-4">
                <p className="text-b3 text-neutral-100">
                  Verify Time
                  <InfoHint text="How long AI verification took for this bidder in this session (estimated until run)." />
                </p>
                <p className="text-h1 font-semibold text-neutral-300">{verifyTimeDisplay}</p>
              </div>
            </div>

            <div className="mb-5 flex items-center justify-between">
              <span className="text-b2 font-medium text-neutral-300">Qualification Status</span>
              <div className="flex items-center gap-3">
                <Badge tone={badgeToneFor(bidder.final_status)}>{bidder.final_status}</Badge>
                <Button
                  variant="primary"
                  disabled={qualifyMutation.isPending}
                  onClick={() => qualifyMutation.mutate("Qualified")}
                >
                  Mark Qualified
                </Button>
                <Button
                  variant="dark"
                  disabled={qualifyMutation.isPending}
                  onClick={() => qualifyMutation.mutate("Not Qualified")}
                >
                  Mark Not Qualified
                </Button>
              </div>
            </div>

            {/* Evaluation & Accuracy Matrix */}
            {findingsQuery.isLoading && (
              <p className="py-6 text-center text-b2 text-neutral-75">Loading evaluation matrix...</p>
            )}
            {!findingsQuery.isLoading && totalClauses === 0 && (
              <div className="py-6 text-center text-b2 text-neutral-75">
                Run AI Verification above, then open Verification Results to review each clause.
              </div>
            )}
            {totalClauses > 0 && (
              <>
                <p className="mb-3 text-b2 font-medium text-neutral-300">
                  Evaluation &amp; Accuracy Matrix for {bidder.name}:
                </p>
                <div className="max-h-[420px] overflow-auto rounded-lg border border-neutral-50">
                  <table className="w-full text-left text-b3">
                    <thead className="sticky top-0 bg-neutral-50 text-neutral-100">
                      <tr>
                        <th className="px-3 py-2 font-normal">Clause</th>
                        <th className="px-3 py-2 font-normal">
                          Category
                          <InfoHint text="QR = Qualification Requirement (mandatory to qualify). Technical = scored but not disqualifying on its own." />
                        </th>
                        <th className="px-3 py-2 font-normal">Specification Requirement</th>
                        <th className="px-3 py-2 font-normal">
                          Bidder Offered Quote
                          <InfoHint text="The exact verbatim text the AI cited from the bidder's document as evidence, with its source page." />
                        </th>
                        <th className="px-3 py-2 font-normal">Status</th>
                        <th className="px-3 py-2 font-normal">
                          Parameter Accuracy
                          <InfoHint text="100% if this clause is Complied, 0% if Not Complied, or Pending Review while unresolved." />
                        </th>
                        <th className="px-3 py-2 font-normal">Remarks</th>
                      </tr>
                    </thead>
                    <tbody>
                      {findings.map((f) => {
                        const status = effectiveStatus(f);
                        const offered = f.evidence?.quoted_text
                          ? `"${f.evidence.quoted_text.slice(0, 60)}${f.evidence.quoted_text.length > 60 ? "..." : ""}" [${f.evidence.document_name ?? "Doc"} p.${f.evidence.page_number ?? "?"}]`
                          : "(No quote found)";
                        return (
                          <tr key={f.id} className="border-t border-neutral-50 text-neutral-300">
                            <td className="px-3 py-2">{f.clause ?? "-"}</td>
                            <td className="px-3 py-2">{f.is_QR ? "QR" : "Technical"}</td>
                            <td className="max-w-[260px] px-3 py-2">
                              {f.requirement_text.slice(0, 65)}
                              {f.requirement_text.length > 65 ? "..." : ""}
                            </td>
                            <td className="max-w-[260px] px-3 py-2">{offered}</td>
                            <td className="px-3 py-2">
                              <Badge tone={statusTone(status)}>{status}</Badge>
                            </td>
                            <td className="px-3 py-2">{accuracyLabel(status)}</td>
                            <td className="max-w-[200px] px-3 py-2">{f.remark || "—"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-b3 text-neutral-75">{totalClauses} clause(s) evaluated.</p>
              </>
            )}
          </div>
        </>
      )}

      {/* Working TBE Master Matrix — only meaningful once verification has
          produced findings to fill it with, so it stays unresponsive until
          "Run AI Verification for ALL Bidders" (or at least one bidder) has
          completed. */}
      <div className="mt-6 flex items-center justify-between rounded-lg border border-neutral-50 p-5">
        <div>
          <h3 className="text-h3 text-neutral-300">Working TBE Master Matrix</h3>
          <p className="text-b3 text-neutral-75">
            Pre-filled spreadsheet with all requirements, ready for offline annotation.
          </p>
        </div>
        <Button
          variant="primary"
          disabled={!hasVerifiedAny || downloadExcelMutation.isPending}
          title={!hasVerifiedAny ? "Run AI Verification above first — the Excel needs findings to fill in." : undefined}
          onClick={() => downloadExcelMutation.mutate()}
        >
          {downloadExcelMutation.isPending ? "Generating..." : "Generate & Download Working Excel"}
          {!downloadExcelMutation.isPending && <DownloadIcon />}
        </Button>
      </div>
    </>
  );
}
