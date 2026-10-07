/**
 * Pages reached from links in account emails: forgot/reset password,
 * email verification and team invitations.
 */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Input, Spinner } from "@/components/ui";
import { api } from "@/lib/api/client";
import type { MessageResponse, TokenResponse, User } from "@/lib/api/types";
import { useAuth } from "@/lib/auth/AuthProvider";
import { usePublicConfig } from "@/lib/config";
import { AuthLayout } from "./AuthLayout";

function BackToSignIn() {
  return (
    <Link to="/login" className="font-medium text-primary hover:underline">
      Back to sign in
    </Link>
  );
}

function MissingToken() {
  return (
    <AuthLayout title="Link incomplete" footer={<BackToSignIn />}>
      <Alert>This link is missing its security token. Open the link from the email again, or request a new one.</Alert>
    </AuthLayout>
  );
}

function usePasswordHint() {
  const { data } = usePublicConfig();
  return `At least ${data?.password_min_length ?? 8} characters.`;
}

// --------------------------------------------------------------------------
export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const request = useMutation({
    mutationFn: () => api<MessageResponse>("/auth/forgot-password", { method: "POST", body: { email }, auth: false }),
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    request.mutate();
  }

  return (
    <AuthLayout title="Reset your password" subtitle="We'll email you a link to choose a new password." footer={<BackToSignIn />}>
      {request.isSuccess ? (
        <Alert tone="success">{request.data.message}. Check your inbox.</Alert>
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          {request.isError && <Alert>{request.error.message}</Alert>}
          <Input label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button type="submit" loading={request.isPending} disabled={!email}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}

// --------------------------------------------------------------------------
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const hint = usePasswordHint();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const reset = useMutation({
    mutationFn: () =>
      api<MessageResponse>("/auth/reset-password", { method: "POST", body: { token, new_password: password }, auth: false }),
  });

  if (!token) return <MissingToken />;
  const mismatch = confirm.length > 0 && confirm !== password;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!mismatch) reset.mutate();
  }

  return (
    <AuthLayout title="Choose a new password" footer={<BackToSignIn />}>
      {reset.isSuccess ? (
        <div className="flex flex-col gap-4">
          <Alert tone="success">{reset.data.message}</Alert>
          <Button className="w-full" onClick={() => navigate("/login")}>
            Go to sign in
          </Button>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          {reset.isError && <Alert>{reset.error.message}</Alert>}
          <Input label="New password" type="password" autoComplete="new-password" hint={hint} required value={password} onChange={(e) => setPassword(e.target.value)} />
          <Input
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            error={mismatch ? "Passwords don't match" : undefined}
            onChange={(e) => setConfirm(e.target.value)}
          />
          <Button type="submit" loading={reset.isPending} disabled={!password || mismatch}>
            Update password
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}

// --------------------------------------------------------------------------
export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const { status, refreshUser } = useAuth();
  const verify = useMutation({
    mutationFn: () => api<User>("/auth/verify-email", { method: "POST", body: { token }, auth: false }),
    onSuccess: () => {
      if (status === "authenticated") void refreshUser();
    },
  });
  const started = useRef(false);

  useEffect(() => {
    if (token && !started.current) {
      started.current = true; // links are single-use; never submit twice (e.g. StrictMode)
      verify.mutate();
    }
  }, [token, verify]);

  if (!token) return <MissingToken />;
  return (
    <AuthLayout title="Confirm your email" footer={status === "authenticated" ? <Link to="/" className="font-medium text-primary hover:underline">Go to your workspace</Link> : <BackToSignIn />}>
      {verify.isSuccess ? (
        <Alert tone="success">Thanks, {verify.data.full_name.split(" ")[0]}. Your email address is confirmed.</Alert>
      ) : verify.isError ? (
        <Alert>{verify.error.message}. Sign in and request a new verification email from your home page.</Alert>
      ) : (
        <Spinner label="Confirming your email" />
      )}
    </AuthLayout>
  );
}

// --------------------------------------------------------------------------
export function AcceptInvitationPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const hint = usePasswordHint();
  const navigate = useNavigate();
  const { startSession, user, switchOrg } = useAuth();
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  // Signed in already: accept with this account (the API checks the invited email matches)
  const acceptAsMe = useMutation({
    mutationFn: () => api<TokenResponse>("/auth/accept-invitation", { method: "POST", body: { token } }),
    onSuccess: async (session) => {
      if (session.user.organization_id) await switchOrg(session.user.organization_id);
      navigate("/", { replace: true });
    },
  });
  const accept = useMutation({
    mutationFn: () =>
      api<TokenResponse>("/auth/accept-invitation", {
        method: "POST",
        body: { token, full_name: fullName, password },
        auth: false,
      }),
    onSuccess: (session) => {
      startSession(session);
      navigate("/", { replace: true });
    },
  });

  if (!token) return <MissingToken />;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    accept.mutate();
  }

  if (user) {
    return (
      <AuthLayout title="Join the organization" subtitle={`You're signed in as ${user.email}.`} footer={<BackToSignIn />}>
        <div className="flex flex-col gap-4">
          {acceptAsMe.isError && <Alert>{acceptAsMe.error.message}</Alert>}
          <p className="text-sm text-muted">
            Accepting adds this organization to your account. You can switch between your organizations from the header.
          </p>
          <Button onClick={() => acceptAsMe.mutate()} loading={acceptAsMe.isPending}>
            Accept invitation
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Join your team" subtitle="Set up your account to accept the invitation." footer={<BackToSignIn />}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {accept.isError && <Alert>{accept.error.message}</Alert>}
        <Input label="Full name" autoComplete="name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
        <Input label="Password" type="password" autoComplete="new-password" hint={hint} required value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button type="submit" loading={accept.isPending} disabled={!fullName.trim() || !password}>
          Create account and join
        </Button>
      </form>
    </AuthLayout>
  );
}
