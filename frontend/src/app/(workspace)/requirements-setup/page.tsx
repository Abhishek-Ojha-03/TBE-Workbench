"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import WorkspaceHeader from "@/components/layout/workspace-header";
import Button from "@/components/ui/button";
import Badge from "@/components/ui/badge";
import {
  addBiddersFromZip,
  ApiError,
  Bidder,
  createBaselineVersion,
  createBidder,
  deleteBidder,
  getRequirementsForVersion,
  listBaselineVersions,
  listBidders,
  Requirement,
} from "@/lib/api";
import { useActiveTenderStore } from "@/lib/store";

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 6h18" />
      <path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0l-1 14a2 2 0 01-2 2H7a2 2 0 01-2-2L4 6" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M7 10l5 5 5-5" />
    </svg>
  );
}

function badgeToneFor(status: Bidder["final_status"]): "violet" | "neutral" {
  return status === "Qualified" ? "violet" : "neutral";
}

function formatApprovedAt(iso: string): string {
  // Backend serializes naive UTC timestamps (no "Z"/offset) — without this,
  // `new Date(iso)` is parsed as local time instead of UTC, showing the
  // wrong clock time by the browser's UTC offset.
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).replace(/ /g, "-") +
    " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function ManualAddBidderTab({ tenderId, onClose }: { tenderId: number; onClose: () => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => createBidder(tenderId, name.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bidders", tenderId] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Failed to add bidder.");
    },
  });

  return (
    <div>
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="e.g. Siemens Ltd"
        className="mb-3 w-full rounded-md border border-neutral-50 px-4 py-2.5 text-b2 text-neutral-300 placeholder:text-neutral-75 focus:border-violet-200 focus:outline-none"
        onKeyDown={(e) => {
          if (e.key === "Enter" && name.trim()) mutation.mutate();
        }}
      />
      {error && <p className="mb-3 text-b3 text-red-500">{error}</p>}
      <Button
        variant="primary"
        disabled={!name.trim() || mutation.isPending}
        onClick={() => mutation.mutate()}
        className="w-full"
      >
        {mutation.isPending ? "Adding..." : "Add Bidder"}
        {!mutation.isPending && <PlusIcon />}
      </Button>
    </div>
  );
}

function ZipAddBidderTab({ tenderId, onClose }: { tenderId: number; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (f: File) => addBiddersFromZip(tenderId, f),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bidders", tenderId] });
      // Not closing automatically — the added/skipped summary below is
      // worth letting the user actually read before dismissing.
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Failed to process ZIP.");
    },
  });

  return (
    <div>
      <p className="mb-4 text-b3 text-neutral-75">
        Upload a ZIP with one sub-folder per bidder (e.g. <code>siemens/</code>, <code>abb/</code>).
        Each top-level folder becomes a bidder here, and the same ZIP is reused in the TBE
        Working Excel screen to ingest documents — no re-upload, no name-matching needed.
      </p>

      <label className="mb-3 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-violet-200 bg-violet-50/30 px-6 py-6 text-center">
        <span className="text-b2 font-medium text-neutral-300">
          {file ? file.name : "Click to select a ZIP file"}
        </span>
        <input
          type="file"
          accept=".zip"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) {
              setFile(f);
              setError(null);
            }
          }}
        />
      </label>

      {error && <p className="mb-3 text-b3 text-red-500">{error}</p>}

      {mutation.data && (
        <div className="mb-3 rounded-md bg-violet-50 px-4 py-3 text-b3 text-violet-300">
          ✅ Added {mutation.data.added.length} bidder(s)
          {mutation.data.added.length > 0 ? `: ${mutation.data.added.join(", ")}` : ""}.
          {mutation.data.skipped.length > 0 && (
            <> Skipped {mutation.data.skipped.length} already registered: {mutation.data.skipped.join(", ")}.</>
          )}
        </div>
      )}

      <div className="flex gap-2">
        <Button
          variant="primary"
          disabled={!file || mutation.isPending}
          onClick={() => file && mutation.mutate(file)}
        >
          {mutation.isPending ? "Processing..." : "Extract Bidder Names & Save for Ingestion"}
          {!mutation.isPending && <PlusIcon />}
        </Button>
        {mutation.data && (
          <Button variant="ghost" onClick={onClose}>
            Done
          </Button>
        )}
      </div>
    </div>
  );
}

