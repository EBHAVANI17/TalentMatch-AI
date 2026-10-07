import { useEffect, useState } from "react";
import { Link, matchPath, useLocation, useSearchParams } from "react-router-dom";
import { Bot, Maximize2, Plus, X } from "lucide-react";
import { useAuth } from "@/lib/auth/AuthProvider";
import { canUseCopilot } from "@/lib/auth/roles";
import { CopilotThread, type CopilotContext } from "./CopilotThread";

/** The record the user is looking at, so "this job" or "this candidate" just works. */
export function usePageContext(): CopilotContext {
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  const job = matchPath("/jobs/:jobId/*", pathname) ?? matchPath("/jobs/:jobId", pathname);
  if (job?.params.jobId && job.params.jobId !== "new") return { job_id: job.params.jobId };
  const candidate = matchPath("/candidates/:candidateId", pathname);
  if (candidate?.params.candidateId && candidate.params.candidateId !== "import") {
    return { candidate_id: candidate.params.candidateId };
  }
  if (matchPath("/talent-match", pathname) && params.get("job")) return { job_id: params.get("job")! };
  return {};
}

/** Header button + slide-over panel. Ctrl/Cmd+J toggles it from anywhere. */
export function CopilotLauncher() {
  const { user } = useAuth();
  const allowed = canUseCopilot(user);
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const context = usePageContext();
  const { pathname } = useLocation();

  useEffect(() => {
    if (!allowed) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [allowed]);

  if (!allowed || pathname.startsWith("/copilot")) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="copilot-panel"
        aria-label="Copilot"
        title="Copilot (Ctrl+J)"
        className="nowrap flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-medium text-muted hover:bg-surface-2 hover:text-fg"
      >
        <Bot className="size-4" aria-hidden />
        <span className="hidden md:inline">Copilot</span>
      </button>
      {open && (
        <aside
          id="copilot-panel"
          role="dialog"
          aria-label="Copilot"
          className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-border bg-surface-2 shadow-card sm:w-[28rem]"
        >
          <div className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-border bg-surface px-4">
            <h2 className="flex items-center gap-2 font-display text-base font-semibold text-fg">
              <Bot className="size-4 text-primary" aria-hidden /> Copilot
            </h2>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setConversationId(null)}
                className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-fg"
                aria-label="New conversation"
                title="New conversation"
              >
                <Plus className="size-4" aria-hidden />
              </button>
              <Link
                to={conversationId ? `/copilot?c=${conversationId}` : "/copilot"}
                onClick={() => setOpen(false)}
                className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-fg"
                aria-label="Open full page"
                title="Open full page and history"
              >
                <Maximize2 className="size-4" aria-hidden />
              </Link>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-fg"
                aria-label="Close copilot"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1">
            <CopilotThread
              conversationId={conversationId}
              onConversationChange={setConversationId}
              context={context}
            />
          </div>
        </aside>
      )}
    </>
  );
}
