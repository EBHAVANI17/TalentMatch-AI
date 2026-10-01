import type { LucideIcon } from "lucide-react";

const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

export function StatTile({ label, value, hint, icon: Icon }: { label: string; value: number | string | null | undefined; hint?: string; icon?: LucideIcon }) {
  const display = value === null || value === undefined ? "–" : typeof value === "number" ? compact.format(value) : value;
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-4 shadow-card">
      <span className="flex items-center gap-2 text-xs font-medium text-muted">
        {Icon && <Icon className="size-3.5" aria-hidden />}
        {label}
      </span>
      <span className="font-display text-2xl font-semibold text-fg">{display}</span>
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </div>
  );
}
