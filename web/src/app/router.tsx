import { createBrowserRouter, useRouteError, type RouteObject } from "react-router-dom";
import { ButtonLink, EmptyState, ErrorState } from "@/components/ui";
import { AcceptInvitationPage, ForgotPasswordPage, ResetPasswordPage, VerifyEmailPage } from "@/features/auth/AccountPages";
import { LoginPage } from "@/features/auth/LoginPage";
import { CandidateDetailPage } from "@/features/candidates/CandidateDetailPage";
import { CandidatesPage } from "@/features/candidates/CandidatesPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { HomePage } from "@/features/home/HomePage";
import { JobDetailPage } from "@/features/jobs/JobDetailPage";
import { JobFormPage } from "@/features/jobs/JobFormPage";
import { JobsPage } from "@/features/jobs/JobsPage";
import { MyProfilePage } from "@/features/profile/MyProfilePage";
import { SearchPage } from "@/features/search/SearchPage";
import { JobsForYouPage } from "@/features/talent-match/JobsForYouPage";
import { TalentMatchPage } from "@/features/talent-match/TalentMatchPage";
import { TeamPage } from "@/features/team/TeamPage";
import { RedirectIfAuthenticated, RequireAuth, RequireRole } from "@/lib/auth/guards";
import { useAuth } from "@/lib/auth/AuthProvider";
import { isCandidate, isOrgAdmin, isOrgMember, isSuperAdmin } from "@/lib/auth/roles";
import type { User } from "@/lib/api/types";
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

const hiringTeam = (u: User | null) => isOrgMember(u) || isSuperAdmin(u);

/** Candidates get their home page; hiring teams and admins get the dashboard. */
function IndexPage() {
  const { user } = useAuth();
  return isCandidate(user) ? <HomePage /> : <DashboardPage />;
}

const hiring = (element: React.ReactNode) => <RequireRole allow={hiringTeam}>{element}</RequireRole>;

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
          { index: true, element: <IndexPage /> },
          { path: "jobs", element: hiring(<JobsPage />) },
          { path: "jobs/new", element: hiring(<JobFormPage />) },
          { path: "jobs/:jobId", element: hiring(<JobDetailPage />) },
          { path: "jobs/:jobId/edit", element: hiring(<JobFormPage />) },
          { path: "candidates", element: hiring(<CandidatesPage />) },
          { path: "candidates/:candidateId", element: hiring(<CandidateDetailPage />) },
          { path: "profile", element: <RequireRole allow={isCandidate}><MyProfilePage /></RequireRole> },
          { path: "talent-match", element: hiring(<TalentMatchPage />) },
          { path: "jobs-for-you", element: <RequireRole allow={isCandidate}><JobsForYouPage /></RequireRole> },
          { path: "search", element: <SearchPage /> },
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

export function createAppRouter() {
  return createBrowserRouter(routes, { basename: "/app" });
}
