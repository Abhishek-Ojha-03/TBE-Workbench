"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import TopNav from "@/components/layout/top-nav";
import Button from "@/components/ui/button";
import { ApiError, createTender, listTenders, Tender } from "@/lib/api";
import { useActiveTenderStore } from "@/lib/store";

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function SortIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M7 10l5-5 5 5M7 14l5 5 5-5" />
    </svg>
  );
}

function formatCreatedAt(iso: string): string {
  // Backend serializes naive UTC timestamps (no "Z"/offset) — without this,
  // `new Date(iso)` is parsed as local time instead of UTC, showing the
  // wrong clock time by the browser's UTC offset.
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  const date = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).replace(/ /g, "-");
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return `${date} | ${time}`;
}

function CreateTenderModal({ onClose }: { onClose: () => void }) {
  const [description, setDescription] = useState("");
  const [nitNumber, setNitNumber] = useState("");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => createTender(description.trim(), nitNumber.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tenders"] });
      onClose();
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : "Failed to create tender.");
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-300/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg bg-white p-8 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-6 text-h3 font-semibold text-neutral-300">New Tender Details</h3>

        <label className="mb-1 block text-b2 text-neutral-300">Tender Description</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e. g.  Supply sdasdvnl"
          rows={3}
          className="mb-5 w-full resize-none rounded-md border border-neutral-50 px-4 py-3 text-b2 text-neutral-300 placeholder:italic placeholder:text-neutral-75 focus:border-violet-200 focus:outline-none"
        />

        <label className="mb-1 block text-b2 text-neutral-300">NIT Number</label>
        <div className="flex gap-3">
          <input
            value={nitNumber}
            onChange={(e) => setNitNumber(e.target.value)}
            placeholder="e. g. 13165"
            className="flex-1 rounded-md border border-neutral-50 px-4 py-2.5 text-b2 text-neutral-300 placeholder:text-neutral-75 focus:border-violet-200 focus:outline-none"
          />
          <Button
            variant="primary"
            disabled={!description.trim() || !nitNumber.trim() || mutation.isPending}
            onClick={() => {
              setError(null);
              mutation.mutate();
            }}
          >
            {mutation.isPending ? "Creating..." : "Create Tender"}
            {!mutation.isPending && <PlusIcon />}
          </Button>
        </div>

        {error && <p className="mt-3 text-b3 text-red-500">{error}</p>}
      </div>
    </div>
  );
}

export default function HomePage() {
  const router = useRouter();
  const setActiveTender = useActiveTenderStore((s) => s.setActiveTender);

  const [activeTab, setActiveTab] = useState<"open" | "completed">("open");
  const [searchQuery, setSearchQuery] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  const { data: tenders, isLoading, isError } = useQuery({
    queryKey: ["tenders", activeTab],
    queryFn: () => listTenders(activeTab),
  });

  const rows = tenders ?? [];
  const filteredRows = searchQuery.trim()
    ? rows.filter(
        (r) =>
          r.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
          r.nit_no.includes(searchQuery)
      )
    : rows;

  function openTender(tender: Tender) {
    setActiveTender(tender.id, tender.description);
    router.push(tender.status === "completed" ? "/archive" : "/specification");
  }

  return (
    <>
      <TopNav />

      <main className="flex-1 bg-background px-10 py-8">
        <h1 className="mb-6 text-display text-neutral-100">TBE Workbench</h1>

        <div className="mb-6 flex items-center gap-4">
          <div className="flex items-center gap-1 rounded-full bg-white p-1">
            <button
              type="button"
              onClick={() => setActiveTab("open")}
              className={`rounded-full px-4 py-2 text-b2 font-medium transition-colors ${
                activeTab === "open"
                  ? "bg-violet-50 text-violet-300"
                  : "text-neutral-200 hover:bg-neutral-50"
              }`}
            >
              Open Tenders
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("completed")}
              className={`rounded-full px-4 py-2 text-b2 font-medium transition-colors ${
                activeTab === "completed"
                  ? "bg-violet-50 text-violet-300"
                  : "text-neutral-200 hover:bg-neutral-50"
              }`}
            >
              Completed Tenders
            </button>
          </div>

          <div className="flex w-80 items-center gap-2 rounded-md border border-neutral-50 bg-white px-4 py-2.5 text-neutral-75">
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search Tenders here"
              className="w-full bg-transparent text-b2 text-neutral-300 placeholder:text-neutral-75 focus:outline-none"
            />
            <SearchIcon />
          </div>

          <div className="flex-1" />

          <Button variant="primary" onClick={() => setModalOpen(true)}>
            Create New
            <PlusIcon />
          </Button>
        </div>

        <div className="overflow-hidden rounded-lg bg-white">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-neutral-50/60 text-label text-neutral-100">
                <th className="px-6 py-4 font-normal">Tender name</th>
                <th className="px-6 py-4 font-normal">NIT</th>
                <th className="px-6 py-4 font-normal">Bidders</th>
                <th className="px-6 py-4 text-right font-normal">
                  <span className="inline-flex items-center gap-1">
                    Created on
                    <SortIcon />
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading && (
                <tr>
                  <td colSpan={4} className="px-6 py-10 text-center text-b2 text-neutral-75">
                    Loading tenders...
                  </td>
                </tr>
              )}
              {isError && (
                <tr>
                  <td colSpan={4} className="px-6 py-10 text-center text-b2 text-red-500">
                    Couldn&apos;t reach the API. Is the backend running at{" "}
                    {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}?
                  </td>
                </tr>
              )}
              {!isLoading && !isError &&
                filteredRows.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => openTender(row)}
                    className="cursor-pointer border-t border-neutral-50 text-b2 text-neutral-300 hover:bg-neutral-50/40"
                  >
                    <td className="px-6 py-4">{row.description}</td>
                    <td className="px-6 py-4">{row.nit_no}</td>
                    <td className="px-6 py-4 font-semibold text-violet-300">{row.bidder_count}</td>
                    <td className="px-6 py-4 text-right text-neutral-100">{formatCreatedAt(row.created_at)}</td>
                  </tr>
                ))}
              {!isLoading && !isError && filteredRows.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-6 py-10 text-center text-b2 text-neutral-75">
                    No {activeTab === "open" ? "open" : "completed"} tenders found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </main>

      {modalOpen && <CreateTenderModal onClose={() => setModalOpen(false)} />}
    </>
  );
}
