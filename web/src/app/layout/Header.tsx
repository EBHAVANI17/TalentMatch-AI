import { useEffect, useRef, useState, type ReactNode } from "react";
import { LogOut, Moon, Sun } from "lucide-react";
import { useAuth } from "@/lib/auth/AuthProvider";
import { roleLabel } from "@/lib/auth/roles";
import { applyTheme, getInitialTheme, type Theme } from "@/lib/theme";
import { NotificationsMenu } from "./NotificationsMenu";

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  useEffect(() => applyTheme(theme), [theme]);
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-fg"
      aria-label={`Switch to ${next} theme`}
    >
      {theme === "dark" ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
    </button>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!user) return null;
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-2"
      >
        <span className="flex size-8 items-center justify-center rounded-full bg-primary-soft text-xs font-bold text-primary">
          {initials(user.full_name)}
        </span>
        <span className="hidden text-left sm:block">
          <span className="block text-sm font-semibold leading-tight text-fg">{user.full_name}</span>
          <span className="block text-xs leading-tight text-muted">{roleLabel(user.role)}</span>
        </span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-30 mt-2 w-56 rounded-xl border border-border bg-surface p-1 shadow-card">
          <div className="border-b border-border px-3 py-2">
            <p className="truncate text-sm font-semibold text-fg">{user.full_name}</p>
            <p className="truncate text-xs text-muted">{user.email}</p>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => void logout()}
            className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-danger hover:bg-danger-soft"
          >
            <LogOut className="size-4" aria-hidden /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export function Header({ leading }: { leading?: ReactNode }) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-border bg-surface px-4 sm:px-6">
      <div className="flex items-center gap-2">{leading}</div>
      <div className="flex items-center gap-1">
        <NotificationsMenu />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