function AddBidderModal({ tenderId, onClose }: { tenderId: number; onClose: () => void }) {
  const [tab, setTab] = useState<"manual" | "zip">("manual");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-300/40"
      onClick={onClose}
    >
      <div className="w-full max-w-lg rounded-lg bg-white p-6" onClick={(e) => e.stopPropagation()}>
        <h3 className="mb-4 text-h3 font-semibold text-neutral-300">Add Bidder</h3>

        <div className="mb-4 flex gap-1 rounded-full bg-neutral-50 p-1">
          <button
            type="button"
            onClick={() => setTab("manual")}
            className={`flex-1 rounded-full px-4 py-2 text-b3 font-medium transition-colors ${
              tab === "manual" ? "bg-white text-violet-300 shadow-sm" : "text-neutral-200"
            }`}
          >
            Manual Entry
          </button>
          <button
            type="button"
            onClick={() => setTab("zip")}
            className={`flex-1 rounded-full px-4 py-2 text-b3 font-medium transition-colors ${
              tab === "zip" ? "bg-white text-violet-300 shadow-sm" : "text-neutral-200"
            }`}
          >
            📦 Add from ZIP
          </button>
        </div>

        {tab === "manual" ? (
          <ManualAddBidderTab tenderId={tenderId} onClose={onClose} />
        ) : (
          <ZipAddBidderTab tenderId={tenderId} onClose={onClose} />
        )}
      </div>
    </div>
  );
}

