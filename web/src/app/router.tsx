import { createBrowserRouter, useRouteError, type RouteObject } from "react-router-dom";
import { ButtonLink, EmptyState, ErrorState } from "@/components/ui";
import { AcceptInvitationPage, ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage } from "@/features/auth/AccountPages";
import { LoginPage } from "@/features/auth/LoginPage";
import { HomePage } from "@/features/home/HomePage";
import { TeamPage } from "@/features/team/TeamPage";
import { RedirectIfAuthenticated, RequireAuth, RequireRole } from "@/lib/auth/guards";
import { isOrgAdmin, isSuperAdmin } from "@/lib/auth/roles";
import { AppShell } from "./layout/AppShell";

function RouteErrorBoundary() {
  const error = useRouteError();
  console.error(error);
  return (
    <div className="flex min-h-full items-center justify-center p-6">
      <ErrorState
        title="This page hit an unexpected error"
        message="The problem has been logged. Reload the page, or go back to your home screen."
        onRetry={() => window.location.reload()}
      />
    </div>
  );
}

function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      description="The page you're looking for doesn't exist, or hasn't moved to the new workspace yet."
      action={
        <ButtonLink to="/" variant="secondary" size="sm">
          Go home
        </ButtonLink>
      }
    />
  );
}

export const routes: RouteObject[] = [
  {
    errorElement: <RouteErrorBoundary />,
    children: [
      { path: "/login", element: <RedirectIfAuthenticated><LoginPage /></RedirectIfAuthenticated> },
      { path: "/forgot-password", element: <ForgotPasswordPage /> },
      { path: "/reset-password", element: <ResetPasswordPage /> },
      { path: "/verify-email", element: <VerifyEmailPage /> },
      { path: "/accept-invitation", element: <AcceptInvitationPage /> },
      {
        element: (
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        ),
        children: [
          { index: true, element: <HomePage /> },
          {
            path: "team",
            element: (
              <RequireRole allow={(u) => isOrgAdmin(u) || isSuperAdmin(u)}>
                <TeamPage />
              </RequireRole>
            ),
          },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

// Opt in to React Router v7 behaviour now so the eventual upgrade is a no-op.
export const ROUTER_FUTURE = {
  v7_relativeSplatPath: true,
  v7_fetcherPersist: true,
  v7_normalizeFormMethod: true,
  v7_partialHydration: true,
  v7_skipActionErrorRevalidation: true,
} as const;

export function createAppRouter() {
  return createBrowserRouter(routes, { basename: "/app", future: ROUTER_FUTURE });
}
