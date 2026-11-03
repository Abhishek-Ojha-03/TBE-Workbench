"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import WorkspaceHeader from "@/components/layout/workspace-header";
import Button from "@/components/ui/button";
import Badge from "@/components/ui/badge";
import {
  ApiError,
  ComplianceRow,
  completeTender,
  downloadMom,
  downloadTer,
  draftClarificationLetter,
  getComplianceMatrix,
  listBidders,
  uploadClarificationReply,
} from "@/lib/api";
import { useActiveTenderStore } from "@/lib/store";

function DownloadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 4v12M12 16l-4-4M12 16l4-4" />
      <path d="M4 20h16" />
    </svg>
  );
}

function UploadIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 16V4M12 4l-4 4M12 4l4 4" />
      <path d="M4 16v3a2 2 0 002 2h12a2 2 0 002-2v-3" />
    </svg>
  );
}

function riskTone(risk: string): "violet" | "neutral" {
  return risk === "Low Risk" || risk === "Clean" ? "violet" : "neutral";
}

function ComplianceScoreAndRiskMatrix({ rows }: { rows: ComplianceRow[] }) {
  const maxScore = Math.max(1, ...rows.map((r) => r.score_pct));

  if (rows.length === 0) {
    return (
      <p className="mb-4 text-b3 text-neutral-75">
        No bidders with findings yet — run AI Verification on the TBE Working Excel screen first.
      </p>
    );
  }

  return (
    <details className="mb-4 rounded-md border border-neutral-50 p-3">
      <summary className="cursor-pointer text-b3 font-medium text-neutral-200">
        Preview: Compliance Scores &amp; Risk Matrix
      </summary>
      <div className="mt-4">
        <p className="mb-2 text-b3 font-medium text-neutral-300">Compliance Score &amp; Risk Summary</p>
        <div className="mb-5 overflow-hidden rounded-lg border border-neutral-50">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-neutral-50/60 text-label text-neutral-100">
                <th className="px-4 py-2 font-normal">Bidder</th>
                <th className="px-4 py-2 font-normal">Total Clauses</th>
                <th className="px-4 py-2 font-normal">Complied</th>
                <th className="px-4 py-2 font-normal">Not Complied</th>
                <th className="px-4 py-2 font-normal">Under Review</th>
                <th className="px-4 py-2 font-normal">Score</th>
                <th className="px-4 py-2 font-normal">Risk</th>
                <th className="px-4 py-2 font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.bidder_id} className="border-t border-neutral-50 text-b3 text-neutral-300">
                  <td className="px-4 py-2">{r.bidder_name}</td>
                  <td className="px-4 py-2">{r.total_clauses}</td>
                  <td className="px-4 py-2">{r.complied}</td>
                  <td className="px-4 py-2">{r.not_complied}</td>
                  <td className="px-4 py-2">{r.under_review}</td>
                  <td className="px-4 py-2">{r.score_pct}%</td>
                  <td className="px-4 py-2">
                    <Badge tone={riskTone(r.risk)}>{r.risk}</Badge>
                  </td>
                  <td className="px-4 py-2">{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mb-3 text-b3 font-medium text-neutral-300">Bidder Technical Compliance Comparison</p>
        <div className="flex flex-col gap-3">
          {rows.map((r) => (
            <div key={r.bidder_id} className="flex items-center gap-3">
              <span className="w-24 shrink-0 text-b3 text-neutral-200">{r.bidder_name}</span>
              <div className="h-5 flex-1 rounded-full bg-neutral-50">
                <div
                  className="h-5 rounded-full bg-violet-300"
                  style={{ width: `${(r.score_pct / maxScore) * 100}%` }}
                />
              </div>
              <span className="w-10 shrink-0 text-right text-b3 text-neutral-200">{r.score_pct}%</span>
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}

function GenerateCard({
  title,
  description,
  buttonLabel,
  onGenerate,
  extra,
}: {
  title: string;
  description: React.ReactNode;
  buttonLabel: string;
  onGenerate: () => Promise<void>;
  extra?: React.ReactNode;
}) {
  const [state, setState] = useState<"idle" | "generating" | "done" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  return (
    <div className="rounded-lg border border-neutral-50 p-5">
      <h3 className="mb-2 text-h3 text-neutral-300">{title}</h3>
      <div className="mb-4 text-b3 text-neutral-75">{description}</div>
      {extra}
      <Button
        variant="primary"
        className="w-full justify-center"
        disabled={state === "generating"}
        onClick={async () => {
          setState("generating");
          setErrorMsg(null);
          try {
            // Single real backend call generates the document AND streams
            // it back — the browser download is triggered as part of this,
            // same as a normal file-download link, not a separate step.
            await onGenerate();
            setState("done");
          } catch (err) {
            setErrorMsg(err instanceof ApiError ? err.message : "Failed to generate document.");
            setState("error");
          }
        }}
      >
        {state === "generating" ? "Generating..." : buttonLabel}
        {state === "idle" && <DownloadIcon />}
      </Button>

      {state === "done" && (
        <p className="mt-3 rounded-md bg-violet-50 px-4 py-3 text-b3 text-violet-300">
          Document generated — check your browser&apos;s downloads.
        </p>
      )}
      {state === "error" && errorMsg && (
        <p className="mt-3 rounded-md bg-red-50 px-4 py-3 text-b3 text-red-500">{errorMsg}</p>
      )}
    </div>
  );
}

export default function ReportsCompletionPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { tenderId, tenderName, clearActiveTender } = useActiveTenderStore();
  const [selectedBidderId, setSelectedBidderId] = useState<number | null>(null);
  const [letterTab, setLetterTab] = useState<"preview" | "edit">("preview");
  const [letter, setLetter] = useState<string | null>(null);
  const [flaggedCount, setFlaggedCount] = useState<number | null>(null);
  const [replyFiles, setReplyFiles] = useState<File[]>([]);

  const biddersQuery = useQuery({
    queryKey: ["bidders", tenderId],
    queryFn: () => listBidders(tenderId as number),
    enabled: tenderId !== null,
  });
  const bidders = biddersQuery.data ?? [];
  const activeBidder = bidders.find((b) => b.id === selectedBidderId) ?? bidders[0];

  const complianceQuery = useQuery({
    queryKey: ["compliance-matrix", tenderId],
    queryFn: () => getComplianceMatrix(tenderId as number),
    enabled: tenderId !== null,
  });

  const draftMutation = useMutation({
    mutationFn: () => draftClarificationLetter(tenderId as number, activeBidder!.id),
    onSuccess: (res) => {
      setLetter(res.letter || "No flagged or needs-review clauses found for this bidder.");
      setFlaggedCount(res.flagged_count);
      setLetterTab("preview");
    },
    onError: (err) => alert(err instanceof ApiError ? err.message : "Failed to draft clarification letter."),
  });

  const deltaMutation = useMutation({
    mutationFn: () => uploadClarificationReply(tenderId as number, activeBidder!.id, replyFiles),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["compliance-matrix", tenderId] });
      queryClient.invalidateQueries({ queryKey: ["bidders", tenderId] });
    },
    onError: (err) => alert(err instanceof ApiError ? err.message : "Delta re-verification failed."),
  });

  const completeMutation = useMutation({
    mutationFn: () => completeTender(tenderId as number),
    onSuccess: () => {
      alert("Tender marked as completed and archived.");
      clearActiveTender();
      router.push("/");
    },
    onError: (err) => alert(err instanceof ApiError ? err.message : "Failed to complete tender."),
  });

  if (tenderId === null) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
        <p className="text-h3 text-neutral-300">No tender selected</p>
        <p className="max-w-md text-b2 text-neutral-75">
          Open a tender from the Home screen first — this page needs to know which
          tender&apos;s deliverables it&apos;s generating.
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

  const complianceRows = complianceQuery.data ?? [];

  return (
    <>
      <WorkspaceHeader
        title="Reports & Completion"
        tenderOptions={[tenderName ?? "Tender"]}
        onBack={() => {
          clearActiveTender();
          router.push("/");
        }}
      />

      {/* Generate MOM + TER */}
      <div className="mb-8 grid grid-cols-2 gap-6">
        <GenerateCard
          title="Generate TBE MOM (.docx)"
          buttonLabel="Generate TBE MOM"
          onGenerate={() => downloadMom(tenderId as number)}
          description={
            <>
              Compiles the official Minutes of Meeting in standard format:
              <ul className="mt-2 list-disc space-y-1 pl-5">
                <li>Meeting committee members and venue</li>
                <li>AI-synthesized executive proceeding summary</li>
                <li>AI-synthesized technical compliance scoring table (per-bidder %)</li>
                <li>Strategic negotiation &amp; discussion talking points for committee</li>
                <li>Signature blocks</li>
              </ul>
            </>
          }
          extra={<ComplianceScoreAndRiskMatrix rows={complianceRows} />}
        />

        <GenerateCard
          title="Generate TBE Report (.docx)"
          buttonLabel="Generate TER Report"
          onGenerate={() => downloadTer(tenderId as number)}
          description={
            <>
              Compiles the full Technical Evaluation Report:
              <ul className="mt-2 list-disc space-y-1 pl-5">
                <li>Cover page &amp; index</li>
                <li>Executive technical summary</li>
                <li>Full comparison matrix (clauses, specified ratings vs. bidder offerings)</li>
                <li>Final qualification recommendation</li>
              </ul>
            </>
          }
        />
      </div>

      {/* Clarification Management */}
      <div className="mb-8 rounded-lg border border-neutral-50 p-5">
        <h3 className="mb-2 text-h3 text-neutral-300">Clarification Management &amp; Delta Re-Verification</h3>
        <p className="mb-4 text-b3 text-neutral-75">
          When bidders have missing documents or unresolved queries, draft formal clarification
          letters, upload their replies, and re-verify only the affected rows without
          re-evaluating the whole tender.
        </p>

        <div className="mb-4 flex items-center gap-4">
          {bidders.length > 0 ? (
            <select
              value={activeBidder?.id}
              onChange={(e) => {
                setSelectedBidderId(Number(e.target.value));
                setLetter(null);
                setFlaggedCount(null);
                setReplyFiles([]);
              }}
              className="rounded-md border border-neutral-50 bg-white px-4 py-2.5 text-b2 text-neutral-300 focus:outline-none"
            >
              {bidders.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </select>
          ) : (
            <p className="text-b2 text-neutral-75">No bidders added yet.</p>
          )}
          {flaggedCount !== null && (
            <span className="text-b3 text-neutral-100">
              Flagged / Review Items: <span className="font-medium text-neutral-300">{flaggedCount} item(s)</span>
            </span>
          )}
        </div>

        <Button
          variant="primary"
          disabled={draftMutation.isPending || !activeBidder}
          onClick={() => draftMutation.mutate()}
        >
          {draftMutation.isPending ? "Drafting..." : "Draft Official Clarification Letter via AI"}
        </Button>

        {letter !== null && (
          <div className="mt-4">
            <div className="mb-3 flex gap-1 rounded-full bg-neutral-50 p-1 w-fit">
              <button
                type="button"
                onClick={() => setLetterTab("preview")}
                className={`rounded-full px-4 py-2 text-b3 font-medium transition-colors ${
                  letterTab === "preview" ? "bg-white text-violet-300 shadow-sm" : "text-neutral-200"
                }`}
              >
                Formal Letter Preview (Clean)
              </button>
              <button
                type="button"
                onClick={() => setLetterTab("edit")}
                className={`rounded-full px-4 py-2 text-b3 font-medium transition-colors ${
                  letterTab === "edit" ? "bg-white text-violet-300 shadow-sm" : "text-neutral-200"
                }`}
              >
                Edit Letter Content
              </button>
            </div>

            {letterTab === "preview" ? (
              <div className="max-h-96 overflow-y-auto rounded-lg border border-neutral-50 bg-white p-6 text-b3 leading-relaxed text-neutral-200 whitespace-pre-wrap">
                {letter}
              </div>
            ) : (
              <>
                <p className="mb-2 text-caption text-neutral-75">
                  You can edit the raw text or formatting below if needed:
                </p>
                <textarea
                  value={letter}
                  onChange={(e) => setLetter(e.target.value)}
                  rows={14}
                  className="max-h-96 w-full resize-y rounded-lg border border-neutral-50 p-4 text-b3 leading-relaxed text-neutral-200 focus:border-violet-200 focus:outline-none"
                />
              </>
            )}
          </div>
        )}

        <details className="mt-4 rounded-md border border-neutral-50 p-4" open>
          <summary className="cursor-pointer text-b3 font-medium text-neutral-200">
            Upload Clarification Reply &amp; Delta Re-Verify
          </summary>
          <div className="mt-3">
            <label className="mb-3 flex cursor-pointer items-center gap-3 rounded-lg border-2 border-dashed border-violet-200 bg-violet-50/30 px-5 py-4">
              <UploadIcon />
              <span className="text-b2 text-neutral-300">
                {replyFiles.length > 0
                  ? `${replyFiles.length} file(s) selected`
                  : "Upload bidder's clarification response PDF(s)"}
              </span>
              <input
                type="file"
                multiple
                accept=".pdf"
                className="hidden"
                onChange={(e) => setReplyFiles(Array.from(e.target.files ?? []))}
              />
            </label>

            {replyFiles.length > 0 && (
              <Button
                variant="primary"
                disabled={deltaMutation.isPending || !activeBidder}
                onClick={() => deltaMutation.mutate()}
              >
                {deltaMutation.isPending
                  ? "Indexing documents and re-verifying..."
                  : `Run Delta Re-Verification (${replyFiles.length} files)`}
              </Button>
            )}

            {deltaMutation.data && (
              <div className="mt-3 rounded-md border-l-4 border-violet-300 bg-neutral-50 px-4 py-3">
                <p className="mb-1 text-b3 font-medium text-neutral-300">
                  Re-Verification Result for {activeBidder?.name}
                </p>
                <p className="text-b3 text-neutral-200">
                  Updated Qualification Status:{" "}
                  <span className="font-medium text-violet-300">{deltaMutation.data.new_status}</span>
                  <br />
                  Clauses Re-Checked: {deltaMutation.data.rechecked_count} (Clauses:{" "}
                  {deltaMutation.data.clauses.join(", ")})
                </p>
              </div>
            )}
          </div>
        </details>
      </div>

      {/* Complete & Archive */}
      <div className="rounded-lg border border-neutral-50 p-5">
        <h3 className="mb-2 text-h3 text-neutral-300">Mark Tender as Completed</h3>
        <p className="mb-4 text-b3 text-neutral-75">
          Once marked Completed, the evaluation baseline is locked and the tender is archived to
          the Home page in read-only mode.
        </p>
        <Button variant="dark" disabled={completeMutation.isPending} onClick={() => completeMutation.mutate()}>
          {completeMutation.isPending ? "Completing..." : "Complete & Archive Tender"}
        </Button>
      </div>
    </>
  );
}
