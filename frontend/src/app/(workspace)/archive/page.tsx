"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import WorkspaceHeader from "@/components/layout/workspace-header";
import Button from "@/components/ui/button";
import Badge from "@/components/ui/badge";
import {
  ApiError,
  ArchiveBidderDetail,
  downloadArchiveDocument,
  downloadArchiveFindingsCsv,
  downloadMom,
  downloadTer,
  downloadWorkingExcel,
  getArchive,
} from "@/lib/api";
import { useActiveTenderStore } from "@/lib/store";

function formatCreatedAt(iso: string): string {
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return (
    d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).replace(/ /g, "-") +
    " " +
    d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
  );
}

function statusTone(status: string): "violet" | "neutral" {
  return status === "Qualified" ? "violet" : "neutral";
}

function formatPrice(price: number | null, currency: string): string {
  if (price === null) return "—";
  return `${currency} ${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 4v12M12 16l-4-4M12 16l4-4" />
      <path d="M4 20h16" />
    </svg>
  );
}

function DocumentDownloadButton({ id, fileName, label }: { id: number; fileName: string; label: string }) {
  const mutation = useMutation({
    mutationFn: () => downloadArchiveDocument(id, fileName),
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Failed to download document.");
    },
  });

  return (
    <button
      type="button"
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
      className="flex items-center gap-2 rounded-md border border-neutral-50 px-3 py-2 text-b3 text-neutral-300 hover:bg-neutral-50 disabled:opacity-50"
    >
      <DownloadIcon />
      {mutation.isPending ? "Downloading..." : label}
    </button>
  );
}

function BidderDetailCard({ tenderId, detail }: { tenderId: number; detail: ArchiveBidderDetail }) {
  const [expanded, setExpanded] = useState(false);

  const csvMutation = useMutation({
    mutationFn: () => downloadArchiveFindingsCsv(tenderId, detail.bidder_id, detail.name),
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Failed to download findings CSV.");
    },
  });

  return (
    <div className="rounded-lg border border-neutral-50">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <span className="text-b2 font-medium text-neutral-300">{detail.name}</span>
        <Badge tone={statusTone(detail.final_status)}>{detail.final_status}</Badge>
      </button>

      {expanded && (
        <div className="border-t border-neutral-50 p-5">
          {detail.findings.length > 0 ? (
            <>
              <div className="mb-3 overflow-hidden rounded-lg border border-neutral-50">
                <table className="w-full text-left text-b3">
                  <thead className="bg-neutral-50/60 text-neutral-100">
                    <tr>
                      <th className="px-4 py-2 font-normal">Clause</th>
                      <th className="px-4 py-2 font-normal">Requirement</th>
                      <th className="px-4 py-2 font-normal">Status</th>
                      <th className="px-4 py-2 font-normal">Bidder Offered (Quote)</th>
                      <th className="px-4 py-2 font-normal">Remark</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.findings.map((f, i) => (
                      <tr key={i} className="border-t border-neutral-50 text-neutral-300">
                        <td className="px-4 py-2">{f.clause}</td>
                        <td className="max-w-[240px] px-4 py-2">{f.requirement_text}</td>
                        <td className="px-4 py-2">{f.status}</td>
                        <td className="max-w-[240px] px-4 py-2">{f.offered_value}</td>
                        <td className="px-4 py-2">{f.remark || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Button
                variant="primary"
                disabled={csvMutation.isPending}
                onClick={() => csvMutation.mutate()}
                className="mb-4"
              >
                {csvMutation.isPending ? "Downloading..." : `Download ${detail.name}'s Findings (CSV)`}
              </Button>
            </>
          ) : (
            <p className="mb-4 text-b3 text-neutral-75">No findings recorded for this bidder.</p>
          )}

          <p className="mb-2 text-b3 font-medium text-neutral-300">Original Submitted Documents</p>
          {detail.documents.length === 0 ? (
            <p className="text-b3 text-neutral-75">No documents on file for this bidder.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {detail.documents.map((d) =>
                d.available ? (
                  <DocumentDownloadButton
                    key={d.id}
                    id={d.id}
                    fileName={d.file_name}
                    label={`${d.file_name} (${d.document_type || "Document"})`}
                  />
                ) : (
                  <span key={d.id} className="rounded-md bg-neutral-50 px-3 py-2 text-b3 text-neutral-75">
                    {d.file_name} — original file no longer on disk
                  </span>
                )
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function GenerateDeliverableButton({
  label,
  onGenerate,
}: {
  label: string;
  onGenerate: () => Promise<void>;
}) {
  const [state, setState] = useState<"idle" | "generating" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  return (
    <div className="flex-1">
      <Button
        variant="primary"
        className="w-full justify-center"
        disabled={state === "generating"}
        onClick={async () => {
          setState("generating");
          setErrorMsg(null);
          try {
            await onGenerate();
            setState("idle");
          } catch (err) {
            setErrorMsg(err instanceof ApiError ? err.message : "Failed to generate document.");
            setState("error");
          }
        }}
      >
        {state === "generating" ? "Generating..." : label}
      </Button>
      {state === "error" && errorMsg && <p className="mt-2 text-b3 text-red-500">{errorMsg}</p>}
    </div>
  );
}

export default function ArchivePage() {
  const router = useRouter();
  const { tenderId, clearActiveTender } = useActiveTenderStore();

  const archiveQuery = useQuery({
    queryKey: ["archive", tenderId],
    queryFn: () => getArchive(tenderId as number),
    enabled: tenderId !== null,
  });

  if (tenderId === null) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
        <p className="text-h3 text-neutral-300">No tender selected</p>
        <p className="max-w-md text-b2 text-neutral-75">
          Open a completed tender from the Home screen first.
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

  const data = archiveQuery.data;

  return (
    <>
      <WorkspaceHeader
        title="Tender Archive"
        tenderOptions={[data?.tender.description ?? "Tender"]}
        onBack={() => {
          clearActiveTender();
          router.push("/");
        }}
      />

      {archiveQuery.isLoading && (
        <p className="py-8 text-center text-b2 text-neutral-75">Loading archive...</p>
      )}

      {data && (
        <>
          <div className="mb-6 rounded-lg bg-violet-50 px-5 py-4 text-b2 text-violet-300">
            Completed, Read-Only — NIT No: {data.tender.nit_no} · Created:{" "}
            {formatCreatedAt(data.tender.created_at)}. This is a read-only archive of a completed
            tender. Use it to find the original specification and exactly what each bidder
            offered, if a similar tender comes up again.
          </div>

          <h3 className="mb-3 text-h3 text-neutral-300">Original Specification</h3>
          {data.spec_documents.length === 0 ? (
            <p className="mb-6 text-b3 text-neutral-75">No specification document found for this tender.</p>
          ) : (
            <div className="mb-6 flex flex-wrap gap-2">
              {data.spec_documents.map((d) =>
                d.available ? (
                  <DocumentDownloadButton key={d.id} id={d.id} fileName={d.file_name} label={d.file_name} />
                ) : (
                  <span key={d.id} className="rounded-md bg-neutral-50 px-3 py-2 text-b3 text-neutral-75">
                    {d.file_name} — original file no longer on disk
                  </span>
                )
              )}
            </div>
          )}

          <h3 className="mb-3 text-h3 text-neutral-300">Bidder Summary — Status, Price &amp; Rank</h3>
          {data.bidders_summary.length === 0 ? (
            <p className="mb-6 text-b3 text-neutral-75">No bidders were registered for this tender.</p>
          ) : (
            <div className="mb-6 overflow-hidden rounded-lg border border-neutral-50">
              <table className="w-full text-left text-b3">
                <thead className="bg-neutral-50/60 text-neutral-100">
                  <tr>
                    <th className="px-4 py-3 font-normal">Bidder</th>
                    <th className="px-4 py-3 font-normal">Final Status</th>
                    <th className="px-4 py-3 font-normal">Quoted Price</th>
                    <th className="px-4 py-3 font-normal">Commercial Rank</th>
                  </tr>
                </thead>
                <tbody>
                  {data.bidders_summary.map((b) => (
                    <tr key={b.bidder_id} className="border-t border-neutral-50 text-neutral-300">
                      <td className="px-4 py-3">{b.name}</td>
                      <td className="px-4 py-3">
                        <Badge tone={statusTone(b.final_status)}>{b.final_status}</Badge>
                      </td>
                      <td className="px-4 py-3">{formatPrice(b.quoted_price, b.currency)}</td>
                      <td className="px-4 py-3">{b.commercial_rank_label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3 className="mb-3 text-h3 text-neutral-300">What Each Bidder Offered</h3>
          <div className="mb-6 flex flex-col gap-3">
            {data.bidder_details.map((detail) => (
              <BidderDetailCard key={detail.bidder_id} tenderId={tenderId} detail={detail} />
            ))}
          </div>

          <h3 className="mb-3 text-h3 text-neutral-300">Generated Deliverables</h3>
          <div className="flex gap-4">
            <GenerateDeliverableButton
              label="Generate & Download Working Excel"
              onGenerate={() => downloadWorkingExcel(tenderId)}
            />
            <GenerateDeliverableButton
              label="Generate & Download MOM"
              onGenerate={() => downloadMom(tenderId)}
            />
            <GenerateDeliverableButton
              label="Generate & Download TER"
              onGenerate={() => downloadTer(tenderId)}
            />
          </div>
        </>
      )}
    </>
  );
}
