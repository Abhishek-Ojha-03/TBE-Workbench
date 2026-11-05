"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

type IconName = "chart" | "grid" | "package" | "home";

function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  if (name === "home") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className}>
        <path d="M3 10.5L12 3l9 7.5" />
        <path d="M5 9.5V20a1 1 0 001 1h4v-6h4v6h4a1 1 0 001-1V9.5" />
      </svg>
    );
  }
  if (name === "chart") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className}>
        <path d="M3 17l5-5 4 4 8-8" />
        <path d="M14 8h6v6" />
      </svg>
    );
  }
  if (name === "grid") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className}>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
    );
  }
  // package
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className}>
      <path d="M21 8l-9-5-9 5 9 5 9-5z" />
      <path d="M3 8v8l9 5 9-5V8" />
      <path d="M12 13v8" />
    </svg>
  );
}

// NOTE: icons here are approximations (generic chart/grid/package glyphs),
// not exported directly from the Figma file — swap for the real exported
// SVGs when available, per Rule 2 (use original assets).
const NAV_ITEMS: { label: string; href: string; icon: IconName }[] = [
  { label: "Home", href: "/", icon: "home" },
  { label: "Specification", href: "/specification", icon: "chart" },
  { label: "Requirements & Setup", href: "/requirements-setup", icon: "grid" },
  { label: "TBE Working Excel", href: "/working-excel", icon: "chart" },
  { label: "Verification Results", href: "/verification-results", icon: "package" },
  { label: "Reports & Completion", href: "/reports-completion", icon: "package" },
  { label: "Commercial Evaluation", href: "/commercial-evaluation", icon: "package" },
  { label: "Accuracy Matrix", href: "/accuracy-matrix", icon: "package" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col justify-between border-r border-neutral-50 bg-white px-5 py-6">
      <div>
        <div className="mb-8 px-2">
          <Image src="/logo.png" alt="Exascale AI" width={140} height={18} />
        </div>

        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-b2 transition-colors ${
                  active
                    ? "bg-violet-50 font-medium text-violet-300"
                    : "text-neutral-200 hover:bg-neutral-50"
                }`}
              >
                <Icon name={item.icon} className={active ? "text-violet-300" : "text-neutral-100"} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <button
        type="button"
        className="flex items-center gap-2 px-3 py-2.5 text-b2 font-medium text-red-500 hover:bg-red-50 rounded-md"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
          <path d="M16 17l5-5-5-5" />
          <path d="M21 12H9" />
        </svg>
        Log out
      </button>
    </aside>
  );
}
