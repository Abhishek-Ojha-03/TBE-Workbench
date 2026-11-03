"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import WorkspaceHeader from "@/components/layout/workspace-header";
import Button from "@/components/ui/button";
import Badge from "@/components/ui/badge";
import {
  ApiError,
  downloadWorkingExcel,
  listBidders,
  bulkZipIngest,
  ingestBidderDocuments,
  verifyBidder,
  verifyAllBidders,
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

export default function WorkingExcelPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { tenderId, tenderName, clearActiveTender } = useActiveTenderStore();
  const [activeBidder, setActiveBidder] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    onSuccess: (res) => {
      const summary = res.results
        .map((r) => `${r.bidder_name}: ${r.matched ? `${r.documents_ingested} docs ingested` : "no matching bidder"}`)
        .join("\n");
      alert(`Bulk ZIP ingestion complete:\n\n${summary}`);
    },
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Bulk ZIP ingestion failed.");
    },
  });

  const bidders = biddersQuery.data ?? [];
  const bidder = bidders[activeBidder];

  const ingestMutation = useMutation({
    mutationFn: (files: File[]) => ingestBidderDocuments(tenderId as number, bidder.id, files),
    onSuccess: (res) => {
      alert(`Ingested ${res.ingested_count} document(s) for ${bidder.name}.`);
    },
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Document ingestion failed.");
    },
  });

  const verifyMutation = useMutation({
    mutationFn: () => verifyBidder(tenderId as number, bidder.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bidders", tenderId] });
      queryClient.invalidateQueries({ queryKey: ["findings", tenderId, bidder.id] });
    },
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "AI verification failed.");
    },
  });

  const verifyAllMutation = useMutation({
    mutationFn: () => verifyAllBidders(tenderId as number),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bidders", tenderId] });
      alert("AI verification complete for all bidders.");
    },
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "AI verification failed for one or more bidders.");
    },
  });

  const ingestAllMutation = useMutation({
    mutationFn: async () => {
      // Matches Streamlit's "Ingest ALL Staged Documents for ALL Bidders" —
      // reuses the same saved-ZIP ingestion path since staged docs for all
      // bidders come from that one ZIP.
      return bulkZipIngest(tenderId as number);
    },
    onSuccess: (res) => {
      const summary = res.results
        .map((r) => `${r.bidder_name}: ${r.matched ? `${r.documents_ingested} docs` : "no match"}`)
        .join("\n");
      alert(`Ingested staged documents for all bidders:\n\n${summary}`);
    },
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Ingestion failed.");
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

      {/* Master Matrix */}
      <div className="mb-6 flex items-center justify-between rounded-lg border border-neutral-50 p-5">
        <div>
          <h3 className="text-h3 text-neutral-300">Working TBE Master Matrix</h3>
          <p className="text-b3 text-neutral-75">
            Pre-filled spreadsheet with all requirements, ready for offline annotation.
          </p>
        </div>
        <Button
          variant="primary"
          disabled={downloadExcelMutation.isPending}
          onClick={() => downloadExcelMutation.mutate()}
        >
          {downloadExcelMutation.isPending ? "Generating..." : "Generate & Download Working Excel"}
          {!downloadExcelMutation.isPending && <DownloadIcon />}
        </Button>
      </div>

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
          {bulkZipIngestMutation.isPending ? "Ingesting..." : "Extract & Ingest ALL Bidders from Saved ZIP"}
        </Button>
      </div>

      {/* Bidder Document Ingestion & AI Verification */}
      <h3 className="mb-4 text-h3 text-neutral-300">Bidder Document Ingestion &amp; AI Verification</h3>
      <div className="mb-6 flex gap-3">
        <Button
          variant="primary"
          className="flex-1 justify-center"
          disabled={ingestAllMutation.isPending}
          onClick={() => ingestAllMutation.mutate()}
        >
          {ingestAllMutation.isPending ? "Ingesting..." : "Ingest ALL Staged Documents for ALL Bidders"}
        </Button>
        <Button
          variant="primary"
          className="flex-1 justify-center"
          disabled={verifyAllMutation.isPending}
          onClick={() => verifyAllMutation.mutate()}
        >
          {verifyAllMutation.isPending ? "Verifying..." : "Run AI Verification for ALL Bidders"}
        </Button>
      </div>

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

            {/* KPI cards */}
            <div className="mb-5 grid grid-cols-4 gap-4">
              <div className="rounded-lg border border-neutral-50 p-4">
                <p className="text-b3 text-neutral-100">Parameter Match Accuracy</p>
                <p className="text-h1 font-semibold text-neutral-300">
                  {verifyMutation.data?.accuracy_pct ?? "—"}
                  {verifyMutation.data ? "%" : ""}
                </p>
              </div>
              <div className="rounded-lg border border-neutral-50 p-4">
                <p className="text-b3 text-neutral-100">Complied</p>
                <p className="text-h1 font-semibold text-neutral-300">{verifyMutation.data?.complied ?? "—"}</p>
              </div>
              <div className="rounded-lg border border-neutral-50 p-4">
                <p className="text-b3 text-neutral-100">Not Complied</p>
                <p className="text-h1 font-semibold text-neutral-300">{verifyMutation.data?.not_complied ?? "—"}</p>
              </div>
              <div className="rounded-lg border border-neutral-50 p-4">
                <p className="text-b3 text-neutral-100">Needs Review</p>
                <p className="text-h1 font-semibold text-neutral-300">{verifyMutation.data?.needs_review ?? "—"}</p>
              </div>
            </div>

            <div className="mb-4 flex items-center justify-between">
              <span className="text-b2 font-medium text-neutral-300">Qualification Status</span>
              <Badge tone={badgeToneFor(bidder.final_status)}>{bidder.final_status}</Badge>
            </div>

            <div className="text-center py-6 text-b2 text-neutral-75">
              Run AI Verification above, then open Verification Results to review each clause.
            </div>
          </div>
        </>
      )}
    </>
  );
}
