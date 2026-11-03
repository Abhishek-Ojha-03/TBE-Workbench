"use client";

import { useState } from "react";

function BellIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 01-3.46 0" />
    </svg>
  );
}

function ProfileIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-4 4-6 8-6s8 2 8 6" />
    </svg>
  );
}

interface WorkspaceHeaderProps {
  title: string;
  /** Mock tender options for the inline selector dropdown shown under the title. */
  tenderOptions?: string[];
  onBack?: () => void;
  rightSlot?: React.ReactNode;
}

export default function WorkspaceHeader({
  title,
  tenderOptions = ["Alpha"],
  onBack,
  rightSlot,
}: WorkspaceHeaderProps) {
  const [selectedTender, setSelectedTender] = useState(tenderOptions[0]);

  return (
    <div className="mb-8">
      <div className="mb-4 flex items-start justify-between">
        <h1 className="text-display text-neutral-100">{title}</h1>
        <div className="flex items-center gap-5">
          {rightSlot}
          <button
            type="button"
            aria-label="Notifications"
            className="relative flex h-9 w-9 items-center justify-center rounded-full text-neutral-300 hover:bg-neutral-50"
          >
            <BellIcon />
            <span className="absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
              13
            </span>
          </button>
          <button
            type="button"
            aria-label="Profile"
            className="flex h-9 w-9 items-center justify-center rounded-full text-neutral-300 hover:bg-neutral-50"
          >
            <ProfileIcon />
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1 rounded-md border border-neutral-50 px-3 py-1.5 text-b3 text-neutral-200 hover:bg-neutral-50"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 18l-6-6 6-6" />
          </svg>
          Back
        </button>

        <select
          value={selectedTender}
          onChange={(e) => setSelectedTender(e.target.value)}
          className="rounded-md border border-neutral-50 px-3 py-1.5 text-b3 text-neutral-200 focus:outline-none"
        >
          {tenderOptions.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
