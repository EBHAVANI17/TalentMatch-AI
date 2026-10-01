import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Building2, Shield, UserRound } from "lucide-react";
import { Alert, Button, Input } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { usePublicConfig } from "@/lib/config";
import { AuthLayout } from "./AuthLayout";

// Seeded demo accounts (backend/app/db/seed.py). Only shown when the server runs with DEMO_MODE=true.
const DEMO_PERSONAS = [
  { label: "Candidate", detail: "Aarav Sharma", email: "aarav@stanford.edu", password: "aarav123", icon: UserRound },
  { label: "Recruiter", detail: "Anthropic", email: "recruiter@anthropic.com", password: "anthropic123", icon: Building2 },
  { label: "Recruiter", detail: "Stripe", email: "recruiter@stripe.com", password: "stripe123", icon: Building2 },
  { label: "Platform admin", detail: "Super admin", email: "admin@talentmatch.ai", password: "admin123", icon: Shield },
];

export function LoginPage() {
  const { login } = useAuth();
  const { data: config } = usePublicConfig();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<string | null>(null);


  async function signIn(emailValue: string, passwordValue: string, source: string) {
    setError(null);
    setPending(source);
    try {
      // RedirectIfAuthenticated (around this page) sends the user to returnTo once signed in.
      await login(emailValue, passwordValue);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the server. Check your connection and try again.");
    } finally {
      setPending(null);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void signIn(email, password, "form");
  }

  return (
    <AuthLayout title="Sign in" subtitle="Welcome back. Sign in to your workspace.">
      {config?.demo_mode && (
        <div className="mb-6">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Demo accounts</p>
          <div className="grid gap-2">
            {DEMO_PERSONAS.map(({ label, detail, email: demoEmail, password: demoPassword, icon: Icon }) => (
              <Button
                key={demoEmail}
                variant="secondary"
                size="sm"
                icon={<Icon className="size-4" aria-hidden />}
                loading={pending === demoEmail}
                disabled={pending !== null}
                onClick={() => void signIn(demoEmail, demoPassword, demoEmail)}
                className="justify-start"
              >
                <span className="truncate">
                  {label} <span className="text-muted">({detail})</span>
                </span>
              </Button>
            ))}
          </div>
          <div className="mt-6 flex items-center gap-3 text-xs text-muted">
            <span className="h-px flex-1 bg-border" />
            or sign in with email
            <span className="h-px flex-1 bg-border" />
          </div>
        </div>
      )}

      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        {error && <Alert>{error}</Alert>}
        <Input label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-sm font-medium text-primary hover:underline">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" loading={pending === "form"} disabled={pending !== null || !email || !password}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  );
}
