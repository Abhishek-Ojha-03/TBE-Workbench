import { create } from "zustand";

/**
 * Tracks which tender is currently "open" for the Specification /
 * Requirements & Setup screens — the same concept as the existing
 * Streamlit app's st.session_state["active_tender_id"].
 *
 * This is the first real cross-screen state need (per the note in
 * ARCHITECTURE.md Section 2 — Zustand was deferred until this moment).
 */
interface ActiveTenderState {
  tenderId: number | null;
  tenderName: string | null;
  setActiveTender: (id: number, name: string) => void;
  clearActiveTender: () => void;
}

export const useActiveTenderStore = create<ActiveTenderState>((set) => ({
  tenderId: null,
  tenderName: null,
  setActiveTender: (id, name) => set({ tenderId: id, tenderName: name }),
  clearActiveTender: () => set({ tenderId: null, tenderName: null }),
}));
