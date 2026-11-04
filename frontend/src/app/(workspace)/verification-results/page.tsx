"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import WorkspaceHeader from "@/components/layout/workspace-header";
import Button from "@/components/ui/button";
import Badge from "@/components/ui/badge";
import {
  ApiError,
  Finding,
  confirmFinding,
  flagFinding,
  getFindings,
  getPageImageUrl,
  listBidders,
  overrideFinding,
  qualifyBidder,
} from "@/lib/api";
import { useActiveTenderStore } from "@/lib/store";

function badgeToneForStatus(status: string | null): "violet" | "neutral" {
  if (!status) return "neutral";
  return status.toLowerCase() === "complied" ? "violet" : "neutral";
}

function FindingCard({
  finding,
  onConfirm,
  onOverride,
  onFlag,
  isMutating,
}: {
  finding: Finding;
  onConfirm: () => void;
  onOverride: (status: string, reason: string) => void;
  onFlag: (reason: string) => void;
  isMutating: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [overrideChoice, setOverrideChoice] = useState<"Complied" | "Not Complied" | "N/A">("Complied");
  const [overrideReason, setOverrideReason] = useState("");
  const [clarificationNote, setClarificationNote] = useState("");
  const [imageFailed, setImageFailed] = useState(false);

  const displayStatus = finding.engineer_status ?? finding.ai_status ?? "Not yet evaluated";

  return (
    <div className="rounded-lg border border-neutral-50">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <span className="text-b2 font-medium text-neutral-300">
          Clause {finding.clause ?? "General"}: {finding.requirement_text.slice(0, 80)}
          {finding.requirement_text.length > 80 ? "..." : ""}
        </span>
        <Badge tone={badgeToneForStatus(displayStatus)}>{displayStatus}</Badge>
      </button>

      {expanded && (
        <div className="border-t border-neutral-50 p-5">
          <div className="mb-5 grid grid-cols-2 gap-6">
            <div>
              <p className="mb-1 text-b3 text-neutral-100">Requirement</p>
              <p className="mb-3 text-b2 text-neutral-300">{finding.requirement_text}</p>
              <p className="mb-1 text-b3 text-neutral-100">AI Recommendation</p>
              <Badge tone={badgeToneForStatus(finding.ai_status)}>{finding.ai_status ?? "Not yet evaluated"}</Badge>
              {finding.remark && (
                <p className="mt-2 text-b3 text-neutral-75">{finding.remark}</p>
              )}
            </div>
            <div>
              <p className="mb-1 text-b3 text-neutral-100">
                Cited Evidence {finding.evidence?.page_number ? `(Page ${finding.evidence.page_number})` : ""}
              </p>
              <p className="mb-3 rounded-md bg-neutral-50 px-4 py-3 text-b3 italic text-neutral-75">
                {finding.evidence?.quoted_text || "Run AI Verification for this bidder to see cited evidence here."}
              </p>
              {finding.evidence?.page_id && !imageFailed && (
                <>
                  <p className="mb-1 text-b3 text-neutral-100">
                    Original Document Preview (check numbers &amp; ratings)
                  </p>
                  {/* eslint-disable-next-line @next/next/no-img-element -- external backend-served file, not a Next-optimizable local asset */}
                  <img
                    src={getPageImageUrl(finding.evidence.page_id)}
                    alt={`Page ${finding.evidence.page_number ?? ""} of ${finding.evidence.document_name ?? "the cited document"}`}
                    onError={() => setImageFailed(true)}
                    className="w-full rounded-md border border-neutral-50"
                  />
                </>
              )}
            </div>
          </div>

          {finding.audit_history.length > 0 && (
            <div className="mb-5 border-t border-neutral-50 pt-5">
              <p className="mb-2 text-b3 font-medium text-neutral-100">Audit History</p>
              <div className="flex flex-col gap-1.5">
                {finding.audit_history.map((log, i) => (
                  <p key={i} className="text-b3 text-neutral-75">
                    {log.who} changed {log.what_changed} from &quot;{log.old_value}&quot; to &quot;{log.new_value}
                    &quot;{log.reason ? ` — ${log.reason}` : ""}
                  </p>
                ))}
              </div>
            </div>
          )}

          <div className="mb-5 border-t border-neutral-50 pt-5">
            {/* items-end: Confirm/Flag are single buttons while Override/
                Clarification are a stack of fields + button — without this,
                CSS Grid's default stretch makes Confirm/Flag balloon to the
                full row height to match the taller columns. This bottom-
                aligns every column instead, so all 4 action buttons end up
                the same compact size. */}
            <div className="grid grid-cols-4 items-end gap-3">
              <Button
                variant="primary"
                className="w-full justify-center"
                disabled={isMutating}
                onClick={onConfirm}
              >
                Confirm
              </Button>

              <div>
                <select
                  value={overrideChoice}
                  onChange={(e) => setOverrideChoice(e.target.value as typeof overrideChoice)}
                  className="mb-2 w-full rounded-md border border-neutral-50 px-3 py-2 text-b3 text-neutral-300 focus:outline-none"
                >
                  <option>Complied</option>
                  <option>Not Complied</option>
                  <option>N/A</option>
                </select>
                <input
                  value={overrideReason}
                  onChange={(e) => setOverrideReason(e.target.value)}
                  placeholder="Reason for override (mandatory)"
                  className="mb-2 w-full rounded-md border border-neutral-50 px-3 py-2 text-b3 text-neutral-300 placeholder:text-neutral-75 focus:outline-none"
                />
                <Button
                  variant="primary"
                  className="w-full justify-center"
                  disabled={!overrideReason.trim() || isMutating}
                  onClick={() => {
                    onOverride(overrideChoice, overrideReason);
                    setOverrideReason("");
                  }}
                >
                  Submit Override
                </Button>
              </div>

              <div>
                <input
                  value={clarificationNote}
                  onChange={(e) => setClarificationNote(e.target.value)}
                  placeholder="Clarification note"
                  className="mb-2 w-full rounded-md border border-neutral-50 px-3 py-2 text-b3 text-neutral-300 placeholder:text-neutral-75 focus:outline-none"
                />
                <Button
                  variant="primary"
                  className="w-full justify-center"
                  disabled={isMutating}
                  onClick={() => {
                    onFlag(clarificationNote || "Clarification requested");
                    setClarificationNote("");
                  }}
                >
                  Request Clarification
                </Button>
              </div>

              <Button
                variant="primary"
                className="w-full justify-center"
                disabled={isMutating}
                onClick={() => onFlag("Flagged for committee review")}
              >
                Flag for Review
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function VerificationResultsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { tenderId, tenderName, clearActiveTender } = useActiveTenderStore();
  const [selectedBidderId, setSelectedBidderId] = useState<number | null>(null);

  const biddersQuery = useQuery({
    queryKey: ["bidders", tenderId],
    queryFn: () => listBidders(tenderId as number),
    enabled: tenderId !== null,
  });

  const bidders = biddersQuery.data ?? [];
  const activeBidder = bidders.find((b) => b.id === selectedBidderId) ?? bidders[0];

  const findingsQuery = useQuery({
    queryKey: ["findings", tenderId, activeBidder?.id],
    queryFn: () => getFindings(tenderId as number, activeBidder!.id),
    enabled: tenderId !== null && !!activeBidder,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["findings", tenderId, activeBidder?.id] });
  };

  const confirmMutation = useMutation({
    mutationFn: (findingId: number) => confirmFinding(findingId),
    onSuccess: invalidate,
    onError: (err) => alert(err instanceof ApiError ? err.message : "Failed to confirm finding."),
  });

  const overrideMutation = useMutation({
    mutationFn: ({ findingId, status, reason }: { findingId: number; status: string; reason: string }) =>
      overrideFinding(findingId, status, reason),
    onSuccess: invalidate,
    onError: (err) => alert(err instanceof ApiError ? err.message : "Failed to submit override."),
  });

  const flagMutation = useMutation({
    mutationFn: ({ findingId, reason }: { findingId: number; reason: string }) => flagFinding(findingId, reason),
    onSuccess: invalidate,
    onError: (err) => alert(err instanceof ApiError ? err.message : "Failed to flag finding."),
  });

  const qualifyMutation = useMutation({
    mutationFn: (status: "Qualified" | "Not Qualified") =>
      qualifyBidder(tenderId as number, activeBidder!.id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bidders", tenderId] }),
    onError: (err) => alert(err instanceof ApiError ? err.message : "Failed to update qualification status."),
  });

  if (tenderId === null) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
        <p className="text-h3 text-neutral-300">No tender selected</p>
        <p className="max-w-md text-b2 text-neutral-75">
          Open a tender from the Home screen first — this page needs to know which
          tender&apos;s findings it&apos;s reviewing.
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

  const findings = findingsQuery.data ?? [];
  const isMutating = confirmMutation.isPending || overrideMutation.isPending || flagMutation.isPending;

  return (
    <>
      <WorkspaceHeader
        title="Verification Results"
        tenderOptions={[tenderName ?? "Tender"]}
        onBack={() => {
          clearActiveTender();
          router.push("/");
        }}
      />

      <div className="mb-6 flex items-center gap-4">
        {bidders.length > 0 ? (
          <select
            value={activeBidder?.id}
            onChange={(e) => setSelectedBidderId(Number(e.target.value))}
            className="rounded-md border border-neutral-50 bg-white px-4 py-2.5 text-b2 text-neutral-300 focus:outline-none"
          >
            {bidders.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        ) : (
          <p className="text-b2 text-neutral-75">
            {biddersQuery.isLoading ? "Loading bidders..." : "No bidders added yet."}
          </p>
        )}

        {activeBidder && (
          <>
            <div className="flex-1 rounded-md bg-violet-50 px-4 py-2.5 text-b2 text-violet-300">
              Bidder: {activeBidder.name} — Current Qualification Status: {activeBidder.final_status}
            </div>
            <Button
              variant="primary"
              disabled={qualifyMutation.isPending}
              onClick={() => qualifyMutation.mutate("Qualified")}
            >
              Mark as Qualified
            </Button>
            <Button
              variant="dark"
              disabled={qualifyMutation.isPending}
              onClick={() => qualifyMutation.mutate("Not Qualified")}
            >
              Mark Not Qualified
            </Button>
          </>
        )}
      </div>

      {findingsQuery.isLoading && (
        <p className="py-8 text-center text-b2 text-neutral-75">Loading findings...</p>
      )}
      {!findingsQuery.isLoading && activeBidder && findings.length === 0 && (
        <p className="py-8 text-center text-b2 text-neutral-75">
          No findings yet for {activeBidder.name} — run AI Verification on the TBE Working Excel screen first.
        </p>
      )}

      <div className="flex flex-col gap-4">
        {findings.map((f) => (
          <FindingCard
            key={f.id}
            finding={f}
            isMutating={isMutating}
            onConfirm={() => confirmMutation.mutate(f.id)}
            onOverride={(status, reason) => overrideMutation.mutate({ findingId: f.id, status, reason })}
            onFlag={(reason) => flagMutation.mutate({ findingId: f.id, reason })}
          />
        ))}
      </div>
    </>
  );
}
