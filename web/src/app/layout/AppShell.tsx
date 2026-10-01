import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { ExternalLink, Menu, X } from "lucide-react";
import { cn } from "@/components/ui";
import { useAuth } from "@/lib/auth/AuthProvider";
import { CLASSIC_WORKSPACE_URL, NAV_ITEMS } from "../navigation";
import { Header } from "./Header";

function BrandMark() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" className="size-7" />
      <span className="font-display text-lg font-semibold text-fg">Talent Match</span>
    </div>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth();
  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-6 px-3 py-5">
      <BrandMark />
      <ul className="flex flex-col gap-1">
        {NAV_ITEMS.filter((item) => item.visible(user)).map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === "/"}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "nowrap flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-primary-soft text-primary" : "text-muted hover:bg-surface-2 hover:text-fg",
                )
              }
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="mt-auto rounded-lg border border-border bg-surface-2 p-3">
        <p className="text-xs text-muted">More modules are moving to this new workspace. Everything else is in the classic workspace.</p>
        <a
          href={CLASSIC_WORKSPACE_URL}
          className="nowrap mt-2 inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
        >
          Open classic workspace <ExternalLink className="size-3" aria-hidden />
        </a>
      </div>
    </nav>
  );
}

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="flex h-full">
      <aside className="hidden w-60 shrink-0 border-r border-border bg-surface lg:block">
        <Sidebar />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <aside className="relative h-full w-64 border-r border-border bg-surface">
            <button
              type="button"
              aria-label="Close menu"
              className="absolute right-3 top-5 text-muted hover:text-fg"
              onClick={() => setMobileOpen(false)}
            >
              <X className="size-5" aria-hidden />
            </button>
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          leading={
            <button
              type="button"
              className="rounded-lg p-2 text-muted hover:bg-surface-2 hover:text-fg lg:hidden"
              aria-label="Open menu"
              onClick={() => setMobileOpen(true)}
            >
              <Menu className="size-5" aria-hidden />
            </button>
          }
        />
        <main id="main" className="min-w-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8">
          <div className="mx-auto max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
