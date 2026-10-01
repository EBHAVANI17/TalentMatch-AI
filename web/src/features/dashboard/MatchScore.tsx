import { cn } from "@/components/ui";

/** Match percentage pill. The number is always shown; color is a secondary cue only. */
export function MatchScore({ value, className }: { value: number | null | undefined; className?: string }) {
  if (value === null || value === undefined) return null;
  const tone = value >= 85 ? "bg-success-soft text-success" : value >= 70 ? "bg-primary-soft text-primary" : "bg-surface-2 text-muted";
  return (
    <span
      className={cn("nowrap inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold", tone, className)}
      title="Fit to the job's listed criteria"
      style={{ fontVariantNumeric: "tabular-nums" }}
    >
      {value}% match
    </span>
  );
}
