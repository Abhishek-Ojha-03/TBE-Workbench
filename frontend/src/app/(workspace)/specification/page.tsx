"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import WorkspaceHeader from "@/components/layout/workspace-header";
import {
  ApiError,
  Requirement,
  createBaselineVersion,
  getRequirements,
  getSpecificationProgress,
  uploadSpecification,
} from "@/lib/api";
import { useActiveTenderStore } from "@/lib/store";
import Button from "@/components/ui/button";

function UploadIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 16V4M12 4l-4 4M12 4l4 4" />
      <path d="M4 16v3a2 2 0 002 2h12a2 2 0 002-2v-3" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 6L6 18M6 6l12 12" />
    </svg>
  );
}

export default function SpecificationPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { tenderId, tenderName, clearActiveTender } = useActiveTenderStore();

  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  // Flips true once an upload has been started; never reset to false by us —
  // whether polling is still ACTIVE is derived below from the progress
  // query's own status, not stored as separate state (avoids the
  // state-in-effect anti-pattern: there's nothing to "turn off" manually,
  // the query's `enabled`/`refetchInterval` already stop themselves).
  const [uploadStarted, setUploadStarted] = useState(false);

  // Pending edits to QR / Mark N/A on existing rows, keyed by requirement id —
  // mirrors Requirements & Setup's save flow: nothing is sent until "Save
  // Changes" creates a new baseline version from the full edited list.
  const [pendingEdits, setPendingEdits] = useState<Record<number, { is_QR?: boolean; not_applicable?: boolean }>>({});
  const [saveChangesError, setSaveChangesError] = useState<string | null>(null);

  const requirementsQuery = useQuery({
    queryKey: ["requirements", tenderId],
    queryFn: () => getRequirements(tenderId as number),
    enabled: tenderId !== null,
  });

  // Polls every 2s while extraction is running (status "ingesting"/"extracting"),
  // stops automatically once the backend reports "complete" or "error" —
  // this is what turns the backend's internal page-by-page tracking
  // (visible in the uvicorn terminal logs) into something the UI can show.
  const progressQuery = useQuery({
    queryKey: ["specification-progress", tenderId],
    queryFn: () => getSpecificationProgress(tenderId as number),
    enabled: tenderId !== null && uploadStarted,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "ingesting" || status === "extracting" ? 2000 : false;
    },
  });

  const progressStatus = progressQuery.data?.status;
  const isPolling = uploadStarted && progressStatus !== "complete" && progressStatus !== "error";

  // Side effect only (cache invalidation) — no setState here, so this
  // doesn't trip the "avoid setState in effect" rule. A ref guards against
  // invalidating repeatedly if the component re-renders while status stays
  // "complete" (e.g. from an unrelated state change elsewhere on the page).
  const hasHandledCompletionRef = useRef<string | null>(null);
  useEffect(() => {
    if (progressStatus === "complete" && hasHandledCompletionRef.current !== "complete") {
      hasHandledCompletionRef.current = "complete";
      queryClient.invalidateQueries({ queryKey: ["requirements", tenderId] });
    }
    if (progressStatus === "error") {
      hasHandledCompletionRef.current = "error";
    }
    if (progressStatus === "ingesting" || progressStatus === "extracting") {
      hasHandledCompletionRef.current = null;
    }
  }, [progressStatus, queryClient, tenderId]);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadSpecification(tenderId as number, file),
    onSuccess: (result) => {
      setUploadedFileName(result.file_name);
      setUploadError(null);
      setUploadStarted(true);
    },
    onError: (err) => {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed.");
    },
  });

  const saveChangesMutation = useMutation({
    mutationFn: async () => {
      const current = requirementsQuery.data ?? [];
      const asInput = current.map((r: Requirement) => ({
        clause: r.clause,
        text: r.text,
        page_number: r.page_number,
        is_QR: pendingEdits[r.id]?.is_QR ?? r.is_QR,
        not_applicable: pendingEdits[r.id]?.not_applicable ?? r.not_applicable,
      }));
      return createBaselineVersion(tenderId as number, asInput);
    },
    onSuccess: () => {
      setPendingEdits({});
      queryClient.invalidateQueries({ queryKey: ["requirements", tenderId] });
    },
    onError: (err) => {
      setSaveChangesError(err instanceof ApiError ? err.message : "Failed to save changes.");
    },
  });

  function toggleField(reqId: number, field: "is_QR" | "not_applicable", original: boolean, next: boolean) {
    setPendingEdits((prev) => {
      const existing = { ...(prev[reqId] ?? {}) };
      if (next === original) {
        delete existing[field];
      } else {
        existing[field] = next;
      }
      const updated = { ...prev };
      if (Object.keys(existing).length === 0) {
        delete updated[reqId];
      } else {
        updated[reqId] = existing;
      }
      return updated;
    });
  }

  const isDirty = Object.keys(pendingEdits).length > 0;

  // No tender selected (e.g. page opened directly, not via Home) — can't do
  // anything useful here without one, since every endpoint needs a tender id.
  if (tenderId === null) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
        <p className="text-h3 text-neutral-300">No tender selected</p>
        <p className="max-w-md text-b2 text-neutral-75">
          Open a tender from the Home screen first — this page needs to know which
          tender&apos;s specification it&apos;s working with.
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

  const requirements = requirementsQuery.data ?? [];

  return (
    <>
      <WorkspaceHeader
        title="Specifications"
        tenderOptions={[tenderName ?? "Tender"]}
        onBack={() => {
          clearActiveTender();
          router.push("/");
        }}
      />

      <div className="grid grid-cols-[420px_1fr] gap-8">
        {/* Left column: upload + ingestion status */}
        <div>
          <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-violet-200 bg-violet-50/30 px-6 py-8 text-center">
            <UploadIcon />
            <span className="text-h3 font-medium text-neutral-300">
              {uploadMutation.isPending
                ? "Uploading..."
                : isPolling
                ? "Processing..."
                : "Upload Specification PDF"}
            </span>
            <span className="text-b3 text-neutral-75">Upload limit 200 mb &nbsp;|&nbsp; File type .pdf</span>
            <input
              type="file"
              accept=".pdf"
              disabled={uploadMutation.isPending || isPolling}
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  setUploadedFileName(file.name);
                  uploadMutation.mutate(file);
                }
              }}
            />
          </label>

          {isPolling && progressQuery.data && (
            <div className="mt-3 rounded-md bg-violet-50 px-4 py-3 text-b3 text-violet-300">
              {progressQuery.data.status === "ingesting" && "Reading document pages..."}
              {progressQuery.data.status === "extracting" &&
                (progressQuery.data.total_pages > 0
                  ? `Processing page ${progressQuery.data.current_page} of ${progressQuery.data.total_pages} — ${progressQuery.data.requirements_so_far} requirements found so far`
                  : "Starting extraction...")}
              {progressQuery.data.total_pages > 10 && (
                <span className="mt-1 block text-neutral-75">
                  Large documents ({'>'}10 pages) process one page at a time to stay within API rate
                  limits — this can take a few minutes.
                </span>
              )}
            </div>
          )}

          {(uploadError || (progressStatus === "error" && progressQuery.data?.error)) && (
            <p className="mt-2 text-b3 text-red-500">
              {uploadError || progressQuery.data?.error}
            </p>
          )}

          <div className="my-5 border-t border-neutral-50" />

          <h3 className="mb-3 text-h3 text-neutral-300">Ingestion Status :</h3>
          {uploadedFileName ? (
            <div className="mb-5 flex items-center justify-between rounded-md border border-neutral-50 px-4 py-3 text-b2 text-neutral-300">
              <span>{uploadedFileName}</span>
              <button
                type="button"
                onClick={() => setUploadedFileName(null)}
                aria-label="Remove file"
                className="text-neutral-200 hover:text-neutral-400"
              >
                <CloseIcon />
              </button>
            </div>
          ) : (
            <p className="mb-5 text-b3 text-neutral-75">No file uploaded yet.</p>
          )}

          <div className="flex gap-4">
            <div className="flex-1 rounded-lg border border-neutral-50 p-4">
              <p className="text-b3 text-neutral-100">Total Pages Ingested</p>
              <p className="text-h1 font-semibold text-neutral-300">
                {uploadMutation.data?.total_pages_ingested ?? "—"}
              </p>
            </div>
            <div className="flex-1 rounded-lg border border-neutral-50 p-4">
              <p className="text-b3 text-neutral-100">Requirements Extracted</p>
              <p className="text-h1 font-semibold text-neutral-300">{requirements.length || "—"}</p>
            </div>
          </div>
        </div>

        {/* Right column: clause table */}
        <div>
          <h3 className="mb-4 text-h3 text-neutral-300">View &amp; Edit Extracted Clauses Right Here</h3>
          <div className="max-h-[480px] overflow-auto rounded-lg border border-neutral-50">
            <table className="w-full text-left">
              <thead className="sticky top-0 z-10">
                <tr className="bg-neutral-50 text-label text-neutral-100">
                  <th className="w-28 px-5 py-3 font-normal">QR (Eligibility Gate)</th>
                  <th className="w-20 px-5 py-3 font-normal">Clause</th>
                  <th className="px-5 py-3 font-normal">Requirements Description</th>
                  <th className="w-24 px-5 py-3 text-right font-normal">Mark N/A</th>
                </tr>
              </thead>
              <tbody>
                {requirementsQuery.isLoading && (
                  <tr>
                    <td colSpan={4} className="px-5 py-8 text-center text-b2 text-neutral-75">
                      Loading requirements...
                    </td>
                  </tr>
                )}
                {!requirementsQuery.isLoading && requirements.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-5 py-8 text-center text-b2 text-neutral-75">
                      No requirements yet — upload a specification PDF to extract some.
                    </td>
                  </tr>
                )}
                {requirements.map((row) => {
                  const effQR = pendingEdits[row.id]?.is_QR ?? row.is_QR;
                  const effNA = pendingEdits[row.id]?.not_applicable ?? row.not_applicable;
                  return (
                    <tr key={row.id} className="border-t border-neutral-50 text-b2 text-neutral-300">
                      <td className="px-5 py-4">
                        <input
                          type="checkbox"
                          checked={effQR}
                          onChange={(e) => toggleField(row.id, "is_QR", row.is_QR, e.target.checked)}
                          className="h-4 w-4 rounded border-neutral-75 accent-violet-300"
                        />
                      </td>
                      <td className="px-5 py-4">{row.clause ?? "—"}</td>
                      <td className="px-5 py-4 text-neutral-200">{row.text}</td>
                      <td className="px-5 py-4 text-right">
                        <input
                          type="checkbox"
                          checked={effNA}
                          onChange={(e) => toggleField(row.id, "not_applicable", row.not_applicable, e.target.checked)}
                          className="h-4 w-4 rounded border-neutral-75 accent-violet-300"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {isDirty && (
            <div className="mt-3 flex items-center justify-between rounded-md bg-violet-50 px-4 py-3">
              <span className="text-b3 text-violet-300">
                {Object.keys(pendingEdits).length} row(s) edited — not saved yet. Saving creates a new
                baseline version; previous versions stay available in Requirements &amp; Setup&apos;s
                version history.
              </span>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={() => setPendingEdits({})}>
                  Discard
                </Button>
                <Button
                  variant="primary"
                  disabled={saveChangesMutation.isPending}
                  onClick={() => {
                    setSaveChangesError(null);
                    saveChangesMutation.mutate();
                  }}
                >
                  {saveChangesMutation.isPending ? "Saving..." : "Save Changes"}
                </Button>
              </div>
            </div>
          )}
          {saveChangesError && <p className="mt-2 text-b3 text-red-500">{saveChangesError}</p>}
        </div>
      </div>
    </>
  );
}
