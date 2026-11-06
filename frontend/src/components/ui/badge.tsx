interface BadgeProps {
  children: React.ReactNode;
  tone?: "violet" | "neutral" | "orange";
  className?: string;
}

export default function Badge({ children, tone = "violet", className = "" }: BadgeProps) {
  const toneClasses =
    tone === "violet"
      ? "bg-violet-50 text-violet-300"
      : tone === "orange"
      ? "bg-orange-50 text-orange-500"
      : "bg-neutral-50 text-neutral-200";

  return (
    <span
      className={`inline-flex items-center rounded-full px-3 py-1 text-label font-medium ${toneClasses} ${className}`}
    >
      {children}
    </span>
  );
}
