"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import WorkspaceHeader from "@/components/layout/workspace-header";
import Button from "@/components/ui/button";
import Badge from "@/components/ui/badge";
import {
  ApiError,
  CommercialRankingRow,
  fetchPricesWithAi,
  getCommercialRanking,
  listBidders,
} from "@/lib/api";
import { useActiveTenderStore } from "@/lib/store";

function rankTone(row: CommercialRankingRow): "violet" | "neutral" {
  return row.rank === 1 ? "violet" : "neutral";
}

function formatPrice(row: CommercialRankingRow): string {
  if (row.quoted_price === null || row.quoted_price <= 0) return "Price Not Mentioned";
  return `${row.currency} ${row.quoted_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function recommendation(row: CommercialRankingRow): string {
  if (row.quoted_price === null || row.quoted_price <= 0) return "Price Not Mentioned in Documents";
  return row.rank === 1 ? "Recommend (L1 Lowest Bidder)" : `Alternative (${row.label})`;
}

export default function CommercialEvaluationPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { tenderId, tenderName, clearActiveTender } = useActiveTenderStore();

  const biddersQuery = useQuery({
    queryKey: ["bidders", tenderId],
    queryFn: () => listBidders(tenderId as number),
    enabled: tenderId !== null,
  });

  const rankingQuery = useQuery({
    queryKey: ["commercial-ranking", tenderId],
    queryFn: () => getCommercialRanking(tenderId as number),
    enabled: tenderId !== null,
  });

  const fetchPricesMutation = useMutation({
    mutationFn: () => fetchPricesWithAi(tenderId as number),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["commercial-ranking", tenderId] });
    },
    onError: (err) => {
      alert(err instanceof ApiError ? err.message : "Failed to fetch prices with AI.");
    },
  });

  if (tenderId === null) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
        <p className="text-h3 text-neutral-300">No tender selected</p>
        <p className="max-w-md text-b2 text-neutral-75">
          Open a tender from the Home screen first — this page needs to know which
          tender&apos;s commercial bids it&apos;s evaluating.
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

  const bidders = biddersQuery.data ?? [];
  const qualifiedCount = bidders.filter((b) => b.final_status === "Qualified").length;
  const unqualified = bidders.filter((b) => b.final_status !== "Qualified");
  const ranking = rankingQuery.data ?? [];

  const l1Entry = ranking.find((r) => r.rank === 1) ?? null;
  const hasTie = ranking.some((r) => r.tie);
  const unpricedCount = ranking.filter((r) => r.quoted_price === null || r.quoted_price <= 0).length;

  return (
    <>
      <WorkspaceHeader
        title="Commercial Evaluation"
        tenderOptions={[tenderName ?? "Tender"]}
        onBack={() => {
          clearActiveTender();
          router.push("/");
        }}
      />

      <div className="mb-6 rounded-lg bg-violet-50 px-5 py-4 text-b2 text-violet-300">
        Two-Envelope Rule: commercial price evaluation opens only for technically qualified
        bidders. AI scans bidder documents for commercial price bids and computes the official
        L1/L2/L3 ranking.
      </div>

      {qualifiedCount === 0 ? (
        <div className="rounded-lg border border-neutral-50 p-5">
          <p className="mb-2 text-b2 font-medium text-neutral-300">
            No bidders have been marked Qualified yet.
          </p>
          <p className="mb-3 text-b3 text-neutral-75">
            Complete Technical Evaluation and set Final Status to Qualified in the Reports &amp;
            Completion screen before opening commercial evaluation.
          </p>
          {bidders.length > 0 && (
            <p className="text-b3 text-neutral-75">
              Bidders currently in the pool:{" "}
              {bidders.map((b) => `${b.name} (${b.final_status})`).join(", ")}
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="mb-6 rounded-lg border border-neutral-50 p-5 text-b2 text-neutral-300">
            {qualifiedCount} technically qualified bidder(s) are eligible for commercial
            evaluation.
            {unqualified.length > 0 && ` ${unqualified.length} unqualified bidder(s) excluded.`}
          </div>

          <div className="mb-6 flex items-center justify-between rounded-lg border border-neutral-50 p-5">
            <div>
              <h3 className="text-h3 text-neutral-300">AI Commercial Price Fetching</h3>
              <p className="text-b3 text-neutral-75">
                AI analyzes bidder commercial submissions, quotations, and schedules to retrieve
                quoted prices.
              </p>
            </div>
            <Button
              variant="primary"
              disabled={fetchPricesMutation.isPending}
              onClick={() => fetchPricesMutation.mutate()}
            >
              {fetchPricesMutation.isPending ? "Scanning..." : "Fetch Prices with AI"}
            </Button>
          </div>

          {hasTie && (
            <div className="mb-6 rounded-lg bg-neutral-50 px-5 py-4 text-b2 text-neutral-300">
              Tie detected: two or more qualified bidders have quoted the exact same price. Both
              receive the same L-rank. The Procurement Committee must resolve this tie manually.
            </div>
          )}

          <h3 className="mb-4 text-h3 text-neutral-300">Commercial Evaluation &amp; Ranking Table</h3>

          {rankingQuery.isLoading && (
            <p className="py-8 text-center text-b2 text-neutral-75">Loading ranking...</p>
          )}

          {!rankingQuery.isLoading && ranking.length > 0 && (
            <div className="mb-6 overflow-hidden rounded-lg border border-neutral-50">
              <table className="w-full text-left text-b3">
                <thead className="bg-neutral-50 text-neutral-100">
                  <tr>
                    <th className="px-4 py-3 font-normal">Rank</th>
                    <th className="px-4 py-3 font-normal">Bidder Name</th>
                    <th className="px-4 py-3 font-normal">Quoted Price</th>
                    <th className="px-4 py-3 font-normal">% Above L1</th>
                    <th className="px-4 py-3 font-normal">Recommendation / Status</th>
                  </tr>
                </thead>
                <tbody>
                  {ranking.map((r) => (
                    <tr key={r.bidder_id} className="border-t border-neutral-50">
                      <td className="px-4 py-3">
                        <Badge tone={rankTone(r)}>
                          {r.label}
                          {r.tie ? " (TIE)" : ""}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-neutral-300">{r.name}</td>
                      <td className="px-4 py-3 text-neutral-300">{formatPrice(r)}</td>
                      <td className="px-4 py-3 text-neutral-300">
                        {r.pct_above_l1 !== null ? `${r.pct_above_l1.toFixed(2)}%` : "—"}
                      </td>
                      <td className="px-4 py-3 text-neutral-300">{recommendation(r)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {l1Entry && (
            <div className="rounded-lg bg-violet-50 px-5 py-4 text-b2 text-violet-300">
              Recommended L1 Bidder: {l1Entry.name} — Quoted Price: {formatPrice(l1Entry)}.
              Evaluated as lowest qualified commercial offer for Committee approval.
            </div>
          )}
          {!l1Entry && ranking.length > 0 && unpricedCount === ranking.length && (
            <div className="rounded-lg bg-neutral-50 px-5 py-4 text-b2 text-neutral-300">
              All qualified bidders currently show &quot;Price Not Mentioned&quot;. Click
              &quot;Fetch Prices with AI&quot; above to extract quotations from bidder documents.
            </div>
          )}

          <p className="mt-4 text-b3 text-neutral-75">
            Only the commercial table is included in official evaluation proceedings. The ranking
            will automatically be reflected in Section 5 of the generated MOM document.
          </p>
        </>
      )}
    </>
  );
}
