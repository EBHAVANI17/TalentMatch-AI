import type { ReactNode } from "react";
import { cn } from "./cn";

type Tone = "neutral" | "primary" | "success" | "warning" | "danger";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted",
  primary: "bg-primary-soft text-primary",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={cn("nowrap inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold", TONES[tone])}>
      {children}
    </span>
  );
}