export default function RequirementsSetupPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { tenderId, tenderName, clearActiveTender } = useActiveTenderStore();

  const [bidderFilter, setBidderFilter] = useState<"all" | "qualified" | "unqualified">("all");
  const [showAddBidder, setShowAddBidder] = useState(false);
  const [showVersionDropdown, setShowVersionDropdown] = useState(false);
  // User's explicit pick, if any — null means "follow the latest version"
  // rather than needing an effect to sync a default once versions load.
  const [explicitVersion, setExplicitVersion] = useState<number | null>(null);
  const [quickAddError, setQuickAddError] = useState<string | null>(null);
  const [saveChangesError, setSaveChangesError] = useState<string | null>(null);

  // Quick Add form state
  const [showQuickAdd, setShowQuickAdd] = useState(false);
  const [qaClause, setQaClause] = useState("");
  const [qaPage, setQaPage] = useState(1);
  const [qaIsQR, setQaIsQR] = useState(false);
  const [qaText, setQaText] = useState("");

  // Pending edits to QR / Mark N/A on existing rows, keyed by requirement id —
  // only the fields the user actually touched, so isDirty is exact. Nothing
  // is sent to the backend until "Save Changes" creates a new baseline
  // version from the full edited list (save_baseline_edits never patches a
  // single row in place).
  const [pendingEdits, setPendingEdits] = useState<Record<number, { is_QR?: boolean; not_applicable?: boolean }>>({});

  const versionsQuery = useQuery({
    queryKey: ["baseline-versions", tenderId],
    queryFn: () => listBaselineVersions(tenderId as number),
    enabled: tenderId !== null,
  });

  const versions = versionsQuery.data ?? [];
  const latestVersion = versions.find((v) => v.is_latest) ?? versions[0];

  // Derived, not synced via effect: follow the latest version unless the
  // user explicitly picked a different one from the dropdown.
  const selectedVersion = explicitVersion ?? latestVersion?.version_number ?? null;

  const requirementsQuery = useQuery({
    queryKey: ["requirements-for-version", tenderId, selectedVersion],
    queryFn: () => getRequirementsForVersion(tenderId as number, selectedVersion as number),
    enabled: tenderId !== null && selectedVersion !== null,
  });

  const biddersQuery = useQuery({
    queryKey: ["bidders", tenderId],
    queryFn: () => listBidders(tenderId as number),
    enabled: tenderId !== null,
  });

  const deleteMutation = useMutation({
    mutationFn: (bidderId: number) => deleteBidder(tenderId as number, bidderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bidders", tenderId] });
    },
  });

  const quickAddMutation = useMutation({
    mutationFn: async () => {
      const current = requirementsQuery.data ?? [];
      const asInput = current.map((r: Requirement) => ({
        clause: r.clause,
        text: r.text,
        page_number: r.page_number,
        is_QR: r.is_QR,
        not_applicable: r.not_applicable,
      }));
      asInput.push({
        clause: qaClause.trim() || null,
        text: qaText.trim(),
        page_number: qaPage,
        is_QR: qaIsQR,
        not_applicable: false,
      });
      return createBaselineVersion(tenderId as number, asInput);
    },
    onSuccess: (newVersion) => {
      setQaClause("");
      setQaPage(1);
      setQaIsQR(false);
      setQaText("");
      setShowQuickAdd(false);
      setExplicitVersion(newVersion.version_number);
      queryClient.invalidateQueries({ queryKey: ["baseline-versions", tenderId] });
      queryClient.invalidateQueries({ queryKey: ["requirements-for-version", tenderId] });
    },
    onError: (err) => {
      setQuickAddError(err instanceof ApiError ? err.message : "Failed to add requirement.");
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
    onSuccess: (newVersion) => {
      setPendingEdits({});
      setExplicitVersion(newVersion.version_number);
      queryClient.invalidateQueries({ queryKey: ["baseline-versions", tenderId] });
      queryClient.invalidateQueries({ queryKey: ["requirements-for-version", tenderId] });
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

  if (tenderId === null) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
        <p className="text-h3 text-neutral-300">No tender selected</p>
        <p className="max-w-md text-b2 text-neutral-75">
          Open a tender from the Home screen first — this page needs to know which
          tender&apos;s requirements and bidders it&apos;s working with.
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
  const bidders = biddersQuery.data ?? [];
  const visibleBidders = bidders.filter((b) => {
    if (bidderFilter === "qualified") return b.final_status === "Qualified";
    if (bidderFilter === "unqualified") return b.final_status === "Not Qualified";
    return true;
  });

  const selectedVersionObj = versions.find((v) => v.version_number === selectedVersion);
  const isViewingLatest = selectedVersionObj?.is_latest ?? true;

  return (
    <>
      <WorkspaceHeader
        title="Requirements & Setup"
        tenderOptions={[tenderName ?? "Tender"]}
        onBack={() => {
          clearActiveTender();
          router.push("/");
        }}
        rightSlot={
          <Button variant="primary" onClick={() => setShowAddBidder(true)}>
            Add Bidder
            <PlusIcon />
          </Button>
        }
      />

      <div className="grid grid-cols-[1fr_380px] gap-8">
        {/* Left: Requirements table */}
        <div>
          <h3 className="mb-4 text-h3 text-neutral-300">Technical &amp; Qualification Requirements</h3>

          {/* Version selector */}
          {versions.length > 0 && selectedVersionObj && (
            <div className="relative mb-3">
              <button
                type="button"
                onClick={() => setShowVersionDropdown((v) => !v)}
                className="flex w-full items-center justify-between rounded-md border border-neutral-50 px-4 py-2.5 text-b2 text-neutral-300"
              >
                Version {selectedVersionObj.version_number} (
                {selectedVersionObj.is_latest ? "Active / Latest" : "Archived History"}) — Approved:{" "}
                {formatApprovedAt(selectedVersionObj.approved_at)}
                <ChevronIcon />
              </button>
              {showVersionDropdown && (
                <div className="absolute z-10 mt-1 w-full rounded-md border border-neutral-50 bg-white shadow-lg">
                  {versions.map((v) => (
                    <button
                      key={v.version_number}
                      type="button"
                      onClick={() => {
                        setExplicitVersion(v.version_number);
                        setShowVersionDropdown(false);
                        setPendingEdits({});
                      }}
                      className="block w-full px-4 py-2.5 text-left text-b3 text-neutral-300 hover:bg-neutral-50"
                    >
                      Version {v.version_number} ({v.is_latest ? "Active / Latest" : "Archived History"}) —{" "}
                      {formatApprovedAt(v.approved_at)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {selectedVersionObj && (
            <div
              className={`mb-4 rounded-md px-4 py-2.5 text-b2 font-medium ${
                isViewingLatest ? "bg-violet-50 text-violet-300" : "bg-neutral-50 text-neutral-200"
              }`}
            >
              {isViewingLatest
                ? `🟢 Active Baseline for Bidder Evaluation: v${selectedVersionObj.version_number}`
                : `🕒 Viewing Historical Version: v${selectedVersionObj.version_number} (Read/Branch)`}
            </div>
          )}

          <div className="mb-3 overflow-hidden rounded-lg border border-neutral-50">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-neutral-50/60 text-label text-neutral-100">
                  <th className="w-16 px-5 py-3 font-normal">QR</th>
                  <th className="w-20 px-5 py-3 font-normal">Clause</th>
                  <th className="w-24 px-5 py-3 font-normal">Page no.</th>
                  <th className="px-5 py-3 font-normal">Requirements Description</th>
                  <th className="w-24 px-5 py-3 text-right font-normal">Mark N/A</th>
                </tr>
              </thead>
              <tbody>
                {requirementsQuery.isLoading && (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-b2 text-neutral-75">
                      Loading requirements...
                    </td>
                  </tr>
                )}
                {!requirementsQuery.isLoading && requirements.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-5 py-8 text-center text-b2 text-neutral-75">
                      No requirements yet — upload a specification on the Specification screen first.
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
                          disabled={!isViewingLatest}
                          onChange={(e) => toggleField(row.id, "is_QR", row.is_QR, e.target.checked)}
                          className="h-4 w-4 rounded border-neutral-75 accent-violet-300 disabled:cursor-not-allowed"
                        />
                      </td>
                      <td className="px-5 py-4">{row.clause ?? "—"}</td>
                      <td className="px-5 py-4">{row.page_number ?? "—"}</td>
                      <td className="px-5 py-4 text-neutral-200">{row.text}</td>
                      <td className="px-5 py-4 text-right">
                        <input
                          type="checkbox"
                          checked={effNA}
                          disabled={!isViewingLatest}
                          onChange={(e) => toggleField(row.id, "not_applicable", row.not_applicable, e.target.checked)}
                          className="h-4 w-4 rounded border-neutral-75 accent-violet-300 disabled:cursor-not-allowed"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {isViewingLatest && isDirty && (
            <div className="mb-4 flex items-center justify-between rounded-md bg-violet-50 px-4 py-3">
              <span className="text-b3 text-violet-300">
                {Object.keys(pendingEdits).length} row(s) edited — not saved yet. Saving creates a new
                baseline version; previous versions stay available in history.
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
          {saveChangesError && <p className="mb-4 text-b3 text-red-500">{saveChangesError}</p>}

          {/* Quick Add Single Requirement */}
          {!showQuickAdd ? (
            <button
              type="button"
              onClick={() => setShowQuickAdd(true)}
              className="flex items-center gap-2 rounded-md px-3 py-2 text-b2 font-medium text-violet-300 hover:bg-violet-50"
            >
              Quick Add Single Requirement / Specification Clause
              <PlusIcon />
            </button>
          ) : (
            <div className="rounded-lg border border-neutral-50 p-4">
              <div className="mb-3 grid grid-cols-[1fr_1fr_3fr] gap-3">
                <div>
                  <label className="mb-1 block text-caption text-neutral-100">Clause No.</label>
                  <input
                    value={qaClause}
                    onChange={(e) => setQaClause(e.target.value)}
                    placeholder="e.g. 6.1 or QR-4"
                    className="w-full rounded-md border border-neutral-50 px-3 py-2 text-b3 text-neutral-300 focus:border-violet-200 focus:outline-none"
                  />
                  <label className="mt-2 flex items-center gap-2 text-b3 text-neutral-200">
                    <input
                      type="checkbox"
                      checked={qaIsQR}
                      onChange={(e) => setQaIsQR(e.target.checked)}
                      className="h-4 w-4 rounded border-neutral-75 accent-violet-300"
                    />
                    Qualification Req (QR)
                  </label>
                </div>
                <div>
                  <label className="mb-1 block text-caption text-neutral-100">Spec Page No.</label>
                  <input
                    type="number"
                    min={1}
                    value={qaPage}
                    onChange={(e) => setQaPage(Number(e.target.value) || 1)}
                    className="w-full rounded-md border border-neutral-50 px-3 py-2 text-b3 text-neutral-300 focus:border-violet-200 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-caption text-neutral-100">
                    Requirement Text / Specification Description
                  </label>
                  <textarea
                    value={qaText}
                    onChange={(e) => setQaText(e.target.value)}
                    placeholder="Enter full requirement clause..."
                    rows={3}
                    className="w-full resize-none rounded-md border border-neutral-50 px-3 py-2 text-b3 text-neutral-300 focus:border-violet-200 focus:outline-none"
                  />
                </div>
              </div>
              {quickAddError && <p className="mb-2 text-b3 text-red-500">{quickAddError}</p>}
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  disabled={!qaText.trim() || quickAddMutation.isPending}
                  onClick={() => {
                    setQuickAddError(null);
                    quickAddMutation.mutate();
                  }}
                >
                  {quickAddMutation.isPending ? "Appending..." : "Append to Baseline"}
                  {!quickAddMutation.isPending && <PlusIcon />}
                </Button>
                <Button variant="ghost" onClick={() => setShowQuickAdd(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Right: Mandatory Docs + Bidders */}
        <div className="flex flex-col gap-6">
          <div className="rounded-lg border border-neutral-50 p-5">
            <h3 className="mb-3 text-h3 text-neutral-300">Mandatory Tender Documents Review</h3>
            <p className="mb-2 text-b2 font-medium text-neutral-300">
              Every bidder must submit these documents to qualify:
            </p>
            <ul className="list-disc space-y-2 pl-5 text-b3 text-neutral-200">
              <li>
                <span className="font-medium text-neutral-300">Technical Offer:</span> The tender specification signed
                &amp; stamped on each page by bidder.
              </li>
              <li>
                <span className="font-medium text-neutral-300">Deviation Sheet:</span> Compliant ONLY if marked NIL
                deviations. Any deviation marked must be evaluated.
              </li>
              <li>
                <span className="font-medium text-neutral-300">Type Test Certificates:</span> Valid accredited lab test
                reports (CPRI / ERDA / equivalent).
              </li>
              <li>
                <span className="font-medium text-neutral-300">Performance Certificates:</span> Utility operational
                track record proof.
              </li>
            </ul>
          </div>

          <div className="overflow-hidden rounded-lg border border-neutral-50">
            <div className="flex items-center justify-between bg-violet-400 px-5 py-3 text-white">
              <span className="text-b1 font-medium">
                Bidders <span className="ml-1">{bidders.length}</span>
              </span>
              <div className="flex gap-1 rounded-full bg-white/10 p-0.5">
                {(["all", "qualified", "unqualified"] as const).map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => setBidderFilter(f)}
                    className={`rounded-full px-3 py-1 text-caption capitalize transition-colors ${
                      bidderFilter === f ? "bg-white text-violet-400" : "text-white/80"
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>

            <div className="divide-y divide-neutral-50">
              {biddersQuery.isLoading && (
                <div className="px-5 py-6 text-center text-b3 text-neutral-75">Loading bidders...</div>
              )}
              {!biddersQuery.isLoading && visibleBidders.length === 0 && (
                <div className="px-5 py-6 text-center text-b3 text-neutral-75">
                  {bidders.length === 0 ? "No bidders added yet." : "No bidders match this filter."}
                </div>
              )}
              {visibleBidders.map((b) => (
                <div key={b.id} className="flex items-center justify-between px-5 py-3">
                  <span className="text-b2 text-neutral-300">{b.name}</span>
                  <div className="flex items-center gap-3">
                    <Badge tone={badgeToneFor(b.final_status)}>{b.final_status}</Badge>
                    <button
                      type="button"
                      aria-label={`Remove ${b.name}`}
                      onClick={() => deleteMutation.mutate(b.id)}
                      disabled={deleteMutation.isPending}
                      className="text-neutral-200 hover:text-red-500 disabled:opacity-50"
                    >
                      <TrashIcon />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {showAddBidder && tenderId !== null && (
        <AddBidderModal tenderId={tenderId} onClose={() => setShowAddBidder(false)} />
      )}
    </>
  );
}
