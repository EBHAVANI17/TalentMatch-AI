import type { ReactNode } from "react";
import { Card } from "@/components/ui";

export function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="flex min-h-full items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-2.5">
          <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" className="size-8" />
          <span className="font-display text-xl font-semibold text-fg">Talent Match</span>
        </div>
        <Card className="p-6 sm:p-8">
          <h1 className="font-display text-2xl font-semibold text-fg">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </Card>
        {footer && <div className="mt-4 text-center text-sm text-muted">{footer}</div>}
      </div>
    </div>
  );
}
