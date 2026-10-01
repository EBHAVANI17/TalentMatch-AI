import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { EmptyState, ErrorState, Spinner, cn } from "@/components/ui";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type Notification = components["schemas"]["NotificationOut"];

const NOTIFICATIONS_KEY = ["notifications"];

export function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: NOTIFICATIONS_KEY,
    queryFn: () => api<Notification[]>("/notifications"),
    refetchInterval: 60_000,
  });

  const markRead = useMutation({
    mutationFn: (id: string) => api<Notification>(`/notifications/${id}/read`, { method: "PATCH" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY }),
  });

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const unread = data?.filter((n) => !n.is_read).length ?? 0;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        className="relative rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-fg"
      >
        <Bell className="size-4" aria-hidden />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Notifications" className="absolute right-0 top-full z-30 mt-2 w-[min(92vw,360px)] rounded-xl border border-border bg-surface shadow-card">
          <div className="border-b border-border px-4 py-3 font-display text-sm font-semibold">Notifications</div>
          <div className="max-h-96 overflow-y-auto">
            {isLoading ? (
              <div className="p-4">
                <Spinner />
              </div>
            ) : isError ? (
              <ErrorState message="Couldn't load notifications." onRetry={() => void refetch()} />
            ) : !data?.length ? (
              <EmptyState title="You're all caught up" description="New activity on your jobs and applications will show up here." />
            ) : (
              <ul>
                {data.slice(0, 20).map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => {
                        if (!n.is_read) markRead.mutate(n.id);
                        if (n.link?.startsWith("/app/")) {
                          setOpen(false);
                          navigate(n.link.slice(4)); // links are stored with the /app base path
                        }
                      }}
                      className={cn(
                        "flex w-full flex-col gap-0.5 border-b border-border px-4 py-3 text-left last:border-0 hover:bg-surface-2",
                        !n.is_read && "bg-primary-soft/40",
                      )}
                    >
                      <span className="flex items-center gap-2 text-sm font-semibold text-fg">
                        {!n.is_read && <span className="size-2 shrink-0 rounded-full bg-primary" aria-label="Unread" />}
                        {n.title}
                      </span>
                      <span className="text-xs text-muted">{n.message}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
