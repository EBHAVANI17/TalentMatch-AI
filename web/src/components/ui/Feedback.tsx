import type { ReactNode } from "react";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import { Button } from "./Button";
import { cn } from "./cn";

export function Spinner({ label = "Loading", className }: { label?: string; className?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-sm text-muted", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden />
      <span>{label}</span>
    </span>
  );
}

export function FullPageSpinner({ label }: { label?: string }) {
  return (
    <div className="flex h-full min-h-[50vh] items-center justify-center">
      <Spinner label={label} />
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-surface-2", className)} />;
}

export function EmptyState({ title, description, action, icon }: { title: string; description?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <div className="mb-1 rounded-full bg-surface-2 p-3 text-muted">{icon ?? <Inbox className="size-5" aria-hidden />}</div>
      <p className="font-display text-sm font-semibold text-fg">{title}</p>
      {description && <p className="max-w-sm text-sm text-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", message, onRetry }: { title?: string; message?: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <div className="mb-1 rounded-full bg-danger-soft p-3 text-danger">
        <AlertTriangle className="size-5" aria-hidden />
      </div>
      <p className="font-display text-sm font-semibold text-fg">{title}</p>
      {message && <p className="max-w-sm text-sm text-muted">{message}</p>}
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-2" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Alert({ tone = "danger", children }: { tone?: "danger" | "success" | "warning" | "info"; children: ReactNode }) {
  const tones = {
    danger: "border-danger/30 bg-danger-soft text-danger",
    success: "border-success/30 bg-success-soft text-success",
    warning: "border-warning/30 bg-warning-soft text-warning",
    info: "border-primary/30 bg-primary-soft text-primary",
  };
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("rounded-lg border px-3 py-2 text-sm", tones[tone])}>
      {children}
    </div>
  );
}
